"""Archive 378 summaries from vtext output to Obsidian vault (投资训练营).

Structure:
  F:/downloads/output/<班级>/<课程>_summary.md
  → F:/vault/20_Learning/投资训练营/<班级>/<课程>.md

Each archived file gets:
- Frontmatter (title, tags, source)
- Summary body
- Embedded clean text (原文 section, collapsible)
"""
from pathlib import Path
import re
import shutil

OUTPUT = Path(r"F:\downloads\output")
VAULT = Path(r"F:\vault\20_Learning\投资训练营")

summaries = sorted(OUTPUT.rglob("*_summary.md"))
print(f"Found {len(summaries)} summaries to archive", flush=True)

VAULT.mkdir(parents=True, exist_ok=True)
archived = 0
skipped = 0

for s in summaries:
    # Determine class folder and course name
    # s = OUTPUT/<班级>/<课程>_summary.md
    rel = s.relative_to(OUTPUT)
    class_folder = rel.parts[0]  # e.g. "大鹏寻龙班：基础篇"
    stem = rel.stem[:-8]  # drop _summary

    # Read summary and clean
    summary_text = s.read_text(encoding="utf-8").strip()
    clean_path = s.with_name(f"{stem}_clean.txt")
    if clean_path.exists():
        clean_text = clean_path.read_text(encoding="utf-8").strip()
    else:
        clean_text = "(clean text not available)"

    # Build frontmatter
    title = stem  # keep original name (already clean, e.g. "1、黑马股的底部买入信号！")
    frontmatter = f"""---
title: {title}
tags:
  - 投资训练营
  - {class_folder.split("：")[0]}
source: vtext extraction
created: 2026-06-27
---

"""

    # Build body: summary + embedded clean (Obsidian collapsible callout)
    clean_lines = []
    for line in clean_text.split("\n"):
        clean_lines.append(">" if line.strip() == "" else "> " + line)

    body = f"""{summary_text}

> [!quote]- 原文（纠错全文）
{chr(10).join(clean_lines)}
"""

    # Write to vault
    vault_class_dir = VAULT / class_folder
    vault_class_dir.mkdir(parents=True, exist_ok=True)
    out_path = vault_class_dir / f"{stem}.md"

    if out_path.exists():
        skipped += 1
    else:
        out_path.write_text(frontmatter + body, encoding="utf-8")
        archived += 1

    if archived % 50 == 0 and archived > 0:
        print(f"  Archived: {archived}/{len(summaries)}", flush=True)

print(f"\nDone. archived={archived} skipped={skipped} total={len(summaries)}", flush=True)
