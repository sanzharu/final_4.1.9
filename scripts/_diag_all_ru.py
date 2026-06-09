#!/usr/bin/env python3
"""Find all Russian books with paragraph-break problems."""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.seed_real_books import load_from_dataset, clean_russian_text, parse_chapters, BOOKS

RU_BOOKS = [b for b in BOOKS if b.get("source") == "dataset"]

fmt_stats = {"good": [], "single_nl": [], "indented": [], "not_found": []}

for bdef in RU_BOOKS:
    raw = load_from_dataset(bdef["dataset_path"])
    if not raw:
        fmt_stats["not_found"].append(bdef["title"]); continue

    # Detect format from RAW text (before cleaning)
    lines = raw.split('\n')
    sample_lines = [l for l in lines[5:200] if l.strip()]
    if not sample_lines:
        continue

    n_indented = sum(1 for l in sample_lines if l and l[0] == ' ' and len(l.strip()) > 3)
    indent_ratio = n_indented / len(sample_lines)

    body_part = raw[300:6300]
    nn = body_part.count('\n\n')
    n  = max(body_part.count('\n'), 1)
    para_ratio = nn / n

    if indent_ratio >= 0.20:
        fmt = "indented"
    elif para_ratio < 0.06:
        fmt = "single_nl"
    else:
        fmt = "good"

    # Also check how bad the current parsing is
    cleaned = clean_russian_text(raw)
    chs = parse_chapters(cleaned, is_russian=True, max_ch=25, min_words=200)
    single_para = sum(1 for c in chs if c["content"].count("\n\n") < 2)

    marker = "!!" if (fmt != "good" or single_para > 3) else "  "
    print(f"{marker} [{fmt:9s}|para_r={para_ratio:.3f}|ind={indent_ratio:.2f}] "
          f"single_para={single_para:2d}/{len(chs):2d}  {bdef['title']}")
    fmt_stats[fmt].append(bdef["title"])

print(f"\n=== Summary ===")
print(f"Good:      {len(fmt_stats['good'])}")
print(f"Single-NL: {len(fmt_stats['single_nl'])}")
print(f"Indented:  {len(fmt_stats['indented'])}")
print(f"Not found: {len(fmt_stats['not_found'])}")
if fmt_stats["not_found"]:
    print("  " + "\n  ".join(fmt_stats["not_found"]))
