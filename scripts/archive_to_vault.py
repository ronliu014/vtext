"""Archive *_summary.md into the Obsidian vault with frontmatter + embedded source.

For each ``<stem>_summary.md`` under OUTPUT_ROOT this emits
``VAULT/<YYYY-MM>/<date>_<title>.md`` containing:

  - YAML frontmatter (date, title, source, video_id, tags)
  - the structured summary body
  - a collapsible Obsidian callout holding the sibling ``<stem>_clean.txt``
    (the corrected full text) as the note's source

The ugly numeric download id is dropped from the visible filename but kept
in ``video_id`` for traceability. Idempotent: regenerates each note on run.
"""
import re
from pathlib import Path

OUTPUT_ROOT = Path(r"F:\vtext\output")
VAULT_ROOT = Path(r"F:\vault\20_Learning\无忌心法")
SOURCE_NAME = "无忌心法"
TAG = "财经/无忌心法"

STEM_RE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})_(?P<title>.+)_(?P<vid>\d+)_summary$")


def _callout(clean_text: str) -> str:
    """Wrap the clean full text in a collapsed Obsidian quote callout."""
    lines = clean_text.strip().splitlines()
    quoted = "\n".join(("> " + ln) if ln.strip() else ">" for ln in lines)
    return "> [!quote]- 原文（纠错全文）\n" + quoted


def build_note(date: str, title: str, vid: str, summary_body: str, clean_text: str) -> str:
    fm = [
        "---",
        f"date: {date}",
        f'title: "{title}"',
        f"source: {SOURCE_NAME}",
        f'video_id: "{vid}"',
        "tags:",
        f"  - {TAG}",
        "---",
        "",
    ]
    parts = ["\n".join(fm), summary_body.strip(), ""]
    if clean_text.strip():
        parts.append(_callout(clean_text))
        parts.append("")
    return "\n".join(parts)


def main() -> int:
    summaries = sorted(OUTPUT_ROOT.rglob("*_summary.md"))
    written = 0
    no_clean: list[str] = []
    unmatched: list[str] = []
    for s in summaries:
        m = STEM_RE.match(s.stem)
        if not m:
            unmatched.append(s.name)
            continue
        date, title, vid = m["date"], m["title"], m["vid"]
        month = date[:7]
        clean_path = s.with_name(s.name.replace("_summary.md", "_clean.txt"))
        clean_text = (
            clean_path.read_text(encoding="utf-8") if clean_path.exists() else ""
        )
        if not clean_text.strip():
            no_clean.append(title)
        note = build_note(date, title, vid, s.read_text(encoding="utf-8"), clean_text)
        out_dir = VAULT_ROOT / month
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{date}_{title}.md").write_text(note, encoding="utf-8")
        written += 1

    print(f"wrote {written} notes")
    if no_clean:
        print(f"{len(no_clean)} note(s) had no clean text: {no_clean}")
    if unmatched:
        print(f"{len(unmatched)} file(s) did not match the name pattern: {unmatched}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
