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
