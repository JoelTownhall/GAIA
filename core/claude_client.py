"""Thin wrapper around the Anthropic SDK for the app's Claude calls.

- API key comes from Streamlit secrets (ANTHROPIC_API_KEY) or the environment.
- The guardrails and framework text go in a cached system block, so repeat turns
  don't pay for them again.
- Server-side refusal fallbacks are enabled (`fallbacks="default"`).
"""
from __future__ import annotations

from collections.abc import Iterator
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
