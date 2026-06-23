"""LLM post-transcription refine: correct ASR errors + structure into Markdown.

Two-stage pipeline so each stage's output is independently inspectable for
debugging (raw ASR -> corrected clean text -> structured summary):

  1. ``correct_text``  : raw -> corrected + simplified, full flowing text
                         (keeps original order/content; only fixes errors)
  2. ``structure_text`` : clean -> structured Markdown reorganization

The summary is derived FROM the clean text, so a correction fault can never be
hidden by the structuring step.

LLM access tries Ollama directly first; on any failure it falls back to the
vtext-server relay (``POST /llm/chat``). All failures raise :class:`RefineError`
so callers can warn-and-skip without losing an already-produced transcript.
"""
import re

import requests

from .api import stream_llm_result, submit_llm_job
from .errors import RefineError

_DEFAULT_OPTIONS = {"temperature": 0.4}

CORRECT_SYSTEM_PROMPT = """你是一名专业的中文文字编辑。任务：对一段 ASR（语音自动转录）原文进行【纠错】，输出一份干净、完整、连贯的全文正文。

要求：
1. 纠正 ASR 转录中的错别字与术语错误。ASR 常把专有名词听错，请结合上下文还原正确写法（例如"戶深300"→"沪深300"、"雞油股"→"绩优股"、"傻戶"→"散户"、"傳小好掉頭"→"船小好掉头"、"護身兩式"→"沪深两市"、"福音"→"收益"、"開獎"→"开课"、"上漾"→"上扬"、"油資"→"游资"、"郵高到低"→"由高到低"、"重藏"→"重仓"等）。特别注意金融领域同音错字："主力"（主力资金/主力庄家）常被 ASR 听成"阻力"——凡指大资金/机构/推动股价的力量之处，应还原为"主力"（如"阻力在股价连续放量上涨之后"实为"主力"、"中长期的阻力去运作"实为"中长期的**主力**去运作"）；但"阻力位/突破阻力/支撑与阻力"等技术面术语中的"阻力"是正确的，应保留。
2. 【保持原文的完整内容、顺序与段意】——不重组、不删减、不合并段落、不添加原文没有的信息，只做纠错与必要的标点/断句整理。
3. 仅去除明显的口语重复与无意义语气词（如"嗯""啊""那个"），保留所有实质内容。
4. 输出统一使用简体中文。
5. 直接输出纠错后的全文正文；不要写任何前言、解释、小标题或"以下是整理结果"之类的话。"""

STRUCTURE_SYSTEM_PROMPT = """你是一名专业的中文内容编辑。任务：把下面这段【已经纠错、简体化】的全文，整理成结构清晰、便于阅读的 Markdown 文档。

要求：
1. 把内容重新组织成结构化形式，用 Markdown 标题（#/##）与列表呈现。根据具体内容自行选择最合适的结构（如：主旨、核心观点、方法/步骤、要点、注意事项、总结等），不要套用固定模板。
2. 严格忠于原文：只做整理与重组，不得添加原文没有的信息，不得发表评论或建议，不得捏造数据或结论。
3. 保留所有具体的事实、数字、条件、步骤与细节，不要遗漏关键内容。
4. 输出统一使用简体中文。
5. 直接输出 Markdown 正文；不要写任何前言或解释。"""


def to_simplified(text: str) -> str:
    """Traditional -> Simplified Chinese via opencc.

    Returns the input unchanged if opencc is unavailable (it is a core
    dependency, so this branch is purely defensive).
    """
    try:
        import opencc

        # tw2s (not t2s) so the verbal particle 著 -> 着 is converted
        # (意味著->意味着, 看著->看着) while legitimate 著 stays (著名/著作/显著).
        return opencc.OpenCC("tw2s").convert(text)
    except ImportError:
        return text


