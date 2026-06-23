"""Tests for vtext_client.refine."""
import requests

import pytest
from unittest.mock import patch

from vtext_client.refine import (
    CORRECT_SYSTEM_PROMPT,
    STRUCTURE_SYSTEM_PROMPT,
    _dispatch,
    _strip_think,
    refine_text,
    to_simplified,
)
from vtext_client.errors import RefineError

OPTS = dict(ollama_url="http://ollama:11434", model="qwen3.5:9b",
            server_url="http://srv:8000", timeout=60)
MSGS = [{"role": "user", "content": "hi"}]


class TestStripThink:
    def test_removes_think_block(self):
        assert _strip_think("<think>reasoning</think>answer") == "answer"

    def test_no_think_unchanged(self):
        assert _strip_think("plain text") == "plain text"

    def test_multiline_think(self):
        assert _strip_think("<think>a\nb\nc</think>\nresult") == "result"


class TestToSimplified:
    def test_converts_traditional(self):
        assert to_simplified("簡體字") == "简体字"

    def test_already_simplified(self):
        assert to_simplified("已经简化") == "已经简化"


class TestDispatch:
    def test_direct_mode_calls_ollama_only(self):
        with patch("vtext_client.refine._ollama_chat_direct", return_value="D") as d, \
             patch("vtext_client.refine._refine_via_server") as s:
            assert _dispatch(MSGS, mode="direct", **OPTS) == "D"
        d.assert_called_once()
        s.assert_not_called()

    def test_server_mode_calls_relay_only(self):
        with patch("vtext_client.refine._ollama_chat_direct") as d, \
             patch("vtext_client.refine._refine_via_server", return_value="S") as s:
            assert _dispatch(MSGS, mode="server", **OPTS) == "S"
        s.assert_called_once()
        d.assert_not_called()

    def test_auto_falls_back_on_direct_failure(self):
        with patch("vtext_client.refine._ollama_chat_direct",
                   side_effect=requests.ConnectionError("no ollama")), \
             patch("vtext_client.refine._refine_via_server", return_value="S") as s:
            assert _dispatch(MSGS, mode="auto", **OPTS) == "S"
        s.assert_called_once()

    def test_auto_both_fail_raises_refine_error(self):
        with patch("vtext_client.refine._ollama_chat_direct",
                   side_effect=requests.ConnectionError("no ollama")), \
             patch("vtext_client.refine._refine_via_server",
                   side_effect=Exception("relay down")):
            with pytest.raises(RefineError):
                _dispatch(MSGS, mode="auto", **OPTS)

    def test_direct_failure_in_direct_mode_propagates(self):
        # In explicit direct mode there is no fallback; a connection error is
        # wrapped by refine_text (tested below), but _dispatch lets it bubble.
        with patch("vtext_client.refine._ollama_chat_direct",
                   side_effect=requests.ConnectionError("no")):
            with pytest.raises(requests.ConnectionError):
                _dispatch(MSGS, mode="direct", **OPTS)


class TestRefinePipeline:
    def test_returns_clean_and_summary_chained(self):
        """summary is derived FROM clean (structuring input == clean output)."""
        def fake_dispatch(messages, **kw):
            sys_content = messages[0]["content"]
            user_content = messages[1]["content"]
            if sys_content == CORRECT_SYSTEM_PROMPT:
                return f"C:{user_content}"
            return f"S:{user_content}"

        with patch("vtext_client.refine._dispatch", side_effect=fake_dispatch):
            clean, summary = refine_text("原始文本", mode="direct", **OPTS)

        assert clean.startswith("C:")
        # structuring received the clean text as input
        assert summary == f"S:{clean}"

    def test_two_llm_calls_made(self):
        calls = []

        def fake_dispatch(messages, **kw):
            calls.append(messages[0]["content"])
            return "ok"

        with patch("vtext_client.refine._dispatch", side_effect=fake_dispatch):
            refine_text("some text", mode="direct", **OPTS)

        assert len(calls) == 2
        assert calls[0] == CORRECT_SYSTEM_PROMPT
        assert calls[1] == STRUCTURE_SYSTEM_PROMPT

    def test_failure_wrapped_as_refine_error(self):
        with patch("vtext_client.refine._dispatch", side_effect=Exception("boom")):
            with pytest.raises(RefineError):
                refine_text("x", mode="direct", **OPTS)
