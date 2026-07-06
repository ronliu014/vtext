"""Fix 投资训练营 vault notes: convert Hexo `{% fold %}` tags to Obsidian
collapsible callouts, matching 无忌心法's format.

`{% fold %}` is Hexo/Jekyll template syntax that Obsidian does not render, so
the "原文" block shows as literal text and cannot be collapsed. This rewrites it
to a native collapsible callout.

  Before:  ## 原文（ASR 纠错全文）\n\n{% fold "..." %}\n<text>\n{% /fold %}
  After:   > [!quote]- 原文（纠错全文）\n> <each line prefixed with "> ">

Idempotent: files already using the callout are skipped. Dry-run by default;
pass --apply to write changes.
"""
from pathlib import Path
import re
import sys

VAULT = Path(r"F:\vault\20_Learning\投资训练营")

PAT = re.compile(
    r'\n+(?:---\s*\n+)?##\s*原文（ASR 纠错全文）\s*\n+'
    r'\{%\s*fold[^%]*%\}\n'
    r'(.*?)'
    r'\n\{%\s*/fold\s*%\}\s*$',
    re.S,
)


def to_callout(original: str) -> str:
    """Wrap the original transcript as a collapsible [!quote] callout.

    Blank lines become ">" so the callout stays contiguous (a bare blank
    line would otherwise terminate the callout in Obsidian).
    """
    out = []
    for line in original.split("\n"):
        out.append(">" if line.strip() == "" else "> " + line)
    return "> [!quote]- 原文（纠错全文）\n" + "\n".join(out)


def convert(text: str):
    """Return rewritten text, None if already a callout, or "NOMATCH"."""
    if "> [!quote]" in text:
        return None
    m = PAT.search(text)
    if not m:
        return "NOMATCH"
    body = text[: m.start()].rstrip()
    return body + "\n\n" + to_callout(m.group(1)) + "\n"


def main():
    apply = "--apply" in sys.argv
    mds = sorted(VAULT.rglob("*.md"))
    print(f"Found {len(mds)} markdown files in 投资训练营")
    print(f"Mode: {'DRY-RUN (pass --apply to write)' if not apply else 'APPLY (will write changes)'}\n")

    converted = 0
    skipped = 0
    nomatch = []

    for md in mds:
        text = md.read_text(encoding="utf-8")
        new = convert(text)

        if new is None:
            skipped += 1
        elif new == "NOMATCH":
            nomatch.append(md.relative_to(VAULT))
        else:
            converted += 1
            if apply:
                md.write_text(new, encoding="utf-8")
            if converted <= 3:
                print(f"  OK {md.relative_to(VAULT)}")

    if converted > 3:
        print(f"  ... (and {converted - 3} more)")

    print(f"\nSummary:")
    print(f"  Converted: {converted}")
    print(f"  Skipped (already callout): {skipped}")
    print(f"  No match (unexpected structure): {len(nomatch)}")

    if nomatch:
        print("\nFiles with unexpected structure:")
        for p in nomatch[:10]:
            print(f"  {p}")

    if not apply and converted > 0:
        print(f"\nDry-run complete. Run with --apply to write {converted} files.")
    elif apply:
        print(f"\n{converted} files updated to collapsible callout format.")


if __name__ == "__main__":
    main()
