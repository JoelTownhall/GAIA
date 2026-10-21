import pytest

from core import claude_client
from core.claude_client import ClaudeUnavailable, build_system


def test_build_system_caches_last_block_only():
    blocks = build_system("Rules", "Mode", cached_context="Framework text")
    assert len(blocks) == 2
    assert "cache_control" not in blocks[0]
    assert blocks[1]["cache_control"] == {"type": "ephemeral"}
    assert blocks[0]["text"] == "Rules\n\nMode"


def test_missing_key_gives_friendly_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(claude_client, "get_setting", lambda *a, **k: None)
    with pytest.raises(ClaudeUnavailable, match="ANTHROPIC_API_KEY"):
        claude_client.get_client()


from types import SimpleNamespace as NS


def test_collect_sources_dedupes_and_puts_cited_first():
    content = [
        NS(type="server_tool_use", name="web_search"),
        NS(type="web_search_tool_result", content=[
            NS(url="https://abs.gov.au/a", title="ABS"), NS(url="https://pc.gov.au/b", title="PC")]),
        NS(type="web_search_tool_result", content=NS(error_code="max_uses_exceeded")),
        NS(type="text", text="Finding.", citations=[NS(url="https://pc.gov.au/b", title="PC")]),
        NS(type="text", text="More.", citations=None),
    ]
    sources = claude_client.collect_sources(content)
    assert [s["url"] for s in sources] == ["https://pc.gov.au/b", "https://abs.gov.au/a"]
    assert sources[0]["cited"] and not sources[1]["cited"]


class _FakeStream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        for b in self.message.content:
            if b.type == "server_tool_use":
                yield NS(type="content_block_start", content_block=b)
            if b.type == "text":
                yield NS(type="content_block_delta", delta=NS(type="text_delta", text=b.text))

    def get_final_message(self):
        return self.message


def test_web_tools_resume_after_pause_turn(monkeypatch):
    turns = [
        NS(stop_reason="pause_turn", usage=None,
           content=[NS(type="text", text="Part 1. ", citations=None),
                    NS(type="server_tool_use", name="web_search")]),
        NS(stop_reason="end_turn", usage=None, content=[NS(type="text", text="Part 2.", citations=None)]),
    ]
    sent = []

    def stream(**kwargs):
        sent.append(kwargs["messages"])
        return _FakeStream(turns[len(sent) - 1])

    fake = NS(beta=NS(messages=NS(stream=stream)))
    monkeypatch.setattr(claude_client, "get_client", lambda: fake)
    tools_seen = []
    result = claude_client.ChatResult()
    text = "".join(claude_client.stream_with_web_tools(
        [], [{"role": "user", "content": "q"}], result=result, on_tool=tools_seen.append))
    assert text == "Part 1. Part 2."
    assert result.text == "Part 1. Part 2." and result.stop_reason == "end_turn"
    assert tools_seen == ["web_search"]
    assert len(sent) == 2 and sent[1][-1]["role"] == "assistant"  # paused turn sent back as is


def test_structured_reply_returns_parsed_model(monkeypatch):
    from pydantic import BaseModel

    class Out(BaseModel):
        answer: str

    captured = {}

    def parse(**kwargs):
        captured.update(kwargs)
        return NS(stop_reason="end_turn", parsed_output=Out(answer="yes"))

    monkeypatch.setattr(claude_client, "get_client", lambda: NS(beta=NS(messages=NS(parse=parse))))
    assert claude_client.structured_reply([], [], Out).answer == "yes"
    assert captured["output_format"] is Out and captured["fallbacks"] == "default"

    monkeypatch.setattr(claude_client, "get_client", lambda: NS(beta=NS(messages=NS(
        parse=lambda **k: NS(stop_reason="refusal", parsed_output=None)))))
    with pytest.raises(ClaudeUnavailable, match="declined"):
        claude_client.structured_reply([], [], Out)
