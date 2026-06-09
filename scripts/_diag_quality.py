#!/usr/bin/env python3
"""Check actual paragraph quality after cleaning."""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.seed_real_books import load_from_dataset, clean_russian_text, parse_chapters

def check(path, label):
    raw = load_from_dataset(path)
    if not raw:
        print(f"NOT FOUND: {path}\n"); return
    cleaned = clean_russian_text(raw)
    chs = parse_chapters(cleaned, is_russian=True, max_ch=25, min_words=200)
    if not chs:
        print(f"NO CHAPTERS: {label}\n"); return

    # Collect paragraph stats across all chapters
    all_para_lens = []
    for c in chs:
        paras = [p for p in c["content"].split("\n\n") if p.strip()]
        all_para_lens.extend(len(p.split()) for p in paras)

    avg = sum(all_para_lens) / max(len(all_para_lens), 1)
    tiny = sum(1 for l in all_para_lens if l < 15)   # < 15 words = fragment
    good = sum(1 for l in all_para_lens if l >= 30)   # ≥ 30 words = real para

    c0 = chs[0]
    paras0 = c0["content"].split("\n\n")
    sample_paras = paras0[:3]

    status = "OK " if (avg >= 30 and tiny / max(len(all_para_lens), 1) < 0.30) else "BAD"
    print(f"[{status}] {label}")
    print(f"       ch={len(chs)}  paras={len(all_para_lens)}  avg={avg:.0f}w  tiny={tiny}({100*tiny//max(len(all_para_lens),1)}%)  good={good}")
    print(f"       Ch1 title: {c0['title']}")
    for i, p in enumerate(sample_paras[:2]):
        words = p.split()
        print(f"       Para {i+1} ({len(words)}w): {' '.join(words[:20])}{'...' if len(words)>20 else ''}")
    print()

# Key test cases — mix of all format types
check("prose/Tolstoy/Война и мир. Том 1.txt",        "Война и мир Т.1")
check("prose/Tolstoy/Семейное счастье.txt",           "Семейное счастье")
check("prose/Dostoevsky/Братья Карамазовы.txt",       "Братья Карамазовы")
check("prose/Dostoevsky/Белые ночи.txt",              "Белые ночи")
check("prose/Dostoevsky/Вечный муж.txt",              "Вечный муж")
check("prose/Pushkin/Капитанская дочка.txt",          "Капитанская дочка")
check("prose/Pushkin/Дубровский.txt",                 "Дубровский")
check("prose/Gogol/Мёртвые души. Том 1.txt",          "Мёртвые души")
check("prose/Gogol/Шинель.txt",                       "Шинель")
check("prose/Gogol/Вий.txt",                          "Вий")
check("prose/Gogol/Невский проспект.txt",             "Невский проспект")
check("prose/Turgenev/Записки охотника.txt",          "Записки охотника")
check("prose/Turgenev/Первая любовь.txt",             "Первая любовь")
check("prose/Turgenev/Дворянское гнездо.txt",         "Дворянское гнездо")
check("prose/Chekhov/Вишнёвый сад.txt",               "Вишнёвый сад")
check("prose/Chekhov/Шинель.txt",                     "Шинель (Чехов?)")
check("prose/Lermontov/Герой нашего времени.txt",     "Герой нашего времени")
check("prose/Gorky/Мать.txt",                         "Мать")
check("prose/Bryusov/Юпитер поверженный.txt",         "Юпитер поверженный")
check("prose/Bryusov/Республика Южного Креста.txt",   "Республика Южного Креста")
