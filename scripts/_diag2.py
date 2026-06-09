#!/usr/bin/env python3
"""Look at actual chapter content for problem books."""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.seed_real_books import load_from_dataset, clean_russian_text, parse_chapters

def show(path, label):
    raw = load_from_dataset(path)
    if not raw:
        print(f"NOT FOUND: {path}\n"); return
    cleaned = clean_russian_text(raw)
    chs = parse_chapters(cleaned, is_russian=True, max_ch=5, min_words=200)
    if not chs:
        print(f"NO CHAPTERS: {label}\n"); return
    c = chs[0]
    paras = c["content"].split("\n\n")
    print(f"=== {label} ===")
    print(f"  Ch1: '{c['title']}' | {len(paras)} paras | {c['words_count']} words")
    for i, p in enumerate(paras[:4]):
        words = p.split()
        print(f"  Para {i+1} ({len(words)}w): {repr(p[:200])}")
    print()

# indented & single_para=0 (presumably working but check quality)
show("prose/Tolstoy/Война и мир. Том 1.txt",          "Война и мир (indented, 0 single-para)")
# indented & single_para>0 (broken)
show("prose/Gogol/Невский проспект.txt",               "Невский проспект (indented, 25 single-para)")
show("prose/Bryusov/Юпитер поверженный.txt",           "Юпитер поверженный (indented, 25 single-para)")
# single_nl & single_para=25 (completely broken)
show("prose/Gogol/Шинель.txt",                         "Шинель (single_nl, 25 single-para)")
show("prose/Dostoevsky/Белые ночи.txt",                "Белые ночи (single_nl, 25 single-para)")
show("prose/Tolstoy/Юность.txt",                       "Юность (good para_r, 25 single-para)")
