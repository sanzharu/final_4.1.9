#!/usr/bin/env python3
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.seed_real_books import load_from_dataset

def raw_inspect(path, label, offset=0, length=600):
    raw = load_from_dataset(path)
    if not raw:
        print(f"NOT FOUND: {path}"); return
    snippet = raw[offset:offset+length]
    nn = raw.count('\n\n')
    n = raw.count('\n')
    # Find first \n\n position
    first_nn = raw.find('\n\n')
    print(f"=== {label} ===")
    print(f"  Total chars: {len(raw):,} | \\n: {n:,} | \\n\\n: {nn:,} | first \\n\\n at: {first_nn}")
    print(f"  Repr [{offset}:{offset+length}]:")
    print(f"  {repr(snippet)}")
    print()

raw_inspect("prose/Tolstoy/Война и мир. Том 1.txt",  "Война и мир (full raw start)")
raw_inspect("prose/Gogol/Невский проспект.txt",       "Невский проспект (raw start)")
raw_inspect("prose/Gogol/Шинель.txt",                 "Шинель (raw start)")
raw_inspect("prose/Dostoevsky/Белые ночи.txt",        "Белые ночи (raw start)")
raw_inspect("prose/Dostoevsky/Идиот.txt",             "Идиот (raw start)")
raw_inspect("prose/Tolstoy/Юность.txt",               "Юность (good para_r, 25 single-para)")
raw_inspect("prose/Gogol/Ревизор.txt",                "Ревизор (good para_r, 25 single-para)")
