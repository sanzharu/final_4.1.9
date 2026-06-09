#!/usr/bin/env python3
"""Detailed diagnosis of Russian text format issues."""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.seed_real_books import load_from_dataset

def diagnose(path, label, show_chars=800):
    raw = load_from_dataset(path)
    if not raw:
        print(f"NOT FOUND: {path}\n"); return

    # Find body start (skip header lines, find first long paragraph)
    lines = raw.split('\n')
    body_start = 0
    for i, l in enumerate(lines[:30]):
        if len(l.strip()) > 100:
            body_start = i; break

    body = '\n'.join(lines[body_start:])

    # Stats
    total_newlines = body.count('\n')
    double_newlines = body.count('\n\n')
    indented_lines = sum(1 for l in lines[body_start:body_start+200] if l and l[0] == ' ')
    total_body_lines = sum(1 for l in lines[body_start:body_start+200] if l.strip())
    multi_spaces = len(re.findall(r'  +', body[:3000]))

    print(f"=== {label} ===")
    print(f"  \\n count in body: {total_newlines:,} | \\n\\n count: {double_newlines:,} | ratio: {double_newlines/max(total_newlines,1):.3f}")
    print(f"  Indented lines (first 200): {indented_lines}/{total_body_lines}")
    print(f"  Multi-space occurrences (first 3000 chars): {multi_spaces}")
    print(f"  Raw repr (body start, {show_chars} chars):")
    print(f"  {repr(body[:show_chars])}")
    print()

diagnose("prose/Lermontov/Герой нашего времени.txt",       "Герой нашего времени")
diagnose("prose/Pushkin/Капитанская дочка.txt",             "Капитанская дочка")
diagnose("prose/Dostoevsky/Братья Карамазовы. Книга 1.txt", "Братья Карамазовы")
diagnose("prose/Gogol/Тарас Бульба.txt",                   "Тарас Бульба")
diagnose("prose/Turgenev/Отцы и дети.txt",                  "Отцы и дети")
diagnose("prose/Gorky/Мать.txt",                            "Мать")
