#!/usr/bin/env python3
"""Inspect edge cases: ind=1.00 uniform-indent books and metadata issues."""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.seed_real_books import load_from_dataset

def raw_inspect(path, label, n=1200):
    raw = load_from_dataset(path)
    if not raw:
        print(f"NOT FOUND: {path}\n"); return
    lines = raw.split('\n')
    sample = [l for l in lines[3:203] if l.strip()]
    ind    = sum(1 for l in sample if l and l[0] == ' ')
    non_ind= sum(1 for l in sample if l and l[0] != ' ' and len(l.strip()) > 3)
    ni_trans = sum(1 for j in range(1, len(sample))
                   if sample[j] and sample[j][0] == ' '
                   and sample[j-1] and sample[j-1][0] != ' ')
    avg_ind_len = (sum(len(l.strip().split()) for l in sample if l and l[0]==' ')
                  / max(ind, 1))

    print(f"=== {label} ===")
    print(f"  ind={ind}/{len(sample)} | non_ind={non_ind} | NI-trans={ni_trans} | avg_ind_words={avg_ind_len:.1f}")
    print(f"  Raw repr ({n} chars):")
    print(f"  {repr(raw[:n])}")
    print()

raw_inspect("prose/Bryusov/Республика Южного Креста.txt",    "Республика Южного Креста")
raw_inspect("prose/Bryusov/Юпитер поверженный.txt",          "Юпитер поверженный")
raw_inspect("prose/Gogol/Невский проспект.txt",               "Невский проспект")
raw_inspect("prose/Dostoevsky/Белые ночи.txt",               "Белые ночи")
raw_inspect("prose/Dostoevsky/Вечный муж.txt",               "Вечный муж")
raw_inspect("prose/Turgenev/Записки охотника.txt",            "Записки охотника")
raw_inspect("prose/Chekhov/Вишнёвый сад.txt",                "Вишнёвый сад")