def refine_text(
    plain: str,
    *,
    ollama_url: str,
    model: str,
    server_url: str,
    mode: str = "auto",
    timeout: int = 300,
) -> tuple[str, str]:
    """Run the two-stage refine pipeline. Returns ``(clean_text, summary_md)``.

    Raises :class:`RefineError` on any failure (caller should warn-and-skip).
    """
    try:
        clean = correct_text(
            plain,
            ollama_url=ollama_url,
            model=model,
            server_url=server_url,
            mode=mode,
            timeout=timeout,
        )
        summary = structure_text(
            clean,
            ollama_url=ollama_url,
            model=model,
            server_url=server_url,
            mode=mode,
            timeout=timeout,
        )
        return clean, summary
    except RefineError:
        raise
    except Exception as e:  # noqa: BLE001 - non-fatal step: wrap anything
        raise RefineError(f"refine failed: {e}") from e


def correct_text(
    plain: str,
    *,
    ollama_url: str,
    model: str,
    server_url: str,
    mode: str = "auto",
    timeout: int = 300,
) -> str:
    """Stage 1: correct ASR errors + simplify, preserving full flowing text."""
    return _llm_transform(
        CORRECT_SYSTEM_PROMPT,
        to_simplified(plain),
        ollama_url=ollama_url,
        model=model,
        server_url=server_url,
        mode=mode,
        timeout=timeout,
    )


def structure_text(
    clean: str,
    *,
    ollama_url: str,
    model: str,
    server_url: str,
    mode: str = "auto",
    timeout: int = 300,
) -> str:
    """Stage 2: reorganize the (already clean) text into structured Markdown."""
    return _llm_transform(
        STRUCTURE_SYSTEM_PROMPT,
        clean,
        ollama_url=ollama_url,
        model=model,
        server_url=server_url,
        mode=mode,
        timeout=timeout,
    )


def _llm_transform(
    system_prompt: str,
    user_text: str,
    *,
    ollama_url: str,
    model: str,
    server_url: str,
    mode: str,
    timeout: int,
) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]
    raw = _dispatch(
        messages,
        ollama_url=ollama_url,
        model=model,
        server_url=server_url,
        mode=mode,
        timeout=timeout,
    )
    return to_simplified(_strip_think(raw))


def _dispatch(
    messages: list[dict],
    *,
    ollama_url: str,
    model: str,
    server_url: str,
    mode: str,
    timeout: int,
) -> str:
    if mode == "direct":
        return _ollama_chat_direct(ollama_url, model, messages, timeout)
    if mode == "server":
        return _refine_via_server(server_url, model, messages, timeout)
    # auto: try Ollama directly; on any failure fall back to the server relay.
    try:
        return _ollama_chat_direct(ollama_url, model, messages, timeout)
    except Exception as direct_err:  # noqa: BLE001 - any failure -> fallback
        try:
            return _refine_via_server(server_url, model, messages, timeout)
        except Exception as relay_err:  # noqa: BLE001
            raise RefineError(
                f"direct Ollama and server relay both failed "
                f"(direct: {direct_err}; relay: {relay_err})"
            ) from relay_err


def _ollama_chat_direct(
    ollama_url: str, model: str, messages: list[dict], timeout: int
) -> str:
    """Call Ollama /api/chat directly. Connection errors propagate (used by the
    auto-fallback in :func:`_dispatch`); bad responses raise :class:`RefineError`.
    """
    url = f"{ollama_url.rstrip('/')}/api/chat"
    resp = requests.post(
        url,
        json={
            "model": model,
            "messages": messages,
            "options": _DEFAULT_OPTIONS,
            "think": False,
            "stream": False,
        },
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RefineError(
            f"ollama direct returned {resp.status_code}: {resp.text[:200]}"
        )
    try:
        return resp.json()["message"]["content"]
    except (ValueError, KeyError, TypeError) as e:
        raise RefineError(f"ollama direct unexpected response: {e}") from e


def _refine_via_server(
    server_url: str, model: str, messages: list[dict], timeout: int
) -> str:
    """Submit to the vtext-server LLM relay and stream until done."""
    job_id = submit_llm_job(
        server_url, model, messages, options=_DEFAULT_OPTIONS, timeout=30
    )
    return stream_llm_result(server_url, job_id)


def _strip_think(text: str) -> str:
    """Remove any <think>...</think> reasoning blocks a model may emit."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
