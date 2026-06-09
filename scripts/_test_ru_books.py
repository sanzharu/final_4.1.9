#!/usr/bin/env python3
"""Inspect Russian book text quality."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.seed_real_books import load_from_dataset, clean_russian_text, parse_chapters

SAMPLES = [
    ("prose/Dostoevsky/Преступление и наказание.txt",  "Преступление и наказание"),
    ("prose/Gogol/Мертвые души. Том 1.txt",            "Мертвые души"),
    ("prose/Chekhov/Степь.txt",                        "Степь"),
    ("prose/Pushkin/Капитанская дочка.txt",            "Капитанская дочка"),
    ("prose/Turgenev/Отцы и дети.txt",                 "Отцы и дети"),
    ("prose/Gorky/Мать.txt",                           "Мать"),
    ("prose/Tolstoy/Анна Каренина.txt",                "Анна Каренина"),
    ("prose/Lermontov/Герой нашего времени.txt",       "Герой нашего времени"),
]

for path, label in SAMPLES:
    raw = load_from_dataset(path)
    if not raw:
        print(f"NOT FOUND: {path}\n"); continue
    cleaned = clean_russian_text(raw)
    chs = parse_chapters(cleaned, is_russian=True, max_ch=25, min_words=200)

    # Check for single-paragraph chapters (solid text = no paragraph breaks)
    single_para_count = sum(1 for c in chs if c["content"].count("\n\n") < 2)

    print(f"=== {label} ===")
    print(f"  Cleaned: {len(cleaned):,} chars | chapters: {len(chs)} | single-para: {single_para_count}")

    if chs:
        c0 = chs[0]
        paras0 = c0["content"].split("\n\n")
        print(f"  Ch1: '{c0['title']}'  — {len(paras0)} paras, {c0['words_count']} words")
        # Show raw structure: first 400 chars of cleaned text
        snippet = repr(cleaned[:600])
        print(f"  Raw start: {snippet}")
        # Show paragraph lengths of ch1
        lens = [len(p.split()) for p in paras0[:6]]
        print(f"  Para word counts (first 6): {lens}")
    print()
