"""Tests for vtext_client.refine."""
import requests

import pytest
from unittest.mock import patch

from vtext_client.refine import (
    CORRECT_SYSTEM_PROMPT,
    REFINE_CHUNK_CHARS,
    STRUCTURE_SYSTEM_PROMPT,
    _dispatch,
    _strip_think,
    refine_text,
    refine_text_chunked,
    split_refine_chunks,
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

    def test_particle_zhe_converted(self):
        # tw2s converts the verbal particle 著 -> 着 (the t2s gap wclaude reported)
        assert to_simplified("意味著 看著 走著 推動著") == "意味着 看着 走着 推动着"

    def test_legitimate_zhu_preserved(self):
        # 著 as "famous/work/significant" must stay
        assert to_simplified("著名 著作 顯著") == "著名 著作 显著"


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


class TestChunkedRefine:
    def test_split_preserves_text_and_limit(self):
        text = "第一句。第二句！第三句没有标点"
        chunks = split_refine_chunks(text, max_chars=6)

        assert "".join(chunks) == text
        assert all(0 < len(chunk) <= 6 for chunk in chunks)

    def test_default_chunk_limit(self):
        chunks = split_refine_chunks("字" * (REFINE_CHUNK_CHARS + 1))

        assert [len(chunk) for chunk in chunks] == [REFINE_CHUNK_CHARS, 1]

    def test_rejects_non_positive_limit(self):
        with pytest.raises(ValueError):
            split_refine_chunks("text", max_chars=0)

    def test_refines_each_chunk_and_nests_summary_headings(self):
        progress = []

        with patch(
            "vtext_client.refine.correct_text",
            side_effect=lambda text, **kwargs: f"clean:{text}",
        ) as correct, patch(
            "vtext_client.refine.structure_text",
            side_effect=lambda text, **kwargs: f"# summary\n{text}",
        ) as structure:
            clean, summary = refine_text_chunked(
                "甲。乙。",
                chunk_chars=2,
                on_progress=lambda index, total, stage: progress.append(
                    (index, total, stage)
                ),
                mode="server",
                **OPTS,
            )

        assert clean == "clean:甲。\n\nclean:乙。"
        assert summary.startswith("# 分段整理")
        assert "## 第 1 部分" in summary
        assert "### summary" in summary
        assert correct.call_count == 2
        assert structure.call_count == 2
        assert progress == [
            (1, 2, "correct"),
            (1, 2, "structure"),
            (2, 2, "correct"),
            (2, 2, "structure"),
        ]

    def test_reports_failed_chunk(self):
        with patch(
            "vtext_client.refine.correct_text",
            side_effect=["clean:甲。", RefineError("timeout")],
        ), patch("vtext_client.refine.structure_text", return_value="# summary"):
            with pytest.raises(RefineError, match="chunk 2/2"):
                refine_text_chunked("甲。乙。", chunk_chars=2, mode="server", **OPTS)
