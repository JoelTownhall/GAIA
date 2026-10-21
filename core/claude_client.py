"""Thin wrapper around the Anthropic SDK for the app's Claude calls.

- API key comes from Streamlit secrets (ANTHROPIC_API_KEY) or the environment.
- The guardrails and framework text go in a cached system block, so repeat turns
  don't pay for them again.
- Server-side refusal fallbacks are enabled (`fallbacks="default"`).
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

import anthropic

from core.config import get_setting, model_for

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeUnavailable(RuntimeError):
    """Raised when Claude can't be called; the message is safe to show users."""


def get_client() -> anthropic.Anthropic:
    api_key = get_setting("ANTHROPIC_API_KEY")
    if not api_key:
        raise ClaudeUnavailable(
            "Claude is not configured. Add ANTHROPIC_API_KEY to the app's secrets."
        )
    return anthropic.Anthropic(api_key=api_key)


def build_system(*parts: str, cached_context: str = "") -> list[dict]:
    """System blocks: static instructions, then cached reference context.

    Everything here must be deterministic (no timestamps or per-user values),
    or the prompt cache is invalidated on every request.
    """
    blocks = [{"type": "text", "text": "\n\n".join(p.strip() for p in parts if p)}]
    if cached_context:
        blocks.append({"type": "text", "text": cached_context})
    blocks[-1]["cache_control"] = {"type": "ephemeral"}
    return blocks


@dataclass
class ChatResult:
    text: str = ""
    stop_reason: str | None = None
    usage: dict = field(default_factory=dict)
    content: list = field(default_factory=list)


def _friendly_error(exc: Exception) -> ClaudeUnavailable:
    if isinstance(exc, anthropic.AuthenticationError):
        return ClaudeUnavailable("The Claude API key was rejected. Check ANTHROPIC_API_KEY.")
    if isinstance(exc, anthropic.RateLimitError):
        return ClaudeUnavailable("Claude is rate limited right now. Try again in a minute.")
    if isinstance(exc, anthropic.APIStatusError):
        return ClaudeUnavailable(f"Claude returned an error ({exc.status_code}). Try again.")
    if isinstance(exc, anthropic.APIConnectionError):
        return ClaudeUnavailable("Could not reach the Claude API. Check the network.")
    return ClaudeUnavailable(str(exc))


def stream_reply(
    system: list[dict],
    messages: list[dict],
    task: str = "advice",
    effort: str = "medium",
    tools: list[dict] | None = None,
    max_tokens: int = 32000,
    result: ChatResult | None = None,
) -> Iterator[str]:
    """Yield text deltas; fills `result` with the final message details.

    Usable directly with `st.write_stream`.
    """
    client = get_client()
    kwargs = dict(
        model=model_for(task),
        max_tokens=max_tokens,
        system=system,
        messages=messages,
        output_config={"effort": effort},
        betas=[FALLBACK_BETA],
        fallbacks="default",
    )
    if tools:
        kwargs["tools"] = tools
    try:
        with client.beta.messages.stream(**kwargs) as stream:
            yield from stream.text_stream
            final = stream.get_final_message()
    except anthropic.APIError as exc:
        raise _friendly_error(exc) from exc

    if final.stop_reason == "refusal":
        raise ClaudeUnavailable(
            "Claude declined to answer this request. Try rephrasing, or contact OIA directly."
        )
    if result is not None:
        result.text = "".join(b.text for b in final.content if b.type == "text")
        result.stop_reason = final.stop_reason
        result.content = final.content
        result.usage = final.usage.to_dict() if final.usage else {}


def structured_reply(
    system: list[dict],
    messages: list[dict],
    output_model: type,
    task: str = "advice",
    effort: str = "high",
    max_tokens: int = 32000,
):
    """One request whose answer is validated against a pydantic model (structured output).

    Returns the parsed model instance.
    """
    client = get_client()
    try:
        response = client.beta.messages.parse(
            model=model_for(task),
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            output_format=output_model,
            output_config={"effort": effort},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
    except anthropic.APIError as exc:
        raise _friendly_error(exc) from exc
    if response.stop_reason == "refusal":
        raise ClaudeUnavailable(
            "Claude declined to answer this request. Try rephrasing, or contact OIA directly."
        )
    if response.stop_reason == "max_tokens" or response.parsed_output is None:
        raise ClaudeUnavailable("Claude's answer was incomplete. Try again with a shorter document.")
    return response.parsed_output


# Server-side web tools (Anthropic runs the searches; results come back in the response).
WEB_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 12},
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 8},
]
MAX_CONTINUATIONS = 5


def collect_sources(content: list) -> list[dict]:
    """Every web page the answer drew on: search results and cited pages, de-duplicated.

    Built from the API response itself, so the list doesn't depend on the model
    reproducing URLs correctly.
    """
    seen: dict[str, dict] = {}

    def add(url: str | None, title: str | None, cited: bool = False) -> None:
        if not url:
            return
        entry = seen.setdefault(url, {"url": url, "title": title or url, "cited": False})
        entry["cited"] = entry["cited"] or cited

    for block in content:
        btype = getattr(block, "type", None)
        if btype == "web_search_tool_result" and isinstance(getattr(block, "content", None), list):
            for r in block.content:
                add(getattr(r, "url", None), getattr(r, "title", None))
        elif btype == "web_fetch_tool_result":
            inner = getattr(block, "content", None)
            add(getattr(inner, "url", None), getattr(getattr(inner, "content", None), "title", None))
        elif btype == "text":
            for c in getattr(block, "citations", None) or []:
                add(getattr(c, "url", None), getattr(c, "title", None), cited=True)
    return sorted(seen.values(), key=lambda s: not s["cited"])


def stream_with_web_tools(
    system: list[dict],
    messages: list[dict],
    task: str = "research",
    effort: str = "high",
    max_tokens: int = 64000,
    result: ChatResult | None = None,
    on_tool: Callable[[str], None] | None = None,
) -> Iterator[str]:
    """Like `stream_reply`, with web search and fetch, resuming on `pause_turn`.

    `on_tool` is called with the tool name each time Claude starts a search or fetch.
    `result.content` holds every content block from every continuation.
    """
    client = get_client()
    convo = list(messages)
    all_content: list = []
    final = None
    for _ in range(MAX_CONTINUATIONS + 1):
        try:
            with client.beta.messages.stream(
                model=model_for(task),
                max_tokens=max_tokens,
                system=system,
                messages=convo,
                tools=WEB_TOOLS,
                output_config={"effort": effort},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            ) as stream:
                for event in stream:
                    if event.type == "content_block_delta" and event.delta.type == "text_delta":
                        yield event.delta.text
                    elif (event.type == "content_block_start" and on_tool
                          and event.content_block.type == "server_tool_use"):
                        on_tool(event.content_block.name)
                final = stream.get_final_message()
        except anthropic.APIError as exc:
            raise _friendly_error(exc) from exc
        all_content.extend(final.content)
        if final.stop_reason != "pause_turn":
            break
        convo = convo + [{"role": "assistant", "content": final.content}]

    if final is not None and final.stop_reason == "refusal":
        raise ClaudeUnavailable(
            "Claude declined to answer this request. Try rephrasing, or contact OIA directly."
        )
    if result is not None and final is not None:
        result.text = "".join(b.text for b in all_content if b.type == "text")
        result.stop_reason = final.stop_reason
        result.content = all_content
        result.usage = final.usage.to_dict() if final.usage else {}
