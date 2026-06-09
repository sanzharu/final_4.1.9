#!/usr/bin/env python3
"""
Seed the database with real books.

Russian books  → Kaggle «Russian Literature» dataset (data/ruslit/prose/)
English books  → Project Gutenberg (downloaded at runtime)

Run from project root:
    python scripts/seed_real_books.py
"""

import asyncio, re, sys, os, time, random, html as html_mod, zipfile, sqlite3, tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text as sa_text, delete as sa_delete, select as sa_select
# Seeding guard — marks DB as seeded so entrypoint.sh skips on restarts
try:
    from app.utils.check_data_loaded import mark_data_seeded as _mark_seeded
except ImportError:
    _mark_seeded = None  # app/utils not yet present; silently skip
from app.db.base import engine, AsyncSessionLocal, Base
import app.models
from app.models.user import User, UserRole
from app.models.book import Book, BookStatus, Genre
from app.models.chapter import Chapter
from app.models.tag import Tag, BookTag
from app.models.social import Review, Bookmark
from app.core.security import hash_password

random.seed(42)

# ─── Dataset path ────────────────────────────────────────────────────────────
_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_SCRIPT_DIR)
DATASET_DIR  = os.path.join(_PROJECT_DIR, "data", "ruslit")   # extracted dataset

# ══════════════════════════════════════════════════════════════════════════════
# AUTHORS
# ══════════════════════════════════════════════════════════════════════════════

RUSSIAN_AUTHORS = [
    {"username": "leo_tolstoy",        "email": "leo_tolstoy@classic.lib",
     "display_name": "Лев Толстой",
     "bio": "Лев Николаевич Толстой (1828–1910) — граф, русский писатель, один из величайших романистов мировой литературы. Автор «Войны и мира», «Анны Карениной», «Воскресения»."},
    {"username": "fyodor_dostoevsky",  "email": "dostoevsky@classic.lib",
     "display_name": "Фёдор Достоевский",
     "bio": "Фёдор Михайлович Достоевский (1821–1881) — русский писатель и мыслитель. Автор «Преступления и наказания», «Идиота», «Братьев Карамазовых»."},
    {"username": "alexander_pushkin",  "email": "pushkin@classic.lib",
     "display_name": "Александр Пушкин",
     "bio": "Александр Сергеевич Пушкин (1799–1837) — русский поэт, прозаик и драматург, основоположник современного русского литературного языка."},
    {"username": "nikolai_gogol",      "email": "gogol@classic.lib",
     "display_name": "Николай Гоголь",
     "bio": "Николай Васильевич Гоголь (1809–1852) — русский прозаик, драматург и публицист. Автор «Мёртвых душ», «Ревизора», «Вечеров на хуторе близ Диканьки»."},
    {"username": "ivan_turgenev",      "email": "turgenev@classic.lib",
     "display_name": "Иван Тургенев",
     "bio": "Иван Сергеевич Тургенев (1818–1883) — русский писатель-реалист. Автор романа «Отцы и дети» и «Записок охотника»."},
    {"username": "anton_chekhov",      "email": "chekhov@classic.lib",
     "display_name": "Антон Чехов",
     "bio": "Антон Павлович Чехов (1860–1904) — русский писатель и драматург. Признан одним из величайших мастеров короткого рассказа в мировой литературе."},
    {"username": "mikhail_lermontov",  "email": "lermontov@classic.lib",
     "display_name": "Михаил Лермонтов",
     "bio": "Михаил Юрьевич Лермонтов (1814–1841) — русский поэт и прозаик. Автор «Героя нашего времени» — первого психологического романа в русской литературе."},
    {"username": "maxim_gorky",        "email": "gorky@classic.lib",
     "display_name": "Максим Горький",
     "bio": "Алексей Максимович Пешков (1868–1936), псевдоним Максим Горький — русский и советский писатель, основоположник социалистического реализма."},
    {"username": "valery_bryusov",     "email": "bryusov@classic.lib",
     "display_name": "Валерий Брюсов",
     "bio": "Валерий Яковлевич Брюсов (1873–1924) — русский поэт и прозаик, один из основоположников русского символизма. Автор исторического романа «Огненный ангел» и фантастических рассказов."},
    {"username": "alexander_herzen",   "email": "herzen@classic.lib",
     "display_name": "Александр Герцен",
     "bio": "Александр Иванович Герцен (1812–1870) — русский публицист, писатель и философ. Автор романа «Кто виноват?» и мемуаров «Былое и думы». Основатель Вольной русской типографии в Лондоне."},
]

ENGLISH_AUTHORS = [
    {"username": "lewis_carroll",      "email": "lewis_carroll@classic.lib",    "display_name": "Lewis Carroll",
     "bio": "Charles Lutwidge Dodgson (1832–1898), pen name Lewis Carroll. English author and mathematician. Best known for Alice's Adventures in Wonderland."},
    {"username": "jane_austen",        "email": "jane_austen@classic.lib",      "display_name": "Jane Austen",
     "bio": "Jane Austen (1775–1817). English novelist whose works critique the British landed gentry. Author of Pride and Prejudice, Emma, Sense and Sensibility."},
    {"username": "arthur_conan_doyle", "email": "conan_doyle@classic.lib",      "display_name": "Arthur Conan Doyle",
     "bio": "Sir Arthur Conan Doyle (1859–1930). British author and physician. Creator of Sherlock Holmes, one of the most famous fictional characters ever."},
    {"username": "bram_stoker",        "email": "bram_stoker@classic.lib",      "display_name": "Bram Stoker",
     "bio": "Abraham Stoker (1847–1912). Irish author of Dracula (1897), the quintessential vampire novel."},
    {"username": "hg_wells",           "email": "hg_wells@classic.lib",         "display_name": "H.G. Wells",
     "bio": "Herbert George Wells (1866–1946). English writer, father of science fiction. Author of The Time Machine, The War of the Worlds, The Invisible Man."},
    {"username": "rl_stevenson",       "email": "rl_stevenson@classic.lib",     "display_name": "Robert Louis Stevenson",
     "bio": "Robert Louis Stevenson (1850–1894). Scottish novelist. Author of Treasure Island, Kidnapped, and Strange Case of Dr Jekyll and Mr Hyde."},
    {"username": "mary_shelley",       "email": "mary_shelley@classic.lib",     "display_name": "Mary Shelley",
     "bio": "Mary Wollstonecraft Shelley (1797–1851). English novelist. Author of Frankenstein (1818), the first true science fiction novel."},
    {"username": "charles_dickens",    "email": "charles_dickens@classic.lib",  "display_name": "Charles Dickens",
     "bio": "Charles Dickens (1812–1870). Greatest Victorian novelist. Author of Oliver Twist, A Tale of Two Cities, Great Expectations, David Copperfield."},
    {"username": "oscar_wilde",        "email": "oscar_wilde@classic.lib",      "display_name": "Oscar Wilde",
     "bio": "Oscar Wilde (1854–1900). Irish poet and playwright. Best known for The Picture of Dorian Gray and his legendary wit."},
    {"username": "mark_twain",         "email": "mark_twain@classic.lib",       "display_name": "Mark Twain",
     "bio": "Samuel Langhorne Clemens (1835–1910). American writer and humorist. Author of The Adventures of Tom Sawyer and Huckleberry Finn."},
    {"username": "jules_verne",        "email": "jules_verne@classic.lib",      "display_name": "Jules Verne",
     "bio": "Jules Verne (1828–1905). French novelist and pioneer of science fiction. Author of 20,000 Leagues Under the Sea and Around the World in Eighty Days."},
    {"username": "charlotte_bronte",   "email": "charlotte_bronte@classic.lib", "display_name": "Charlotte Brontë",
     "bio": "Charlotte Brontë (1816–1855). English novelist, author of Jane Eyre. Her sisters Emily and Anne were also celebrated novelists."},
    {"username": "emily_bronte",       "email": "emily_bronte@classic.lib",     "display_name": "Emily Brontë",
     "bio": "Emily Brontë (1818–1848). English novelist and poet. Her only novel, Wuthering Heights (1847), is considered a masterpiece of English literature."},
    {"username": "lf_baum",            "email": "lf_baum@classic.lib",          "display_name": "L. Frank Baum",
     "bio": "Lyman Frank Baum (1856–1919). American author best known for The Wonderful Wizard of Oz and its thirteen sequels in the Land of Oz series."},
    {"username": "jack_london",        "email": "jack_london@classic.lib",      "display_name": "Jack London",
     "bio": "John Griffith London (1876–1916). American novelist. Author of The Call of the Wild, White Fang, and The Sea-Wolf."},
    {"username": "alexandre_dumas",    "email": "dumas@classic.lib",            "display_name": "Alexandre Dumas",
     "bio": "Alexandre Dumas (1802–1870). French writer. Author of The Three Musketeers and The Count of Monte Cristo."},
]

ALL_AUTHORS = RUSSIAN_AUTHORS + ENGLISH_AUTHORS

# ══════════════════════════════════════════════════════════════════════════════
# TAGS
# ══════════════════════════════════════════════════════════════════════════════

ALL_TAGS = {
    "Классика": "klassika", "Романтика": "romantika",
    "Приключение": "priklyuchenie", "Мистика": "mistika",
    "Психология": "psihologiya", "Семья": "semya",
    "Дружба": "druzhba", "Вампиры": "vampiry",
    "Исторический": "istoricheskiy", "Россия XIX век": "rossiya-xix",
    "Апокалипсис": "apokalipsis", "Космос": "kosmos",
    "Путешествие": "puteshestvie", "Выживание": "vyzhivanie",
    "Предательство": "predatelstvo", "Детектив": "detektiv",
    "Сатира": "satira", "Реализм": "realizm",
    "Символизм": "simvolizm", "Антиутопия": "antiutopiya",
    "Магия": "magiya", "Дети": "deti",
    "Война": "voyna", "Любовь": "lyubov",
    "Преступление": "prestuplenie", "Природа": "priroda",
    "Философия": "filosofiya", "Юмор": "yumor",
    "Трагедия": "tragediya", "Средневековье": "srednevekove",
    "Фэнтези": "fentezi", "Постапокалипсис": "postapokalipsis",
}

# ══════════════════════════════════════════════════════════════════════════════
# DATASET LOADER
# ══════════════════════════════════════════════════════════════════════════════
#
# Reads directly from archive.zip (bypasses Windows cp437 filename mangling).
# Falls back to extracted files on disk if zip not found.
# ─────────────────────────────────────────────────────────────────────────────

_ZIP_INDEX: dict | None = None   # normalized_title → ZipInfo
_ZIP_PATH:  str  | None = None


def _find_archive_zip() -> str | None:
    """Search several likely locations for archive.zip."""
    candidates = [
        os.path.join(_PROJECT_DIR, "data", "archive.zip"),
        os.path.join(_PROJECT_DIR, "archive.zip"),
        os.path.join(os.path.dirname(_PROJECT_DIR), "archive.zip"),
        os.path.join(os.path.dirname(_PROJECT_DIR), "data", "archive.zip"),
        # If user runs from inside the 'project' subdirectory
        os.path.join(os.path.dirname(_PROJECT_DIR), "project", "data", "archive.zip"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


def _zip_real_name(info) -> str:
    """Decode cp437-mangled UTF-8 Cyrillic filename stored in the zip."""
    try:
        # Zip created on Linux/Mac stores UTF-8 bytes but labels them as cp437
        return info.filename.encode('cp437').decode('utf-8')
    except Exception:
        return info.filename


def _normalize_title(s: str) -> str:
    """Lowercase + strip all spaces and punctuation for fuzzy matching."""
    s = s.lower()
    s = re.sub(r"[\s.\-\u2013\u2014\u2116#()\[\]\u00ab\u00bb'\"]+", '', s)
    return s


def _build_zip_index(zpath: str) -> dict:
    """Map {normalized_basename_without_ext → ZipInfo} for every .txt in the zip."""
    import zipfile as _zf
    index = {}
    with _zf.ZipFile(zpath) as z:
        for info in z.infolist():
            real = _zip_real_name(info)
            if not real.endswith('.txt'):
                continue
            base = os.path.splitext(os.path.basename(real))[0]
            key  = _normalize_title(base)
            if key and key not in index:
                index[key] = info
    return index


def _get_zip_index():
    global _ZIP_INDEX, _ZIP_PATH
    if _ZIP_INDEX is None:
        _ZIP_PATH = _find_archive_zip()
        if _ZIP_PATH:
            _ZIP_INDEX = _build_zip_index(_ZIP_PATH)
            print(f"   📦  Dataset index: {len(_ZIP_INDEX)} files  ({_ZIP_PATH})")
        else:
            _ZIP_INDEX = {}
            print("   ⚠️  archive.zip not found — will try filesystem only")
    return _ZIP_INDEX


def load_from_dataset(relative_path: str) -> str | None:
    """
    Load a text file from the Russian Literature dataset.
    relative_path example: 'prose/Tolstoy/Анна Каренина.txt'

    1. Read from archive.zip  (reliable, bypasses OS filename encoding)
    2. Walk filesystem        (fallback)
    """
    import zipfile as _zf

    base = os.path.splitext(os.path.basename(relative_path))[0]
    key  = _normalize_title(base)

    # ── 1. archive.zip ────────────────────────────────────────────────────
    idx = _get_zip_index()
    if key in idx and _ZIP_PATH:
        try:
            with _zf.ZipFile(_ZIP_PATH) as z:
                raw  = z.read(idx[key])
                text = raw.decode('utf-8', errors='replace')
                if len(text) > 500:
                    return text
        except Exception:
            pass

    # ── 2. Filesystem walk ─────────────────────────────────────────────────
    roots = [
        DATASET_DIR,
        os.path.join(_PROJECT_DIR, "data"),
        _PROJECT_DIR,
        os.path.join(_PROJECT_DIR, "project", "data", "ruslit"),
        os.path.join(_PROJECT_DIR, "project", "data"),
    ]
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, _, filenames in os.walk(root):
            for fname in filenames:
                if not fname.endswith('.txt'):
                    continue
                fname_key = _normalize_title(os.path.splitext(fname)[0])
                if fname_key == key:
                    try:
                        text = open(os.path.join(dirpath, fname),
                                    encoding='utf-8', errors='replace').read()
                        if len(text) > 500:
                            return text
                    except Exception:
                        pass
    return None
# ══════════════════════════════════════════════════════════════════════════════
# TEXT CLEANING
# ══════════════════════════════════════════════════════════════════════════════

def _extract_footnotes(text: str) -> tuple[str, dict]:
    """
    Extract the footnotes section from a dataset file and return:
    - text with footnote section removed
    - dict {footnote_number: footnote_text}
    """
    footnotes: dict[str, str] = {}

    # Find notes/Примечания section
    _NOTES_RE = re.compile(
        r'\n\s*(?:notes|Примечания|ПРИМЕЧАНИЯ|Комментарии|КОММЕНТАРИИ'
        r'|Приложение|Об авторе|ОБ АВТОРЕ)\s*\n',
        re.IGNORECASE
    )
    m = _NOTES_RE.search(text)
    if not m or m.start() < len(text) * 0.5:
        return text, footnotes

    notes_text = text[m.end():]
    text = text[:m.start()]

    # Parse individual footnotes: digit on its own line, then text
    # Format: \n1\n\nText of footnote...\n\n2\n\n...
    note_blocks = re.split(r'\n\s*(\d{1,4})\s*\n', notes_text)
    i = 0
    while i < len(note_blocks):
        chunk = note_blocks[i].strip()
        if chunk.isdigit() and i + 1 < len(note_blocks):
            fn_num = chunk
            fn_text = note_blocks[i + 1].strip()
            # Clean the footnote text
            fn_text = re.sub(r'\s+', ' ', fn_text).strip()
            if fn_text and len(fn_text) > 2:
                footnotes[fn_num] = fn_text
            i += 2
        else:
            i += 1

    return text, footnotes


def _embed_footnotes(text: str, footnotes: dict) -> str:
    """
    Replace [N] markers in text with {{fn:N:footnote text}} markers
    that the frontend can render as tooltips.
    """
    if not footnotes:
        # Just remove bare [N] markers
        text = re.sub(r'\[\d{1,4}\]', '', text)
        return text

    def replace_fn(m):
        n = m.group(1)
        if n in footnotes:
            # Escape any special chars in footnote text
            fn_safe = footnotes[n].replace('}}', ') ')
            return f'{{{{fn:{n}:{fn_safe}}}}}'
        return ''  # remove if no matching footnote

    text = re.sub(r'\[(\d{1,4})\]', replace_fn, text)
    return text


def clean_russian_text(text: str) -> str:
    """Fix encoding artifacts, HTML entities, typography in Russian dataset texts."""
    # ── 1. Control-char and cp1252 fixes ────────────────────────────────────
    _FIXES = {
        '\x85': '\u2026', '\x91': '\u2018', '\x92': '\u2019',
        '\x93': '\u201c', '\x94': '\u201d', '\x96': '\u2013', '\x97': '\u2014',
        '\xa0': ' ', '\xad': '', '\r': '',
    }
    for bad, good in _FIXES.items():
        text = text.replace(bad, good)

    # ── 2. Decode HTML numeric entities  &#224; → à  ────────────────────────
    def _decode_entity(m):
        try:
            return chr(int(m.group(1)))
        except (ValueError, OverflowError):
            return m.group(0)
    text = re.sub(r'&#(\d+);', _decode_entity, text)
    text = re.sub(r'&amp;#(\d+);', _decode_entity, text)
    text = (text
            .replace('&amp;', '&').replace('&lt;', '<')
            .replace('&gt;', '>').replace('&quot;', '"').replace('&apos;', "'"))

    # ── 3. Extract footnotes and embed as tooltip markers ────────────────────
    text, footnotes = _extract_footnotes(text)
    text = _embed_footnotes(text, footnotes)

    # ── 4. em-dash fixup ─────────────────────────────────────────────────────
    text = re.sub(r'(?<=[А-ЯЁа-яё\w])\s*--\s*', ' — ', text)
    text = re.sub(r'(?m)^-\s', '— ', text)

    # ── 5. Strip dataset header (author / title lines) ───────────────────────
    lines = text.splitlines()
    if (len(lines) > 5
            and lines[0].strip()
            and len(lines[0].strip()) < 80
            and not re.match(r'\s*(?:Глава|Часть|[IVXLCDM]+\s*$|\d+\s*$)', lines[0])):
        skip = 0
        for i in range(min(8, len(lines))):
            s = lines[i].strip()
            if len(s) > 100:
                skip = i; break
            if re.match(r'(?:Глава|Часть|Книга|[IVXLCDM]{1,5}\.?)\s', s):
                skip = i; break
        if 0 < skip <= 6:
            text = '\n'.join(lines[skip:])

    # ── 5b. Normalize whitespace-only lines ("pseudo-blanks") ───────────────
    # Some OCR files use lines of spaces (e.g. "  \n  \n") as paragraph
    # separators.  Strip trailing/leading spaces from lines that contain
    # nothing else so that \n{2,} splits work correctly.
    text = re.sub(r'(?m)^[ \t]+$', '', text)

    # ── 6. Handle indented paragraph format (old OCR / typewriter style) ───────
    # Detect: if ≥20 % of non-empty body lines start with a space → indented.
    # In this format new paragraphs are marked by a leading indent; continuation
    # lines of the same paragraph have no indent (word-wrap).
    # Fix: join continuation lines with a space, treat each indented start as a
    #      paragraph boundary.
    #
    # Multi-level indent support: some books use TWO indent depths, e.g.
    #   2-space lines  = continuation of the current paragraph
    #   7-space lines  = start of a new paragraph
    # We detect the largest gap between unique indent levels and use the level
    # just above that gap as the "new paragraph" threshold.  If no clear gap
    # exists (all gaps ≤ 2 spaces), we fall back to "any indent = new para".
    _all_lines = text.split('\n')
    _skip = min(5, len(_all_lines))
    _sample = [l for l in _all_lines[_skip: _skip + 300] if l.strip()]
    if _sample:
        _n_ind = sum(1 for l in _sample if l and l[0] == ' ' and len(l.strip()) > 3)
        if _n_ind / len(_sample) >= 0.20:
            # ── Determine paragraph-start indent threshold ──────────────────
            # Two distinct OCR/typewriter layouts exist:
            #
            # A) True continuation format (e.g. Республика Южного Креста):
            #      2-space lines  = continuation of current paragraph (word-wrap)
            #      7-space lines  = start of a new paragraph
            #    → continuation lines appear in RUNS (several in a row per paragraph)
            #    → each continuation line is SHORT (one word-wrapped fragment)
            #
            # B) One-line-per-paragraph format (e.g. Война и мир):
            #      4/5-space lines = each is one COMPLETE paragraph (never continues)
            #      10-space lines  = chapter headings / special content
            #    → the "lower-indent" lines do NOT appear in consecutive runs
            #    → each line is LONG (the entire paragraph on one line)
            #
            # We only activate the multi-level threshold when we see evidence of
            # layout A: the lower-indent lines form runs of 3+ consecutive lines
            # AND the LONGEST of those lines is ≤ 200 chars.  A word-wrapped
            # continuation line is always short; a one-sentence-per-line layout
            # will have some very long lines (600+ chars) even if short dialogue
            # lines pull the average down.
            _ind_lines = [l for l in _sample if l and l[0] == ' ' and len(l.strip()) > 3]
            _u_levels  = sorted(set(len(l) - len(l.lstrip()) for l in _ind_lines))
            _para_thr  = 1  # default: any indent = new paragraph
            if len(_u_levels) >= 2:
                _gaps = [(_u_levels[i + 1] - _u_levels[i], i)
                         for i in range(len(_u_levels) - 1)]
                _big_gap = max(_gaps, key=lambda x: x[0])
                if _big_gap[0] >= 3:  # candidate for multi-level
                    # Verify it's a true continuation format: look for runs of
                    # 3+ consecutive low-indent lines AND max line length ≤ 200.
                    _low_lvl  = _u_levels[_big_gap[1]]   # top level below gap
                    _max_run  = 0
                    _cur_run  = 0
                    _low_lens: list[int] = []
                    for _sl in _sample:
                        _sli = len(_sl) - len(_sl.lstrip())
                        if _sl and _sl[0] == ' ' and _sli <= _low_lvl and len(_sl.strip()) > 3:
                            _cur_run += 1
                            _low_lens.append(len(_sl.strip()))
                            if _cur_run > _max_run:
                                _max_run = _cur_run
                        else:
                            _cur_run = 0
                    if _max_run >= 3 and (max(_low_lens) if _low_lens else 0) <= 200:
                        _para_thr = _u_levels[_big_gap[1] + 1]

            # Split on pre-existing blank lines first, then handle indentation
            # within each section separately.
            _secs = re.split(r'\n{2,}', text)
            _rebuilt: list[str] = []
            for _sec in _secs:
                if not _sec.strip():
                    continue
                _paras: list[list[str]] = []
                _cur:   list[str]       = []
                for _line in _sec.split('\n'):
                    _s = _line.strip()
                    if not _s:
                        if _cur:
                            _paras.append(_cur); _cur = []
                        continue
                    _ind = len(_line) - len(_line.lstrip())
                    if _line[0] == ' ' and _ind >= _para_thr:
                        # Indent meets threshold → new paragraph
                        if _cur:
                            _paras.append(_cur)
                        _cur = [_s]
                    else:
                        # Below threshold → continuation (or unindented heading)
                        if _cur:
                            _cur.append(_s)
                        else:
                            _cur = [_s]
                if _cur:
                    _paras.append(_cur)
                _rebuilt.extend(' '.join(p) for p in _paras if p)
            text = '\n\n'.join(p for p in _rebuilt if p)

    # ── 7. Collapse multiple inline spaces (typewriter / OCR artefact) ──────
    text = re.sub(r'  +', ' ', text)

    # ── 8. Ensure proper paragraph separation ────────────────────────────────
    # OLD check ('\n\n' not in text[:2000]) fails when the *header* has double
    # newlines but the prose body uses only single newlines.
    # NEW: measure the \n\n / \n ratio in the actual body (skip first 300 chars
    # to exclude any header artefacts).  If the ratio is very low the file uses
    # single newlines for paragraph breaks → expand every lone \n to \n\n.
    _body = text[min(300, len(text) // 8):]
    _nn   = _body.count('\n\n')
    _n    = max(_body.count('\n'), 1)
    if _nn / _n < 0.08:
        text = re.sub(r'\n(?!\n)', '\n\n', text)

    text = re.sub(r'\n{4,}', '\n\n\n', text)
    return text.strip()


# ══════════════════════════════════════════════════════════════════════════════
# ENGLISH BOOKS — archive_eng.zip / books.db
# ══════════════════════════════════════════════════════════════════════════════

_ENG_DB_CONN: sqlite3.Connection | None = None
_ENG_DB_TMP:  str | None = None


def _ensure_eng_db() -> sqlite3.Connection | None:
    """Lazily extract books.db from archive_eng.zip and open a SQLite connection."""
    global _ENG_DB_CONN, _ENG_DB_TMP
    if _ENG_DB_CONN is not None:
        return _ENG_DB_CONN

    candidates = [
        os.path.join(_PROJECT_DIR, "data", "archive_eng.zip"),
        os.path.join(_PROJECT_DIR, "archive_eng.zip"),
        os.path.join(os.path.dirname(_PROJECT_DIR), "data", "archive_eng.zip"),
        os.path.join(os.path.dirname(_PROJECT_DIR), "archive_eng.zip"),
        # Absolute fallback for development
        r"C:\Users\User\PycharmProjects\final_4.1.4\data\archive_eng.zip",
    ]
    zip_path = next((p for p in candidates if os.path.isfile(p)), None)
    if not zip_path:
        print("   ⚠️  archive_eng.zip not found")
        return None

    fd, tmp = tempfile.mkstemp(suffix=".db", prefix="eng_books_")
    os.close(fd)
    with zipfile.ZipFile(zip_path) as z:
        with open(tmp, "wb") as f:
            f.write(z.read("books.db"))
    _ENG_DB_TMP = tmp
    _ENG_DB_CONN = sqlite3.connect(tmp, check_same_thread=False)
    print(f"   [EN DB] English books DB: {zip_path}")
    return _ENG_DB_CONN


def _nsort(s: str) -> list:
    """Natural sort key so 'Chapter-09' < 'Chapter-10'."""
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", s)]


def _chapter_db_name_to_title(raw: str) -> str:
    """
    Convert a chapter name from book_file.chapter to a human-readable title.
    Examples:
        'Chapter-03'       → 'Chapter 3'
        'Chap7'            → 'Chapter 7'
        'Part2-chapter09'  → 'Part 2, Chapter 9'
        'Aliceadventure07' → 'Chapter 7'
        'A Scandal In Bohemia' → 'A Scandal in Bohemia'
    """
    if not raw or raw.lower() in ("nan", "index", "addendum"):
        return ""
    m = re.match(r"^[Cc]hapter-?(\d+)$", raw)
    if m:
        return f"Chapter {int(m.group(1))}"
    m = re.match(r"^[Cc]hap(\d+)$", raw)
    if m:
        return f"Chapter {int(m.group(1))}"
    m = re.match(r"^[Pp]art(\d+)-?[Cc]hapter(\d+)$", raw)
    if m:
        return f"Part {int(m.group(1))}, Chapter {int(m.group(2))}"
    # BookNameNNN pattern  (e.g. "Aliceadventure07", "Chap1")
    m = re.match(r"^[A-Za-z]{3,}?(\d+)$", raw)
    if m:
        return f"Chapter {int(m.group(1))}"
    # Looks like a real title ("A Scandal In Bohemia", "His Last Bow")
    return re.sub(r"[-_]+", " ", raw).strip()


# Chapter names that indicate navigation/boilerplate pages to skip
_SKIP_CH_RE = re.compile(
    r"^(?:index|addendum|colophon|preface|toc|contents|cover|title"
    r"|frontispiece|introduction|appendix|foreword|dedication)\s*$",
    re.IGNORECASE,
)


_DECO_PARA_RE = re.compile(r"^[\s*\-_=~.<>|]{0,80}$")
_END_BOOK_RE  = re.compile(
    r"^\s*[-—.]*\s*(?:End\s+of\s+(?:the\s+)?(?:Project\s+Gutenberg|book|text)"
    r"|THE\s+END|FINIS|FOOTNOTES|NOTES|APPENDIX|BIBLIOGRAPHY|INDEX)"
    r"[\s\-—.]*$",
    re.IGNORECASE,
)


def _clean_eng_body(text: str) -> str:
    """
    Normalise English chapter body text shared by both HTML and TXT sources.

    Both formats from books.db have the same artefact: every physical line
    ends with \\n\\n because the original files were formatted with a blank
    line after each wrapped line.  Real paragraph boundaries are >= 4 newlines.

    Steps:
      1. Split on \\n{4,} to isolate paragraphs.
      2. Within each paragraph join wrapped lines with a single space.
      3. Drop decorative-only paragraphs (asterisks, dashes, etc.).
      4. Stop at end-of-book markers (THE END, FINIS, FOOTNOTES …).
      5. Rejoin with \\n\\n.
    """
    sections = re.split(r"\n{4,}", text)
    out: list[str] = []
    for sec in sections:
        lines = [l.strip() for l in re.split(r"\n+", sec)]
        lines = [l for l in lines if l]
        if not lines:
            continue
        para = re.sub(r" {2,}", " ", " ".join(lines)).strip()
        if not para or _DECO_PARA_RE.match(para):
            continue
        if _END_BOOK_RE.match(para):
            break
        out.append(para)
    # Strip end-of-book markers that got merged into the last paragraph
    if out:
        cleaned = re.sub(
            r"[\s.—\-]*(?:THE\s+END|FINIS|End|END\s+OF\s+(?:VOLUME|BOOK)\s*[IVX\d]*)[\s.—\-]*$",
            "", out[-1], flags=re.IGNORECASE,
        ).strip()
        if cleaned:
            out[-1] = cleaned
        else:
            out.pop()
    return "\n\n".join(out)


def _html_chapter_to_text(html: str) -> tuple[str, str]:
    """
    Convert one HTML chapter file to (title, plain_text).

    Extracts the chapter title from the first H1/H2/H3 tag.
    Removes navigation links, HEAD, ADDRESS blocks.
    Converts <P> to paragraph breaks, strips all remaining markup,
    decodes HTML entities, then applies _clean_eng_body().
    """
    # ── Extract chapter title ──────────────────────────────────────────────
    title = ""
    for tag in ("H1", "H2", "H3"):
        m = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", html, re.IGNORECASE | re.DOTALL)
        if m:
            raw_t = re.sub(r"<[^>]+>", "", m.group(1))
            raw_t = html_mod.unescape(raw_t)
            raw_t = re.sub(r"\s+", " ", raw_t).strip()
            if (3 < len(raw_t) < 200 and not re.match(
                    r"^(?:table\s*of\s*contents|index\b|previous\s*chapter|next\s*chapter)",
                    raw_t, re.IGNORECASE)):
                title = raw_t
                break

    # ── Remove boilerplate ─────────────────────────────────────────────────
    html = re.sub(r"<HEAD\b[^>]*>.*?</HEAD>", "", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<ADDRESS\b[^>]*>.*?</ADDRESS>", "", html, flags=re.IGNORECASE | re.DOTALL)
    # Navigation links (Previous/Next chapter, Table of Contents, root /)
    html = re.sub(
        r'<A\b[^>]*\bHREF\s*=\s*["\'][^"\']*(?:chap|index)[^"\']*["\'][^>]*>.*?</A>',
        "", html, flags=re.IGNORECASE | re.DOTALL,
    )
    html = re.sub(
        r'<A\b[^>]*\bHREF\s*=\s*["\'][/"#][^"\']*["\'][^>]*>.*?</A>',
        "", html, flags=re.IGNORECASE | re.DOTALL,
    )
    html = re.sub(
        r"\[(?:Previous|Next)\s+Chapter\]|\[Table\s+of\s+Contents\]",
        "", html, flags=re.IGNORECASE,
    )

    # ── Convert structural tags to paragraph separators ───────────────────
    html = re.sub(r"</?(?:P|DIV|SECTION|BLOCKQUOTE)\b[^>]*>", "\n\n\n\n",
                  html, flags=re.IGNORECASE)
    html = re.sub(r"<BR\s*/?>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"<HR\b[^>]*>", "\n\n\n\n", html, flags=re.IGNORECASE)
    html = re.sub(
        r"<(?:H[1-6]|CENTER)\b[^>]*>(.*?)</(?:H[1-6]|CENTER)>",
        r"\n\n\n\n\1\n\n\n\n", html, flags=re.IGNORECASE | re.DOTALL,
    )

    # ── Strip remaining tags, decode entities ─────────────────────────────
    html = re.sub(r"<[^>]+>", "", html)
    html = html_mod.unescape(html).replace("\xa0", " ")

    content = _clean_eng_body(html)

    # If the extracted title is duplicated as the first paragraph, remove it
    if title and content:
        paras = content.split("\n\n")
        first = paras[0].strip()
        if (first == title
                or re.match(r"^Chapter\s+[IVXLCDM\d]+\.?\s*$", first, re.IGNORECASE)):
            content = "\n\n".join(paras[1:])

    return title, content


def _txt_chapter_to_text(txt: str) -> tuple[str, str]:
    """
    Convert one plain-text chapter file to (title, plain_text).

    Looks for a 'CHAPTER N / subtitle' pattern at the top to extract
    the chapter title and skip the heading from the body content.
    """
    sections = re.split(r"\n{4,}", txt)
    non_empty = [
        (i, re.sub(r"\s+", " ", s).strip())
        for i, s in enumerate(sections) if s.strip()
    ]

    title = ""
    body_start = 0  # section index where body begins

    for j, (i, sec) in enumerate(non_empty[:10]):
        m_ch = re.match(
            r"^(?:CHAPTER|Chapter)\s+([IVXLCDM]+|\d+)(?:[.:—\s\-]+(.+))?$",
            sec, re.IGNORECASE,
        )
        if m_ch:
            ch_num = m_ch.group(1).strip()
            ch_sub = (m_ch.group(2) or "").strip()
            if not ch_sub and j + 1 < len(non_empty):
                # Next section might be the subtitle
                next_sec = non_empty[j + 1][1]
                if len(next_sec) < 150 and not re.search(r"\.\s+[A-Z]", next_sec):
                    title = next_sec
                    body_start = non_empty[j + 1][0] + 1
                else:
                    title = f"Chapter {ch_num}"
                    body_start = i + 1
            else:
                title = ch_sub or f"Chapter {ch_num}"
                body_start = i + 1
            break

    body_secs = sections[body_start:]
    out: list[str] = []
    for sec in body_secs:
        lines = [l.strip() for l in re.split(r"\n+", sec)]
        lines = [l for l in lines if l]
        if not lines:
            continue
        para = re.sub(r" {2,}", " ", " ".join(lines)).strip()
        if not para or _DECO_PARA_RE.match(para):
            continue
        if _END_BOOK_RE.match(para):
            break
        out.append(para)

    content = "\n\n".join(out)

    # If no title was found, skip the very first paragraph when it looks like
    # an OCR-style header (book title / author / year on one line, < 20 words)
    if not title and content:
        paras = content.split("\n\n")
        if paras and len(paras[0].split()) < 20:
            content = "\n\n".join(paras[1:])

    return title, content


_CH_TAIL_RE = re.compile(
    r"[ \t]*[-—]*[ \t]*(?:End|The\s+End|Finis|END\s+OF\s+(?:VOLUME|BOOK)\s*[IVX\d]*)[ \t]*[-—.]*\s*$",
    re.IGNORECASE,
)


def _trim_chapter_tail(chs: list[dict]) -> list[dict]:
    """Strip stray end-of-chapter markers from every chapter's last line."""
    for ch in chs:
        paras = ch["content"].split("\n\n")
        # Drop whole paragraphs that are just an end marker
        while paras:
            p = paras[-1].strip()
            if _END_BOOK_RE.match(p) or re.fullmatch(
                r"[-—.* ]*(?:End|The\s+End|Finis)[-—.* ]*", p, re.IGNORECASE
            ):
                paras.pop()
            else:
                # Strip end marker that got merged into the last sentence
                paras[-1] = _CH_TAIL_RE.sub("", paras[-1]).strip()
                break
        if paras:
            ch["content"] = "\n\n".join(paras)
            ch["words_count"] = len(ch["content"].split())
    return chs


def load_english_book(book_id: int, max_ch: int = 25) -> list[dict] | None:
    """
    Load and clean English book chapters from books.db (inside archive_eng.zip).

    If the book is stored as a single file (chapter='Nan'), the text is cleaned
    and split via parse_chapters().  Otherwise each DB row is one chapter.

    Returns a list of {number, title, content, words_count} dicts, or None.
    """
    conn = _ensure_eng_db()
    if conn is None:
        return None

    cur = conn.cursor()
    cur.execute(
        """SELECT bf."index", bf.chapter, tf.fmt, tf.text
           FROM book_file bf
           JOIN text_files tf ON tf."index" = bf.file_id
           WHERE bf.book_id = ?""",
        (book_id,),
    )
    rows = cur.fetchall()
    if not rows:
        return None

    # ── Single-file book (chapter='Nan') ──────────────────────────────────
    unique_ch = {r[1] for r in rows}
    if unique_ch == {"Nan"}:
        _, _, fmt, text = rows[0]
        if fmt in ("html", "htm"):
            _, body = _html_chapter_to_text(text)
        else:
            _, body = _txt_chapter_to_text(text)
        if not body or len(body) < 1000:
            return None
        # Drop short book-title / author header paragraphs at the very top
        paras = body.split("\n\n")
        while paras and len(paras[0].split()) < 10:
            paras.pop(0)
        body = "\n\n".join(paras)
        return _trim_chapter_tail(
            parse_chapters(body, is_russian=False, max_ch=max_ch, min_words=300)
        )

    # ── Multi-chapter book ────────────────────────────────────────────────
    rows_sorted = sorted(rows, key=lambda r: _nsort(r[1]))

    result: list[dict] = []
    seen: set[str] = set()

    for _idx, ch_name, fmt, text in rows_sorted:
        # Skip navigation/boilerplate pages
        if _SKIP_CH_RE.match(ch_name.strip()):
            continue
        if len(text.strip()) < 500:
            continue

        if fmt in ("html", "htm"):
            title, content = _html_chapter_to_text(text)
        else:
            title, content = _txt_chapter_to_text(text)

        # Fall back to DB chapter name if no title extracted from content
        if not title:
            title = _chapter_db_name_to_title(ch_name)

        if not content or len(content.split()) < 100:
            continue

        # Dedup by normalised title slug
        slug = re.sub(r"\W+", "", title.lower())[:40]
        if slug in seen:
            continue
        seen.add(slug)

        num = len(result) + 1
        result.append({
            "number": num,
            "title": title[:295],
            "content": content,
            "words_count": len(content.split()),
        })
        if len(result) >= max_ch:
            break

    return _trim_chapter_tail(result) or None


# ══════════════════════════════════════════════════════════════════════════════
# CHAPTER PARSING
# ══════════════════════════════════════════════════════════════════════════════

_RU_ORDINALS = {
    'первая':1,'первый':1,'первое':1,'вторая':2,'второй':2,'второе':2,
    'третья':3,'третий':3,'третье':3,'четвёртая':4,'четвертая':4,
    'четвёртый':4,'пятая':5,'пятый':5,'шестая':6,'шестой':6,
    'седьмая':7,'седьмой':7,'восьмая':8,'восьмой':8,'девятая':9,'девятый':9,
    'десятая':10,'десятый':10,'одиннадцатая':11,'двенадцатая':12,
    'тринадцатая':13,'четырнадцатая':14,'пятнадцатая':15,
    'шестнадцатая':16,'семнадцатая':17,'восемнадцатая':18,
    'девятнадцатая':19,'двадцатая':20,
}


def roman_to_int(s: str) -> int:
    v = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    s = s.upper().strip()
    total = prev = 0
    for ch in reversed(s):
        n = v.get(ch, 0)
        total += n if n >= prev else -n
        prev = n
    return total


def num_str_to_int(s: str) -> int:
    s = s.strip().lower()
    if s.isdigit(): return int(s)
    if re.fullmatch(r'[ivxlcdm]+', s, re.IGNORECASE):
        v = roman_to_int(s)
        if v: return v
    return _RU_ORDINALS.get(s, 0)


EN_CHAPTER_PATTERNS = [
    # "  CHAPTER I", "Chapter 12", "Chapter ONE  — optional same-line title"
    r'(?m)^\s*(?:CHAPTER|Chapter)\s+([IVXLCDM]+|\d+)(?:[ \t.:—-]+([^\n]+?))?[ \t]*$',
    # Bare roman numeral on its own line: "  IV  " or "  IV."
    r'(?m)^\s*([IVXLCDM]{2,})\.?[ \t]*$',
]
RU_CHAPTER_PATTERNS = [
    # "Глава первая", "ГЛАВА I", "Глава 5. Заголовок" — title only on same line
    r'(?m)^\s*(?:ГЛАВА|Глава)\s+([IVXLCDM]+|\d+|[а-яёА-ЯЁ][а-яёА-ЯЁ]+)(?:[ \t.:—-]+([^\n]+?))?[ \t]*$',
    # "Часть первая", "Книга вторая", "Раздел I"
    r'(?m)^\s*(?:ЧАСТЬ|Часть|КНИГА|Книга|РАЗДЕЛ|Раздел)\s+([IVXLCDM]+|\d+|[а-яёА-ЯЁ][а-яёА-ЯЁ]+)(?:[ \t.:—-]+([^\n]+?))?[ \t]*$',
    # Bare roman numeral: "   III   " or "  V."
    r'(?m)^\s*([IVXLCDM]{1,6})\.?[ \t]*$',
    # Bare arabic numeral: "   12   " or "  7."
    r'(?m)^\s*(\d{1,3})\.?[ \t]*$',
    # "* 5 *" style
    r'(?m)^\s*\*\s*(\d+)\s*\*[ \t]*$',
]


def parse_chapters(text: str, is_russian: bool = False,
                   max_ch: int = 25, min_words: int = 200) -> list[dict]:
    """
    Split text into chapters.
    Strategy:
    1. Try all heading patterns.
    2. Filter consecutive matches that are TOC entries (< 50 words between them).
    3. Pick the pattern that finds the most valid chapters with avg >= min_avg_words.
    4. After splitting: remove sub-chapter roman numerals from content.
    5. Fall back to equal-size chunks if no pattern qualifies.
    """
    patterns = RU_CHAPTER_PATTERNS if is_russian else EN_CHAPTER_PATTERNS
    # Words between two consecutive chapter headings below this = TOC entry, skip it
    toc_threshold = 50  # very tight — only removes true TOC lines (< 1 paragraph)

    def filter_toc(ms: list) -> list:
        """Remove matches that are clearly TOC entries (< toc_threshold words after)."""
        if len(ms) < 2:
            return ms
        result = []
        for i, m in enumerate(ms):
            nxt = ms[i + 1].start() if i + 1 < len(ms) else len(text)
            words_after = len(text[m.end():nxt].split())
            if words_after >= toc_threshold:
                result.append(m)
        # Safeguard: if we filtered too aggressively, return original
        return result if len(result) >= 2 else ms

    def avg_words_between(ms: list) -> float:
        if len(ms) < 2:
            return 0.0
        counts = [len(text[ms[i].end():ms[i + 1].start()].split())
                  for i in range(len(ms) - 1)]
        return sum(counts) / len(counts) if counts else 0.0

    best: list = []
    best_score: float = 0.0
    # Minimum average words per chapter — Russian chapters are longer
    min_avg_words = 200 if is_russian else 100

    for pat in patterns:
        try:
            ms = list(re.finditer(pat, text, re.MULTILINE))
        except re.error:
            continue
        if len(ms) < 2:
            continue
        ms_real = filter_toc(ms)
        if len(ms_real) < 2:
            continue
        avg = avg_words_between(ms_real)
        # Prefer the pattern with most chapters AND adequate average word count
        score = len(ms_real) if avg >= min_avg_words else 0
        if score > 0 and (score > best_score or (score == best_score and avg > avg_words_between(best))):
            best = ms_real
            best_score = score

    if len(best) < 2:
        return _chunk(text, max_ch, min_words, is_russian)

    # Build chapter list — always renumber 1, 2, 3...
    result = []
    for i, m in enumerate(best):
        start = m.end()
        end = best[i + 1].start() if i + 1 < len(best) else len(text)
        raw_content = text[start:end].strip()

        # Remove sub-chapter roman numerals standing alone on a line
        raw_content = re.sub(r'(?m)^\s*[IVXLCDM]{1,6}\.?\s*$\n?', '', raw_content)
        # Ensure proper paragraph spacing.
        # Use body-ratio check (same logic as clean_russian_text) so that chapters
        # whose internal text uses single \n for paragraph breaks are also fixed —
        # even when the surrounding text has \n\n around headings (which would fool
        # the old '\n\n' not in raw_content[:1000] check).
        _ch_body = raw_content[min(50, len(raw_content) // 8):]
        _ch_nn   = _ch_body.count('\n\n')
        _ch_n    = max(_ch_body.count('\n'), 1)
        if _ch_nn / _ch_n < 0.08:
            raw_content = re.sub(r'\n(?!\n)', '\n\n', raw_content)
        raw_content = re.sub(r'\n{4,}', '\n\n\n', raw_content).strip()

        words = len(raw_content.split())
        if words < min_words:
            continue

        seq_num = len(result) + 1
        gs = m.groups()
        title_s = (gs[1] or '').strip() if len(gs) > 1 else ''
        if re.fullmatch(r'[IVXLCDM]{1,6}\.?|\d{1,3}', title_s, re.IGNORECASE):
            title_s = ''
        label = f"Глава {seq_num}" if is_russian else f"Chapter {seq_num}"
        if title_s:
            label = f"{label}. {title_s}"
        label = label[:295]
        result.append({"number": seq_num, "title": label, "content": raw_content,
                       "words_count": words})
        if len(result) >= max_ch:
            break

    return result


def _chunk(text: str, max_chunks: int, min_words: int, is_russian: bool) -> list[dict]:
    """
    Split text into roughly equal parts, grouping at paragraph boundaries so that
    \n\n paragraph structure is preserved inside every chunk.

    The old word-split approach did text.split() which collapsed all whitespace,
    destroying every paragraph break.  This version accumulates whole paragraphs
    until the target word count is reached, then starts a new chunk.
    """
    paras = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
    if not paras:
        return []

    # Skip short metadata paragraphs at the very start (author name, subtitle,
    # chapter title lines) that slipped through header stripping.  Only drop
    # them when the first "real" prose paragraph is within the first 5 entries
    # and the preceding entries are clearly short (< 50 words each).
    _first_long = next((i for i, p in enumerate(paras) if len(p.split()) >= 50),
                       len(paras))
    if 0 < _first_long <= 5:
        paras = paras[_first_long:]
    if not paras:
        return []

    total_words  = sum(len(p.split()) for p in paras)
    target_words = max(min_words * 2, total_words // max_chunks)

    result:  list[dict] = []
    bucket:  list[str]  = []
    bucket_w = 0

    for para in paras:
        w = len(para.split())
        bucket.append(para)
        bucket_w += w
        # Flush when target reached and we still have room for more chunks
        if bucket_w >= target_words and len(result) < max_chunks - 1:
            content = '\n\n'.join(bucket)
            wc      = len(content.split())
            if wc >= min_words:
                num   = len(result) + 1
                label = f"Часть {num}" if is_russian else f"Part {num}"
                result.append({"number": num, "title": label[:295],
                               "content": content, "words_count": wc})
            bucket   = []
            bucket_w = 0

    # Remaining paragraphs → last chunk
    if bucket:
        content = '\n\n'.join(bucket)
        wc      = len(content.split())
        if wc >= min_words:
            num   = len(result) + 1
            label = f"Часть {num}" if is_russian else f"Part {num}"
            result.append({"number": num, "title": label[:295],
                           "content": content, "words_count": wc})

    return result[:max_chunks]


def make_slug(title: str) -> str:
    slug = re.sub(r'[^\w\s-]', '', title.lower())
    slug = re.sub(r'[\s_]+', '-', slug)
    return re.sub(r'-+', '-', slug).strip('-')[:200] or 'book'


# ══════════════════════════════════════════════════════════════════════════════
# BOOK CATALOGUE
# source: "dataset" → read from local ruslit dataset (Russian)
# source: "gutenberg" → download from Project Gutenberg (English)
# ══════════════════════════════════════════════════════════════════════════════

BOOKS = [

    # ══════════════════════════════════════════════════════════════
    # RUSSIAN BOOKS — Kaggle «Russian Literature» dataset
    # ══════════════════════════════════════════════════════════════

    # ── Толстой ───────────────────────────────────────────────────
    {"source":"dataset","dataset_path":"prose/Tolstoy/Анна Каренина.txt","is_russian":True,
     "title":"Анна Каренина","author_username":"leo_tolstoy",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Трагическая история Анны Карениной, полюбившей офицера Вронского, переплетается с нравственными исканиями Лёвина. Один из величайших романов мировой литературы о любви, браке и нравственном законе.",
     "cover_emoji":"🌹","is_adult":False,"is_featured":True,
     "tags":["Классика","Романтика","Трагедия","Россия XIX век","Любовь"],"views_count":198000,"likes_count":16400,"rating":4.90},

    {"source":"dataset","dataset_path":"prose/Tolstoy/Война и мир. Том 1.txt","is_russian":True,
     "title":"Война и мир. Том 1","author_username":"leo_tolstoy",
     "genre":Genre.HISTORICAL,"status":BookStatus.COMPLETED,
     "description":"Первый том грандиозной эпопеи: 1805 год, светские салоны Петербурга, Аустерлицкое сражение. Юный Пьер Безухов и Андрей Болконский ищут своё место в жизни на фоне наполеоновских войн.",
     "cover_emoji":"⚔️","is_adult":False,"is_featured":True,
     "tags":["Классика","Исторический","Война","Россия XIX век"],"views_count":167000,"likes_count":13800,"rating":4.92},

    {"source":"dataset","dataset_path":"prose/Tolstoy/Война и мир. Том 2.txt","is_russian":True,
     "title":"Война и мир. Том 2","author_username":"leo_tolstoy",
     "genre":Genre.HISTORICAL,"status":BookStatus.COMPLETED,
     "description":"1806–1812 годы. Мирная жизнь чередуется с войной. Наташа Ростова выходит в свет. Андрей Болконский переживает потери и возрождение. Пьер ищет смысл в масонстве.",
     "cover_emoji":"🕊️","is_adult":False,"is_featured":False,
     "tags":["Классика","Исторический","Война","Романтика","Россия XIX век"],"views_count":148000,"likes_count":12200,"rating":4.90},

    {"source":"dataset","dataset_path":"prose/Tolstoy/Война и мир. Том 3.txt","is_russian":True,
     "title":"Война и мир. Том 3","author_username":"leo_tolstoy",
     "genre":Genre.HISTORICAL,"status":BookStatus.COMPLETED,
     "description":"1812 год. Вторжение Наполеона, Бородинское сражение, пожар Москвы. Судьбы главных героев в огне Отечественной войны. Кульминация великой эпопеи.",
     "cover_emoji":"🔥","is_adult":False,"is_featured":False,
     "tags":["Классика","Исторический","Война","Трагедия","Россия XIX век"],"views_count":154000,"likes_count":12800,"rating":4.91},

    {"source":"dataset","dataset_path":"prose/Tolstoy/Война и мир. Том 4.txt","is_russian":True,
     "title":"Война и мир. Том 4","author_username":"leo_tolstoy",
     "genre":Genre.HISTORICAL,"status":BookStatus.COMPLETED,
     "description":"Финал эпопеи: изгнание Наполеона, развязка судеб всех героев, эпилог с философскими рассуждениями об истории и свободе воли.",
     "cover_emoji":"🌅","is_adult":False,"is_featured":False,
     "tags":["Классика","Исторический","Война","Россия XIX век","Философия"],"views_count":139000,"likes_count":11400,"rating":4.89},

    {"source":"dataset","dataset_path":"prose/Tolstoy/Воскресение.txt","is_russian":True,
     "title":"Воскресение","author_username":"leo_tolstoy",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Князь Нехлюдов узнаёт среди подсудимых девушку, которую соблазнил в юности, и отправляется за ней в Сибирь. Последний великий роман Толстого об искуплении и несправедливости закона.",
     "cover_emoji":"🕊️","is_adult":False,"is_featured":False,
     "tags":["Классика","Реализм","Философия","Россия XIX век"],"views_count":84000,"likes_count":6700,"rating":4.77},

    {"source":"dataset","dataset_path":"prose/Tolstoy/Детство.txt","is_russian":True,
     "title":"Детство","author_username":"leo_tolstoy",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Первое произведение Толстого. Десятилетний Николенька Иртеньев прощается с детством, покидая родовое гнездо. Начало великой автобиографической трилогии.",
     "cover_emoji":"📚","is_adult":False,"is_featured":False,
     "tags":["Классика","Реализм","Семья","Россия XIX век"],"views_count":72000,"likes_count":5800,"rating":4.68},

    {"source":"dataset","dataset_path":"prose/Tolstoy/Отрочество.txt","is_russian":True,
     "title":"Отрочество","author_username":"leo_tolstoy",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Вторая часть трилогии. Николенька взрослеет, переезжает в Москву и впервые сталкивается с социальным неравенством и жестокостью мира.",
     "cover_emoji":"📖","is_adult":False,"is_featured":False,
     "tags":["Классика","Реализм","Семья","Россия XIX век"],"views_count":58000,"likes_count":4500,"rating":4.62},

    {"source":"dataset","dataset_path":"prose/Tolstoy/Юность.txt","is_russian":True,
     "title":"Юность","author_username":"leo_tolstoy",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Завершающая часть трилогии. Николенька поступает в университет, мечтает о нравственном совершенстве и открывает мир взрослых со всеми его противоречиями.",
     "cover_emoji":"🌱","is_adult":False,"is_featured":False,
     "tags":["Классика","Реализм","Семья","Россия XIX век"],"views_count":61000,"likes_count":4900,"rating":4.65},

    {"source":"dataset","dataset_path":"prose/Tolstoy/Смерть Ивана Ильича.txt","is_russian":True,
     "title":"Смерть Ивана Ильича","author_username":"leo_tolstoy",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Чиновник Иван Ильич, прожив «правильную» жизнь, смертельно заболевает и впервые задаётся вопросом: правильно ли он жил? Одна из сильнейших повестей о смысле существования.",
     "cover_emoji":"⚖️","is_adult":False,"is_featured":False,
     "tags":["Классика","Философия","Трагедия","Россия XIX век"],"views_count":89000,"likes_count":7200,"rating":4.82},

    {"source":"dataset","dataset_path":"prose/Tolstoy/Крейцерова соната.txt","is_russian":True,
     "title":"Крейцерова соната","author_username":"leo_tolstoy",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"В ночном поезде пассажир исповедуется: он убил жену из ревности. Беспощадная повесть о браке и страсти, запрещённая цензурой при жизни автора.",
     "cover_emoji":"🎻","is_adult":True,"is_featured":False,
     "tags":["Классика","Трагедия","Психология","Россия XIX век"],"views_count":76000,"likes_count":6100,"rating":4.74},

    {"source":"dataset","dataset_path":"prose/Tolstoy/Казаки.txt","is_russian":True,
     "title":"Казаки","author_username":"leo_tolstoy",
     "genre":Genre.ADVENTURE,"status":BookStatus.COMPLETED,
     "description":"Молодой московский аристократ Оленин уезжает на Кавказ и попадает в станицу вольных казаков. Повесть о столкновении цивилизованного и природного человека.",
     "cover_emoji":"🏔️","is_adult":False,"is_featured":False,
     "tags":["Классика","Исторический","Война","Природа","Россия XIX век"],"views_count":72000,"likes_count":5800,"rating":4.77},

    {"source":"dataset","dataset_path":"prose/Tolstoy/Хаджи-Мурат.txt","is_russian":True,
     "title":"Хаджи-Мурат","author_username":"leo_tolstoy",
     "genre":Genre.HISTORICAL,"status":BookStatus.COMPLETED,
     "description":"Легендарный чеченский воин Хаджи-Мурат переходит на сторону русских, надеясь спасти семью. Суровая повесть о достоинстве, свободе и гибели непокорного духа.",
     "cover_emoji":"⚔️","is_adult":True,"is_featured":False,
     "tags":["Классика","Исторический","Война","Россия XIX век","Трагедия"],"views_count":86000,"likes_count":7000,"rating":4.85},

    {"source":"dataset","dataset_path":"prose/Tolstoy/Семейное счастье.txt","is_russian":True,
     "title":"Семейное счастье","author_username":"leo_tolstoy",
     "genre":Genre.ROMANCE,"status":BookStatus.COMPLETED,
     "description":"История любви молодой помещицы и пожилого соседа от пылкого романтизма до спокойного семейного счастья. Ранняя повесть Толстого о природе любви и брака.",
     "cover_emoji":"🏡","is_adult":False,"is_featured":False,
     "tags":["Классика","Романтика","Семья","Россия XIX век","Любовь"],"views_count":54000,"likes_count":4300,"rating":4.70},

    {"source":"dataset","dataset_path":"prose/Tolstoy/Отец Сергий.txt","is_russian":True,
     "title":"Отец Сергий","author_username":"leo_tolstoy",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Блестящий гвардейский офицер Касатский уходит в монастырь, став отцом Сергием. Но слава праведника оборачивается новым искушением. Повесть о гордыне, смирении и поиске Бога.",
     "cover_emoji":"✝️","is_adult":False,"is_featured":False,
     "tags":["Классика","Философия","Психология","Россия XIX век"],"views_count":67000,"likes_count":5400,"rating":4.78},

    # ── Достоевский ───────────────────────────────────────────────
    {"source":"dataset","dataset_path":"prose/Dostoevsky/Братья Карамазовы.txt","is_russian":True,
     "title":"Братья Карамазовы","author_username":"fyodor_dostoevsky",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Три брата связаны убийством отца. Последний роман Достоевского — грандиозная сумма его мировоззрения, трактат о Боге, свободе и братской любви.",
     "cover_emoji":"✝️","is_adult":True,"is_featured":True,
     "tags":["Классика","Философия","Преступление","Россия XIX век"],"views_count":156000,"likes_count":12800,"rating":4.92},

    {"source":"dataset","dataset_path":"prose/Dostoevsky/Идиот.txt","is_russian":True,
     "title":"Идиот","author_username":"fyodor_dostoevsky",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Князь Мышкин — «положительно прекрасный человек» — возвращается в петербургское общество и своей добротой разрушает судьбы окружающих. Роман о невозможности идеала в падшем мире.",
     "cover_emoji":"😇","is_adult":False,"is_featured":True,
     "tags":["Классика","Психология","Трагедия","Россия XIX век","Философия"],"views_count":142000,"likes_count":11500,"rating":4.88},

    {"source":"dataset","dataset_path":"prose/Dostoevsky/Бесы.txt","is_russian":True,
     "title":"Бесы","author_username":"fyodor_dostoevsky",
     "genre":Genre.THRILLER,"status":BookStatus.COMPLETED,
     "description":"Группа революционеров-нигилистов совершает террористическое убийство. Жёсткий роман-пророчество о разрушительной силе безбожного радикализма.",
     "cover_emoji":"🔥","is_adult":True,"is_featured":False,
     "tags":["Классика","Психология","Преступление","Россия XIX век","Философия"],"views_count":108000,"likes_count":8900,"rating":4.83},

    {"source":"dataset","dataset_path":"prose/Dostoevsky/Бедные люди.txt","is_russian":True,
     "title":"Бедные люди","author_username":"fyodor_dostoevsky",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Переписка мелкого чиновника Макара Девушкина и бедной девушки Вареньки. Дебютный роман Достоевского — первый голос «маленького человека» в русской литературе.",
     "cover_emoji":"✉️","is_adult":False,"is_featured":False,
     "tags":["Классика","Реализм","Россия XIX век","Трагедия"],"views_count":68000,"likes_count":5400,"rating":4.65},

    {"source":"dataset","dataset_path":"prose/Dostoevsky/Белые ночи.txt","is_russian":True,
     "title":"Белые ночи","author_username":"fyodor_dostoevsky",
     "genre":Genre.ROMANCE,"status":BookStatus.COMPLETED,
     "description":"Мечтатель встречает в петербургские белые ночи Настеньку и четыре ночи подряд беседует с ней о жизни и любви. Трогательная повесть об одиночестве и несбыточных надеждах.",
     "cover_emoji":"🌙","is_adult":False,"is_featured":False,
     "tags":["Классика","Романтика","Россия XIX век","Трагедия","Любовь"],"views_count":112000,"likes_count":9400,"rating":4.87},

    {"source":"dataset","dataset_path":"prose/Dostoevsky/Игрок.txt","is_russian":True,
     "title":"Игрок","author_username":"fyodor_dostoevsky",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Молодой учитель теряет голову от рулетки и от красавицы Полины. Роман об азарте и страсти, продиктованный за 26 дней — иначе права отошли бы издателю.",
     "cover_emoji":"🎲","is_adult":False,"is_featured":False,
     "tags":["Классика","Психология","Трагедия","Россия XIX век"],"views_count":72000,"likes_count":5700,"rating":4.69},

    {"source":"dataset","dataset_path":"prose/Dostoevsky/Записки из подполья.txt","is_russian":True,
     "title":"Записки из подполья","author_username":"fyodor_dostoevsky",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Исповедь озлобленного «человека из подполья» — первый образец антигероя в мировой литературе. Достоевский разбивает просветительскую веру в разумного человека.",
     "cover_emoji":"🕳️","is_adult":False,"is_featured":False,
     "tags":["Классика","Психология","Философия","Россия XIX век"],"views_count":82000,"likes_count":6600,"rating":4.80},

    {"source":"dataset","dataset_path":"prose/Dostoevsky/Вечный муж.txt","is_russian":True,
     "title":"Вечный муж","author_username":"fyodor_dostoevsky",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Чиновник Трусоцкий приходит к бывшему другу-сопернику после смерти жены. Психологическая дуэль двух мужчин — исследование ревности, унижения и странной взаимозависимости.",
     "cover_emoji":"🎩","is_adult":False,"is_featured":False,
     "tags":["Классика","Психология","Россия XIX век","Трагедия"],"views_count":64000,"likes_count":5100,"rating":4.72},

    {"source":"dataset","dataset_path":"prose/Dostoevsky/Двойник.txt","is_russian":True,
     "title":"Двойник","author_username":"fyodor_dostoevsky",
     "genre":Genre.MYSTERY,"status":BookStatus.COMPLETED,
     "description":"Чиновник Голядкин встречает своего двойника — точную копию, захватывающую его место в жизни. Ранняя повесть Достоевского о раздвоении личности и безумии.",
     "cover_emoji":"👤","is_adult":False,"is_featured":False,
     "tags":["Классика","Мистика","Психология","Россия XIX век"],"views_count":58000,"likes_count":4600,"rating":4.66},

    {"source":"dataset","dataset_path":"prose/Dostoevsky/Подросток.txt","is_russian":True,
     "title":"Подросток","author_username":"fyodor_dostoevsky",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Двадцатилетний незаконнорождённый Аркадий Долгорукий ищет своё место в жизни и отца. Один из самых личных и недооценённых романов Достоевского.",
     "cover_emoji":"🧑","is_adult":False,"is_featured":False,
     "tags":["Классика","Психология","Семья","Россия XIX век"],"views_count":68000,"likes_count":5400,"rating":4.72},

    {"source":"dataset","dataset_path":"prose/Dostoevsky/Неточка Незванова.txt","is_russian":True,
     "title":"Неточка Незванова","author_username":"fyodor_dostoevsky",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Незаконченный роман о девочке-сироте из петербургских трущоб. История взросления, любви и страдания — Достоевский в лучшей лирической форме.",
     "cover_emoji":"🎻","is_adult":False,"is_featured":False,
     "tags":["Классика","Реализм","Семья","Россия XIX век","Трагедия"],"views_count":52000,"likes_count":4100,"rating":4.67},

    {"source":"dataset","dataset_path":"prose/Dostoevsky/Униженные и оскорблённые.txt","is_russian":True,
     "title":"Унижённые и оскорблённые","author_username":"fyodor_dostoevsky",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Молодой писатель наблюдает жизнь петербургских «маленьких людей» — сироты Нелли, несчастного Ихменева и его дочери Наташи. Роман о страдании и жертвенности.",
     "cover_emoji":"💔","is_adult":False,"is_featured":False,
     "tags":["Классика","Реализм","Россия XIX век","Трагедия","Психология"],"views_count":78000,"likes_count":6200,"rating":4.74},

    {"source":"dataset","dataset_path":"prose/Dostoevsky/Дядюшкин сон.txt","is_russian":True,
     "title":"Дядюшкин сон","author_username":"fyodor_dostoevsky",
     "genre":Genre.COMEDY,"status":BookStatus.COMPLETED,
     "description":"Провинциальная дама устраивает брак своей дочери со старым сенильным князем. Сатирическая комедия нравов, полная гоголевского гротеска.",
     "cover_emoji":"😴","is_adult":False,"is_featured":False,
     "tags":["Классика","Юмор","Сатира","Россия XIX век"],"views_count":44000,"likes_count":3500,"rating":4.61},

    {"source":"dataset","dataset_path":"prose/Dostoevsky/Село Степанчиково и его обитатели.txt","is_russian":True,
     "title":"Село Степанчиково и его обитатели","author_username":"fyodor_dostoevsky",
     "genre":Genre.COMEDY,"status":BookStatus.COMPLETED,
     "description":"Бывший приживальщик Фома Опискин захватил власть над помещичьим домом и его обитателями. Злая комедия о лицемерии, тирании и человеческой глупости.",
     "cover_emoji":"🏠","is_adult":False,"is_featured":False,
     "tags":["Классика","Юмор","Сатира","Психология","Россия XIX век"],"views_count":48000,"likes_count":3800,"rating":4.65},

    # ── Пушкин ────────────────────────────────────────────────────
    {"source":"dataset","dataset_path":"prose/Pushkin/Капитанская дочка.txt","is_russian":True,
     "title":"Капитанская дочка","author_username":"alexander_pushkin",
     "genre":Genre.HISTORICAL,"status":BookStatus.COMPLETED,
     "description":"На фоне Пугачёвского восстания — история молодого офицера Гринёва и его любви к Маше Мироновой. Исторический роман о чести, долге и милосердии.",
     "cover_emoji":"⚔️","is_adult":False,"is_featured":True,
     "tags":["Классика","Исторический","Романтика","Россия XIX век","Война"],"views_count":118000,"likes_count":9600,"rating":4.82},

    {"source":"dataset","dataset_path":"prose/Pushkin/Пиковая дама.txt","is_russian":True,
     "title":"Пиковая дама","author_username":"alexander_pushkin",
     "genre":Genre.MYSTERY,"status":BookStatus.COMPLETED,
     "description":"Офицер Германн одержим тайной трёх карт, обеспечивающих выигрыш. Мистическая повесть о роке, страсти и безумии.",
     "cover_emoji":"🃏","is_adult":False,"is_featured":False,
     "tags":["Классика","Мистика","Россия XIX век","Трагедия"],"views_count":96000,"likes_count":7800,"rating":4.79},

    {"source":"dataset","dataset_path":"prose/Pushkin/Дубровский.txt","is_russian":True,
     "title":"Дубровский","author_username":"alexander_pushkin",
     "genre":Genre.ADVENTURE,"status":BookStatus.COMPLETED,
     "description":"Обедневший дворянин Дубровский, лишившись имения, становится разбойником и влюбляется в дочь своего врага. Роман о чести, мести и несправедливости.",
     "cover_emoji":"🗡️","is_adult":False,"is_featured":False,
     "tags":["Классика","Романтика","Приключение","Россия XIX век"],"views_count":89000,"likes_count":7200,"rating":4.73},

    {"source":"dataset","dataset_path":"prose/Pushkin/Повести Белкина.txt","is_russian":True,
     "title":"Повести Белкина","author_username":"alexander_pushkin",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Пять повестей: «Выстрел», «Метель», «Гробовщик», «Станционный смотритель», «Барышня-крестьянка». Первый прозаический сборник Пушкина — образец лаконичной русской прозы.",
     "cover_emoji":"📜","is_adult":False,"is_featured":False,
     "tags":["Классика","Реализм","Россия XIX век"],"views_count":78000,"likes_count":6300,"rating":4.76},

    {"source":"dataset","dataset_path":"prose/Pushkin/Арап Петра Великого.txt","is_russian":True,
     "title":"Арап Петра Великого","author_username":"alexander_pushkin",
     "genre":Genre.HISTORICAL,"status":BookStatus.COMPLETED,
     "description":"Незаконченный исторический роман о прадеде Пушкина — Абраме Ганнибале при дворе Петра Великого. Живой портрет петровской эпохи.",
     "cover_emoji":"👑","is_adult":False,"is_featured":False,
     "tags":["Классика","Исторический","Россия XIX век"],"views_count":48000,"likes_count":3800,"rating":4.63},

    {"source":"dataset","dataset_path":"prose/Pushkin/История Пугачёва.txt","is_russian":True,
     "title":"История Пугачёва","author_username":"alexander_pushkin",
     "genre":Genre.HISTORICAL,"status":BookStatus.COMPLETED,
     "description":"Документальная история Пугачёвского восстания, написанная Пушкиным на основе архивных материалов. Строгая проза историка, дополняющая художественную «Капитанскую дочку».",
     "cover_emoji":"📜","is_adult":False,"is_featured":False,
     "tags":["Классика","Исторический","Война","Россия XIX век"],"views_count":52000,"likes_count":4100,"rating":4.67},

    # ── Гоголь ────────────────────────────────────────────────────
    {"source":"dataset","dataset_path":"prose/Gogol/Мёртвые души.txt","is_russian":True,
     "title":"Мёртвые души","author_username":"nikolai_gogol",
     "genre":Genre.COMEDY,"status":BookStatus.COMPLETED,
     "description":"Чиновник Чичиков ездит по России и скупает у помещиков «мёртвые души». Поэма в прозе о пороках российского общества — галерея незабываемых характеров.",
     "cover_emoji":"🪙","is_adult":False,"is_featured":True,
     "tags":["Классика","Сатира","Россия XIX век","Юмор"],"views_count":134000,"likes_count":10800,"rating":4.87},

    {"source":"dataset","dataset_path":"prose/Gogol/Ревизор.txt","is_russian":True,
     "title":"Ревизор","author_username":"nikolai_gogol",
     "genre":Genre.COMEDY,"status":BookStatus.COMPLETED,
     "description":"В провинциальный город приезжает мелкий чиновник Хлестаков. Напуганные чиновники принимают его за тайного ревизора. Величайшая комедия русской драматургии.",
     "cover_emoji":"🎭","is_adult":False,"is_featured":False,
     "tags":["Классика","Сатира","Юмор","Россия XIX век"],"views_count":109000,"likes_count":8700,"rating":4.84},

    {"source":"dataset","dataset_path":"prose/Gogol/Тарас Бульба.txt","is_russian":True,
     "title":"Тарас Бульба","author_username":"nikolai_gogol",
     "genre":Genre.HISTORICAL,"status":BookStatus.COMPLETED,
     "description":"Старый казацкий полковник ведёт сыновей на войну с поляками. Эпическая повесть о запорожском казачестве, воле и трагическом предательстве.",
     "cover_emoji":"🏇","is_adult":True,"is_featured":False,
     "tags":["Классика","Исторический","Война","Россия XIX век"],"views_count":98000,"likes_count":7900,"rating":4.78},

    {"source":"dataset","dataset_path":"prose/Gogol/Вечера на хуторе близ Диканьки.txt","is_russian":True,
     "title":"Вечера на хуторе близ Диканьки","author_username":"nikolai_gogol",
     "genre":Genre.FANTASY,"status":BookStatus.COMPLETED,
     "description":"Украинские народные сказки и фантастические истории: черти, ведьмы, влюблённые кузнецы и яркий колорит украинской ночи. Дебютный сборник Гоголя.",
     "cover_emoji":"🌙","is_adult":False,"is_featured":False,
     "tags":["Классика","Мистика","Магия","Юмор"],"views_count":83000,"likes_count":6800,"rating":4.73},

    {"source":"dataset","dataset_path":"prose/Gogol/Невский проспект.txt","is_russian":True,
     "title":"Невский проспект","author_username":"nikolai_gogol",
     "genre":Genre.MYSTERY,"status":BookStatus.COMPLETED,
     "description":"Две истории о молодых людях, увлечённых прекрасными незнакомками на Невском проспекте. Первый шедевр петербургского цикла Гоголя — о разрыве мечты и действительности.",
     "cover_emoji":"🌃","is_adult":True,"is_featured":False,
     "tags":["Классика","Мистика","Реализм","Россия XIX век"],"views_count":67000,"likes_count":5400,"rating":4.77},

    {"source":"dataset","dataset_path":"prose/Gogol/Портрет.txt","is_russian":True,
     "title":"Портрет","author_username":"nikolai_gogol",
     "genre":Genre.MYSTERY,"status":BookStatus.COMPLETED,
     "description":"Бедный художник покупает на рынке зловещий портрет ростовщика с живыми глазами — и его жизнь переворачивается. Мистическая повесть об искусстве, деньгах и душе.",
     "cover_emoji":"🖼️","is_adult":False,"is_featured":False,
     "tags":["Классика","Мистика","Символизм","Россия XIX век"],"views_count":72000,"likes_count":5800,"rating":4.75},

    {"source":"dataset","dataset_path":"prose/Gogol/Шинель.txt","is_russian":True,
     "title":"Шинель","author_username":"nikolai_gogol",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Мелкий чиновник Акакий Акакиевич копит на новую шинель. Повесть о судьбе «маленького человека» — один из самых знаменитых текстов русской литературы.",
     "cover_emoji":"🧥","is_adult":False,"is_featured":False,
     "tags":["Классика","Реализм","Трагедия","Россия XIX век"],"views_count":94000,"likes_count":7600,"rating":4.82},

    {"source":"dataset","dataset_path":"prose/Gogol/Нос.txt","is_russian":True,
     "title":"Нос","author_username":"nikolai_gogol",
     "genre":Genre.COMEDY,"status":BookStatus.COMPLETED,
     "description":"Коллежский асессор Ковалёв обнаруживает, что его нос сбежал и живёт самостоятельной жизнью. Абсурдная, блистательная повесть о чиновничьем тщеславии.",
     "cover_emoji":"👃","is_adult":False,"is_featured":False,
     "tags":["Классика","Юмор","Сатира","Россия XIX век"],"views_count":81000,"likes_count":6500,"rating":4.78},

    {"source":"dataset","dataset_path":"prose/Gogol/Вий.txt","is_russian":True,
     "title":"Вий","author_username":"nikolai_gogol",
     "genre":Genre.HORROR,"status":BookStatus.COMPLETED,
     "description":"Семинарист Хома Брут три ночи читает молитвы над гробом ведьмы. Самая страшная повесть Гоголя — классика русской мистической прозы.",
     "cover_emoji":"👁️","is_adult":True,"is_featured":False,
     "tags":["Классика","Мистика","Магия","Трагедия"],"views_count":88000,"likes_count":7100,"rating":4.80},

    {"source":"dataset","dataset_path":"prose/Gogol/Записки сумасшедшего.txt","is_russian":True,
     "title":"Записки сумасшедшего","author_username":"nikolai_gogol",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Дневник мелкого чиновника Поприщина, постепенно сходящего с ума. Один из первых психологических монологов в русской литературе — трагикомический и пронзительный.",
     "cover_emoji":"📓","is_adult":False,"is_featured":False,
     "tags":["Классика","Психология","Юмор","Россия XIX век"],"views_count":64000,"likes_count":5100,"rating":4.76},

    # ── Тургенев ──────────────────────────────────────────────────
    {"source":"dataset","dataset_path":"prose/Turgenev/Отцы и дети.txt","is_russian":True,
     "title":"Отцы и дети","author_username":"ivan_turgenev",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Нигилист Базаров приезжает в поместье и входит в конфликт со старшим поколением. Роман, породивший слово «нигилизм» и выразивший раскол русского общества 1860-х.",
     "cover_emoji":"🌿","is_adult":False,"is_featured":True,
     "tags":["Классика","Реализм","Россия XIX век","Философия"],"views_count":128000,"likes_count":10200,"rating":4.85},

    {"source":"dataset","dataset_path":"prose/Turgenev/Дворянское гнездо.txt","is_russian":True,
     "title":"Дворянское гнездо","author_username":"ivan_turgenev",
     "genre":Genre.ROMANCE,"status":BookStatus.COMPLETED,
     "description":"Лаврецкий возвращается в родное гнездо и влюбляется в Лизу Калитину. Тургеневский роман о несостоявшемся счастье и русском долге.",
     "cover_emoji":"🍂","is_adult":False,"is_featured":False,
     "tags":["Классика","Романтика","Россия XIX век","Трагедия"],"views_count":87000,"likes_count":6900,"rating":4.77},

    {"source":"dataset","dataset_path":"prose/Turgenev/Записки охотника.txt","is_russian":True,
     "title":"Записки охотника","author_username":"ivan_turgenev",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Двадцать пять очерков о помещиках и крестьянах. Книга, которая ускорила отмену крепостного права. Тонкая лирическая проза с острым социальным видением.",
     "cover_emoji":"🌲","is_adult":False,"is_featured":False,
     "tags":["Классика","Реализм","Природа","Россия XIX век"],"views_count":76000,"likes_count":6200,"rating":4.79},

    {"source":"dataset","dataset_path":"prose/Turgenev/Вешние воды.txt","is_russian":True,
     "title":"Вешние воды","author_username":"ivan_turgenev",
     "genre":Genre.ROMANCE,"status":BookStatus.COMPLETED,
     "description":"Молодой русский Санин влюбляется в итальянскую красавицу Джемму, но роковая встреча с богатой авантюристкой перевернёт всё. Повесть о любви, слабости и раскаянии.",
     "cover_emoji":"💧","is_adult":False,"is_featured":False,
     "tags":["Классика","Романтика","Россия XIX век","Трагедия","Любовь"],"views_count":72000,"likes_count":5800,"rating":4.76},

    {"source":"dataset","dataset_path":"prose/Turgenev/Первая любовь.txt","is_russian":True,
     "title":"Первая любовь","author_username":"ivan_turgenev",
     "genre":Genre.ROMANCE,"status":BookStatus.COMPLETED,
     "description":"Шестнадцатилетний Владимир влюбляется в свою соседку — своевольную красавицу Зинаиду. Но тайна её сердца оказывается жестокой. Самая пронзительная повесть о первой любви.",
     "cover_emoji":"🌺","is_adult":False,"is_featured":False,
     "tags":["Классика","Романтика","Россия XIX век","Трагедия","Любовь"],"views_count":94000,"likes_count":7800,"rating":4.83},

    {"source":"dataset","dataset_path":"prose/Turgenev/Муму.txt","is_russian":True,
     "title":"Муму","author_username":"ivan_turgenev",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Немой дворник Герасим привязывается к собачке Муму. Но барыня приказывает избавиться от неё. Рассказ-протест против крепостного права.",
     "cover_emoji":"🐕","is_adult":False,"is_featured":False,
     "tags":["Классика","Реализм","Трагедия","Россия XIX век"],"views_count":94000,"likes_count":7700,"rating":4.72},

    {"source":"dataset","dataset_path":"prose/Turgenev/Ася.txt","is_russian":True,
     "title":"Ася","author_username":"ivan_turgenev",
     "genre":Genre.ROMANCE,"status":BookStatus.COMPLETED,
     "description":"Русский путешественник встречает в Германии загадочную девушку Асю и влюбляется в неё. Но в решающий момент трусость берёт верх. О потерянном счастье.",
     "cover_emoji":"🌸","is_adult":False,"is_featured":False,
     "tags":["Классика","Романтика","Россия XIX век","Трагедия"],"views_count":81000,"likes_count":6600,"rating":4.78},

    {"source":"dataset","dataset_path":"prose/Turgenev/Дым.txt","is_russian":True,
     "title":"Дым","author_username":"ivan_turgenev",
     "genre":Genre.ROMANCE,"status":BookStatus.COMPLETED,
     "description":"В Баден-Бадене русский дворянин Литвинов встречает бывшую возлюбленную и снова вспыхивает давняя страсть. Роман о иллюзиях, компромиссах и цене счастья.",
     "cover_emoji":"💨","is_adult":False,"is_featured":False,
     "tags":["Классика","Романтика","Россия XIX век","Трагедия","Любовь"],"views_count":58000,"likes_count":4600,"rating":4.69},

    # ── Чехов ─────────────────────────────────────────────────────
    {"source":"dataset","dataset_path":"prose/Chekhov/Палата №6.txt","is_russian":True,
     "title":"Палата № 6","author_username":"anton_chekhov",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Провинциальный доктор начинает беседовать с пациентом психиатрической палаты и сам попадает в неё. Беспощадная повесть о безумии системы.",
     "cover_emoji":"🏥","is_adult":False,"is_featured":True,
     "tags":["Классика","Психология","Трагедия","Россия XIX век"],"views_count":98000,"likes_count":8100,"rating":4.86},

    {"source":"dataset","dataset_path":"prose/Chekhov/Вишнёвый сад.txt","is_russian":True,
     "title":"Вишнёвый сад","author_username":"anton_chekhov",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Разорившаяся помещица возвращается в родовое имение, которое продают на аукционе. Последняя пьеса Чехова — лирическая комедия о конце старой России.",
     "cover_emoji":"🌳","is_adult":False,"is_featured":True,
     "tags":["Классика","Трагедия","Россия XIX век","Символизм"],"views_count":101000,"likes_count":8200,"rating":4.87},

    {"source":"dataset","dataset_path":"prose/Chekhov/Три сестры.txt","is_russian":True,
     "title":"Три сестры","author_username":"anton_chekhov",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Три сестры мечтают о Москве, но их жизнь проходит в провинции. Пьеса о несбыточных надеждах и невозможности вырваться из обыденности.",
     "cover_emoji":"🌸","is_adult":False,"is_featured":False,
     "tags":["Классика","Трагедия","Психология","Россия XIX век"],"views_count":86000,"likes_count":6900,"rating":4.83},

    {"source":"dataset","dataset_path":"prose/Chekhov/Дуэль.txt","is_russian":True,
     "title":"Дуэль","author_username":"anton_chekhov",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Два совершенно разных человека — вялый интеллигент Лаевский и убеждённый зоолог Фон Корен — сталкиваются в конфликте, ведущем к дуэли. Лучшая повесть Чехова о русской интеллигенции.",
     "cover_emoji":"🔫","is_adult":False,"is_featured":False,
     "tags":["Классика","Психология","Россия XIX век","Реализм"],"views_count":74000,"likes_count":5900,"rating":4.82},

    {"source":"dataset","dataset_path":"prose/Chekhov/Драма на охоте.txt","is_russian":True,
     "title":"Драма на охоте","author_username":"anton_chekhov",
     "genre":Genre.DETECTIVE,"status":BookStatus.COMPLETED,
     "description":"Следователь расследует убийство молодой женщины в помещичьей усадьбе. Единственный детективный роман Чехова — захватывающий и психологически точный.",
     "cover_emoji":"🔍","is_adult":True,"is_featured":False,
     "tags":["Классика","Детектив","Психология","Россия XIX век"],"views_count":82000,"likes_count":6600,"rating":4.78},

    {"source":"dataset","dataset_path":"prose/Chekhov/Дама с собачкой.txt","is_russian":True,
     "title":"Дама с собачкой","author_username":"anton_chekhov",
     "genre":Genre.ROMANCE,"status":BookStatus.COMPLETED,
     "description":"Банковский служащий Гуров встречает в Ялте замужнюю Анну Сергеевну. Курортный роман неожиданно перерастает в настоящую любовь. Шедевр мировой короткой прозы.",
     "cover_emoji":"🐩","is_adult":False,"is_featured":False,
     "tags":["Классика","Романтика","Трагедия","Россия XIX век","Любовь"],"views_count":118000,"likes_count":9600,"rating":4.88},

    {"source":"dataset","dataset_path":"prose/Chekhov/Ионыч.txt","is_russian":True,
     "title":"Ионыч","author_username":"anton_chekhov",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"История молодого врача Старцева, как провинциальный быт и несостоявшаяся любовь превращают его в «Ионыча» — сытого, равнодушного обывателя.",
     "cover_emoji":"💊","is_adult":False,"is_featured":False,
     "tags":["Классика","Реализм","Трагедия","Россия XIX век"],"views_count":67000,"likes_count":5300,"rating":4.79},

    {"source":"dataset","dataset_path":"prose/Chekhov/В овраге.txt","is_russian":True,
     "title":"В овраге","author_username":"anton_chekhov",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Жизнь крестьянской семьи в деревне, где торгуют поддельной водкой. История ужасающего преступления и бессилия добра перед злом. Самая жёсткая повесть Чехова.",
     "cover_emoji":"🌾","is_adult":True,"is_featured":False,
     "tags":["Классика","Реализм","Трагедия","Россия XIX век","Преступление"],"views_count":58000,"likes_count":4600,"rating":4.76},

    {"source":"dataset","dataset_path":"prose/Chekhov/Человек в футляре.txt","is_russian":True,
     "title":"Человек в футляре","author_username":"anton_chekhov",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Учитель Беликов боится всего, что «как бы чего не вышло», и своим страхом держит в футляре весь город. Рассказ-символ о духовной несвободе.",
     "cover_emoji":"📦","is_adult":False,"is_featured":False,
     "tags":["Классика","Сатира","Психология","Россия XIX век"],"views_count":89000,"likes_count":7200,"rating":4.83},

    {"source":"dataset","dataset_path":"prose/Chekhov/Дом с мезонином.txt","is_russian":True,
     "title":"Дом с мезонином","author_username":"anton_chekhov",
     "genre":Genre.ROMANCE,"status":BookStatus.COMPLETED,
     "description":"Художник влюбляется в Мисюсь — юную сестру деятельной народницы Лиды. Но Лида разлучает их. Лирическая повесть о красоте, любви и невозможности счастья.",
     "cover_emoji":"🏠","is_adult":False,"is_featured":False,
     "tags":["Классика","Романтика","Россия XIX век","Трагедия","Любовь"],"views_count":61000,"likes_count":4900,"rating":4.77},

    # ── Лермонтов ─────────────────────────────────────────────────
    {"source":"dataset","dataset_path":"prose/Lermontov/Герой нашего времени.txt","is_russian":True,
     "title":"Герой нашего времени","author_username":"mikhail_lermontov",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Печорин — офицер, эгоист и скептик — странствует по Кавказу и разрушает жизни людей. Первый психологический роман в русской литературе.",
     "cover_emoji":"🏔️","is_adult":False,"is_featured":True,
     "tags":["Классика","Психология","Россия XIX век","Философия"],"views_count":138000,"likes_count":11200,"rating":4.89},

    # ── Горький ───────────────────────────────────────────────────
    {"source":"dataset","dataset_path":"prose/Gorky/Мать.txt","is_russian":True,
     "title":"Мать","author_username":"maxim_gorky",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Простая заводская женщина Пелагея Ниловна следует за сыном-революционером и сама становится борцом. Роман о пробуждении народного сознания — главный политический роман Горького.",
     "cover_emoji":"✊","is_adult":False,"is_featured":False,
     "tags":["Классика","Реализм","Война","Россия XIX век"],"views_count":84000,"likes_count":6700,"rating":4.72},

    {"source":"dataset","dataset_path":"prose/Gorky/Детство.txt","is_russian":True,
     "title":"Детство (Горький)","author_username":"maxim_gorky",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Первая часть автобиографической трилогии. Алёша Пешков растёт в жестокой купеческой семье. Пронзительный рассказ о детстве среди насилия, где свет исходит от бабушки.",
     "cover_emoji":"🏚️","is_adult":False,"is_featured":False,
     "tags":["Классика","Реализм","Семья","Россия XIX век"],"views_count":84000,"likes_count":6700,"rating":4.75},

    {"source":"dataset","dataset_path":"prose/Gorky/В людях.txt","is_russian":True,
     "title":"В людях","author_username":"maxim_gorky",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Вторая часть трилогии. Алёша работает слугой и поварёнком, жадно читая всё, что попадается. Роман о самообразовании и становлении писателя.",
     "cover_emoji":"📚","is_adult":False,"is_featured":False,
     "tags":["Классика","Реализм","Россия XIX век"],"views_count":58000,"likes_count":4600,"rating":4.67},

    {"source":"dataset","dataset_path":"prose/Gorky/Мои университеты.txt","is_russian":True,
     "title":"Мои университеты","author_username":"maxim_gorky",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Третья часть трилогии. Алёша идёт в «университеты жизни»: работает в пекарне, общается с народниками, переживает духовный кризис.",
     "cover_emoji":"🎓","is_adult":False,"is_featured":False,
     "tags":["Классика","Реализм","Россия XIX век"],"views_count":52000,"likes_count":4100,"rating":4.65},

    {"source":"dataset","dataset_path":"prose/Gorky/Фома Гордеев.txt","is_russian":True,
     "title":"Фома Гордеев","author_username":"maxim_gorky",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Сын богатого купца Фома Гордеев бунтует против мира наживы и бесчестья. Роман о трагедии свободного человека в клетке купеческого мира.",
     "cover_emoji":"🌊","is_adult":False,"is_featured":False,
     "tags":["Классика","Реализм","Трагедия","Россия XIX век","Психология"],"views_count":67000,"likes_count":5300,"rating":4.73},

    {"source":"dataset","dataset_path":"prose/Gorky/На дне.txt","is_russian":True,
     "title":"На дне","author_username":"maxim_gorky",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"В ночлежке собрались отверженные. Приходит странник Лука с утешительной ложью. Пьеса-вопрос: что лучше — правда или утешение?",
     "cover_emoji":"🕯️","is_adult":True,"is_featured":False,
     "tags":["Классика","Реализм","Трагедия","Россия XIX век","Философия"],"views_count":94000,"likes_count":7600,"rating":4.81},

    {"source":"dataset","dataset_path":"prose/Gorky/Старуха Изергиль.txt","is_russian":True,
     "title":"Старуха Изергиль","author_username":"maxim_gorky",
     "genre":Genre.FANTASY,"status":BookStatus.COMPLETED,
     "description":"Три истории: легенда о гордеце Ларре, история жизни самой старухи Изергиль и легенда о Данко, осветившем путь людям своим горящим сердцем.",
     "cover_emoji":"🔥","is_adult":False,"is_featured":False,
     "tags":["Классика","Магия","Философия","Реализм"],"views_count":78000,"likes_count":6400,"rating":4.78},

    {"source":"dataset","dataset_path":"prose/Gorky/Бывшие люди.txt","is_russian":True,
     "title":"Бывшие люди","author_username":"maxim_gorky",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Очерк о людях «дна» — бывших чиновниках, дворянах, интеллигентах, павших до ночлежки. Ранний Горький в лучшей реалистической форме.",
     "cover_emoji":"🌧️","is_adult":False,"is_featured":False,
     "tags":["Классика","Реализм","Трагедия","Россия XIX век"],"views_count":48000,"likes_count":3800,"rating":4.68},

    # ── Брюсов ────────────────────────────────────────────────────
    {"source":"dataset","dataset_path":"prose/Bryusov/Огненный ангел.txt","is_russian":True,
     "title":"Огненный ангел","author_username":"valery_bryusov",
     "genre":Genre.HISTORICAL,"status":BookStatus.COMPLETED,
     "description":"Германия XVI века: рыцарь Рупрехт встречает девушку Ренату, одержимую духом «огненного ангела». Мистический исторический роман — вершина русского символизма.",
     "cover_emoji":"🔥","is_adult":True,"is_featured":False,
     "tags":["Исторический","Мистика","Символизм","Романтика","Средневековье"],"views_count":58000,"likes_count":4600,"rating":4.72},

    {"source":"dataset","dataset_path":"prose/Bryusov/Алтарь победы.txt","is_russian":True,
     "title":"Алтарь победы","author_username":"valery_bryusov",
     "genre":Genre.HISTORICAL,"status":BookStatus.COMPLETED,
     "description":"Рим IV века нашей эры на закате великой империи. Молодой провинциал Юний Норбан попадает в водоворот языческой и христианской борьбы за душу умирающей цивилизации.",
     "cover_emoji":"🏛️","is_adult":False,"is_featured":False,
     "tags":["Исторический","Классика","Философия","Средневековье"],"views_count":42000,"likes_count":3300,"rating":4.65},

    {"source":"dataset","dataset_path":"prose/Bryusov/Юпитер поверженный.txt","is_russian":True,
     "title":"Юпитер поверженный","author_username":"valery_bryusov",
     "genre":Genre.HISTORICAL,"status":BookStatus.COMPLETED,
     "description":"Продолжение «Алтаря победы»: падение Западной Римской империи. Последние язычники и первые христиане в эпоху великого перелома.",
     "cover_emoji":"⚡","is_adult":False,"is_featured":False,
     "tags":["Исторический","Классика","Философия","Средневековье","Война"],"views_count":36000,"likes_count":2900,"rating":4.61},

    {"source":"dataset","dataset_path":"prose/Bryusov/Республика Южного Креста.txt","is_russian":True,
     "title":"Республика Южного Креста","author_username":"valery_bryusov",
     "genre":Genre.SCIFI,"status":BookStatus.COMPLETED,
     "description":"В идеальном городе под арктическим куполом разгорается эпидемия безумия — «мании противоречия». Рассказ-антиутопия, предвосхитивший Замятина и Оруэлла.",
     "cover_emoji":"🌐","is_adult":False,"is_featured":False,
     "tags":["Антиутопия","Символизм","Апокалипсис","Философия"],"views_count":44000,"likes_count":3500,"rating":4.68},

    # ── Герцен ────────────────────────────────────────────────────
    {"source":"dataset","dataset_path":"prose/Herzen/Кто виноват.txt","is_russian":True,
     "title":"Кто виноват?","author_username":"alexander_herzen",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Молодой дворянин Бельтов возвращается в провинцию и разрушает тихое семейное счастье Круциферских. Роман-вопрос о вине, обществе и неустроенности «лишнего человека».",
     "cover_emoji":"❓","is_adult":False,"is_featured":False,
     "tags":["Классика","Реализм","Психология","Россия XIX век","Философия"],"views_count":48000,"likes_count":3800,"rating":4.68},

    {"source":"dataset","dataset_path":"prose/Herzen/Долг прежде всего.txt","is_russian":True,
     "title":"Долг прежде всего","author_username":"alexander_herzen",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Повесть об испанском революционере и его семье, оказавшейся в ловушке чести и долга. Героический сюжет с острым политическим подтекстом.",
     "cover_emoji":"⚡","is_adult":False,"is_featured":False,
     "tags":["Классика","Исторический","Война","Философия"],"views_count":38000,"likes_count":3000,"rating":4.58},

    {"source":"dataset","dataset_path":"prose/Herzen/С того берега.txt","is_russian":True,
     "title":"С того берега","author_username":"alexander_herzen",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Философские диалоги и монологи о революции 1848 года, крушении либеральных надежд и судьбе Европы. Одно из главных произведений русской политической мысли.",
     "cover_emoji":"🌊","is_adult":False,"is_featured":False,
     "tags":["Классика","Философия","Исторический","Реализм"],"views_count":32000,"likes_count":2500,"rating":4.60},

    # ══════════════════════════════════════════════════════════════
    # ENGLISH BOOKS — archive_eng.zip / books.db
    # engdb_id = book_id in books.db
    # ══════════════════════════════════════════════════════════════

    # ── Lewis Carroll ─────────────────────────────────────────────
    {"source":"engdb","engdb_id":63,"is_russian":False,
     "title":"Alice's Adventures in Wonderland","author_username":"lewis_carroll",
     "genre":Genre.FANTASY,"status":BookStatus.COMPLETED,
     "description":"Alice follows a White Rabbit down a rabbit hole into a world of talking creatures and absurd logic. A timeless Victorian masterpiece of imagination and wordplay.",
     "cover_emoji":"🐇","is_adult":False,"is_featured":True,
     "tags":["Магия","Приключение","Классика","Дети"],"views_count":124500,"likes_count":9800,"rating":4.82},

    # ── L. Frank Baum ─────────────────────────────────────────────
    {"source":"engdb","engdb_id":877,"is_russian":False,
     "title":"The Patchwork Girl of Oz","author_username":"lf_baum",
     "genre":Genre.FANTASY,"status":BookStatus.COMPLETED,
     "description":"A young Munchkin boy and a living Patchwork Girl journey through the magical Land of Oz in search of ingredients for a life-restoring potion.",
     "cover_emoji":"🌈","is_adult":False,"is_featured":False,
     "tags":["Магия","Дружба","Приключение","Дети"],"views_count":74000,"likes_count":5800,"rating":4.65},

    # ── Jane Austen ───────────────────────────────────────────────
    {"source":"engdb","engdb_id":581,"is_russian":False,
     "title":"Pride and Prejudice","author_username":"jane_austen",
     "genre":Genre.ROMANCE,"status":BookStatus.COMPLETED,
     "description":"Elizabeth Bennet navigates love and marriage in Regency England. Her sparring relationship with the proud Mr. Darcy is one of literature's greatest love stories.",
     "cover_emoji":"💌","is_adult":False,"is_featured":True,
     "tags":["Романтика","Классика","Семья","Любовь"],"views_count":210000,"likes_count":18500,"rating":4.91},

    {"source":"engdb","engdb_id":620,"is_russian":False,
     "title":"Sense and Sensibility","author_username":"jane_austen",
     "genre":Genre.ROMANCE,"status":BookStatus.COMPLETED,
     "description":"Sisters Elinor and Marianne Dashwood seek love and security — one through cool reason, the other through passionate feeling. Austen's first published novel.",
     "cover_emoji":"🌸","is_adult":False,"is_featured":False,
     "tags":["Романтика","Классика","Семья","Любовь"],"views_count":98500,"likes_count":7800,"rating":4.79},

    {"source":"engdb","engdb_id":178,"is_russian":False,
     "title":"Emma","author_username":"jane_austen",
     "genre":Genre.ROMANCE,"status":BookStatus.COMPLETED,
     "description":"Emma Woodhouse amuses herself matchmaking for her friends — with disastrously misguided results. Austen's wittiest and most perfectly constructed novel.",
     "cover_emoji":"🎀","is_adult":False,"is_featured":False,
     "tags":["Романтика","Классика","Юмор","Семья","Любовь"],"views_count":112000,"likes_count":9200,"rating":4.83},

    {"source":"engdb","engdb_id":546,"is_russian":False,
     "title":"Persuasion","author_username":"jane_austen",
     "genre":Genre.ROMANCE,"status":BookStatus.COMPLETED,
     "description":"Anne Elliot reunites with Captain Wentworth years after being persuaded to end their engagement. Austen's last, most emotionally mature novel.",
     "cover_emoji":"🍂","is_adult":False,"is_featured":False,
     "tags":["Романтика","Классика","Любовь"],"views_count":74000,"likes_count":5900,"rating":4.77},

    # ── Charlotte Brontë ──────────────────────────────────────────
    {"source":"engdb","engdb_id":275,"is_russian":False,
     "title":"Jane Eyre","author_username":"charlotte_bronte",
     "genre":Genre.ROMANCE,"status":BookStatus.COMPLETED,
     "description":"Orphan Jane Eyre becomes a governess and falls for the brooding Mr. Rochester — but dark secrets hidden in Thornfield Hall threaten everything.",
     "cover_emoji":"🌹","is_adult":False,"is_featured":False,
     "tags":["Романтика","Классика","Психология","Любовь"],"views_count":145000,"likes_count":11200,"rating":4.87},

    # ── Emily Brontë ──────────────────────────────────────────────
    {"source":"engdb","engdb_id":1084,"is_russian":False,
     "title":"Wuthering Heights","author_username":"emily_bronte",
     "genre":Genre.ROMANCE,"status":BookStatus.COMPLETED,
     "description":"Heathcliff and Catherine's fierce, obsessive love on the wild Yorkshire moors ends in tragedy spanning two generations. Gothic passion at its most intense.",
     "cover_emoji":"🌬️","is_adult":False,"is_featured":False,
     "tags":["Романтика","Классика","Трагедия","Психология","Любовь"],"views_count":118000,"likes_count":9600,"rating":4.83},

    # ── Arthur Conan Doyle ────────────────────────────────────────
    {"source":"engdb","engdb_id":668,"is_russian":False,
     "title":"The Adventures of Sherlock Holmes","author_username":"arthur_conan_doyle",
     "genre":Genre.DETECTIVE,"status":BookStatus.COMPLETED,
     "description":"Twelve classic cases solved by the world's greatest detective: A Scandal in Bohemia, The Red-Headed League, The Five Orange Pips, and more.",
     "cover_emoji":"🔍","is_adult":False,"is_featured":True,
     "tags":["Детектив","Классика","Психология"],"views_count":189000,"likes_count":15200,"rating":4.93},

    {"source":"engdb","engdb_id":802,"is_russian":False,
     "title":"The Hound of the Baskervilles","author_username":"arthur_conan_doyle",
     "genre":Genre.DETECTIVE,"status":BookStatus.COMPLETED,
     "description":"A spectral hound terrorises the Baskerville family on the fog-shrouded Dartmoor moors. Holmes and Watson must unravel a curse centuries old.",
     "cover_emoji":"🐺","is_adult":False,"is_featured":False,
     "tags":["Детектив","Мистика","Классика"],"views_count":134000,"likes_count":10800,"rating":4.88},

    {"source":"engdb","engdb_id":39,"is_russian":False,
     "title":"A Study in Scarlet","author_username":"arthur_conan_doyle",
     "genre":Genre.DETECTIVE,"status":BookStatus.COMPLETED,
     "description":"The first Sherlock Holmes story: Dr Watson meets the brilliant detective and together they solve a murder in London with roots stretching to the American West.",
     "cover_emoji":"🕵️","is_adult":False,"is_featured":False,
     "tags":["Детектив","Классика","Приключение"],"views_count":91000,"likes_count":7500,"rating":4.79},

    # ── Bram Stoker ───────────────────────────────────────────────
    {"source":"engdb","engdb_id":165,"is_russian":False,
     "title":"Dracula","author_username":"bram_stoker",
     "genre":Genre.HORROR,"status":BookStatus.COMPLETED,
     "description":"Jonathan Harker's visit to Count Dracula's Transylvanian castle begins a nightmare. Told through journals and letters — the definitive vampire novel.",
     "cover_emoji":"🧛","is_adult":True,"is_featured":True,
     "tags":["Вампиры","Мистика","Классика"],"views_count":178000,"likes_count":13500,"rating":4.85},

    # ── Mary Shelley ──────────────────────────────────────────────
    {"source":"engdb","engdb_id":204,"is_russian":False,
     "title":"Frankenstein","author_username":"mary_shelley",
     "genre":Genre.SCIFI,"status":BookStatus.COMPLETED,
     "description":"Victor Frankenstein creates a sentient being from dead matter and abandons it in horror. A profound meditation on creation, responsibility, and what it means to be human.",
     "cover_emoji":"⚡","is_adult":False,"is_featured":True,
     "tags":["Классика","Психология","Мистика","Философия"],"views_count":112000,"likes_count":9100,"rating":4.72},

    # ── Robert Louis Stevenson ────────────────────────────────────
    {"source":"engdb","engdb_id":164,"is_russian":False,
     "title":"Dr. Jekyll and Mr. Hyde","author_username":"rl_stevenson",
     "genre":Genre.HORROR,"status":BookStatus.COMPLETED,
     "description":"Dr Jekyll's scientific potion splits his personality into two — the respectable doctor and the monstrous Hyde. A chilling tale of duality and the dark side of human nature.",
     "cover_emoji":"🧪","is_adult":True,"is_featured":False,
     "tags":["Мистика","Психология","Классика"],"views_count":98000,"likes_count":8200,"rating":4.76},

    {"source":"engdb","engdb_id":1035,"is_russian":False,
     "title":"Treasure Island","author_username":"rl_stevenson",
     "genre":Genre.ADVENTURE,"status":BookStatus.COMPLETED,
     "description":"Young Jim Hawkins sets sail for Treasure Island alongside the cunning Long John Silver and a crew of dangerous pirates. The novel that defined the modern pirate story.",
     "cover_emoji":"⚓","is_adult":False,"is_featured":True,
     "tags":["Приключение","Классика","Выживание"],"views_count":134000,"likes_count":10900,"rating":4.83},

    # ── H.G. Wells ────────────────────────────────────────────────
    {"source":"engdb","engdb_id":969,"is_russian":False,
     "title":"The Time Machine","author_username":"hg_wells",
     "genre":Genre.SCIFI,"status":BookStatus.COMPLETED,
     "description":"A Victorian scientist travels to the year 802,701 AD and discovers humanity has evolved into two very different species. The novel that invented the concept of time travel.",
     "cover_emoji":"⏱️","is_adult":False,"is_featured":False,
     "tags":["Космос","Путешествие","Классика","Антиутопия"],"views_count":89000,"likes_count":7400,"rating":4.68},

    {"source":"engdb","engdb_id":1066,"is_russian":False,
     "title":"The War of the Worlds","author_username":"hg_wells",
     "genre":Genre.SCIFI,"status":BookStatus.COMPLETED,
     "description":"Martian cylinders land in Surrey and unstoppable tripods begin destroying everything in their path. Mankind's first alien invasion story.",
     "cover_emoji":"🚀","is_adult":False,"is_featured":False,
     "tags":["Космос","Апокалипсис","Классика","Война"],"views_count":95600,"likes_count":7900,"rating":4.71},

    # ── Jules Verne ───────────────────────────────────────────────
    {"source":"engdb","engdb_id":99,"is_russian":False,
     "title":"Around the World in Eighty Days","author_username":"jules_verne",
     "genre":Genre.ADVENTURE,"status":BookStatus.COMPLETED,
     "description":"The eccentric Phileas Fogg bets his entire fortune that he can circumnavigate the globe in just 80 days. The race begins — and the world follows.",
     "cover_emoji":"🌍","is_adult":False,"is_featured":False,
     "tags":["Приключение","Классика","Путешествие"],"views_count":112000,"likes_count":9200,"rating":4.77},

    {"source":"engdb","engdb_id":1,"is_russian":False,
     "title":"20,000 Leagues Under the Sea","author_username":"jules_verne",
     "genre":Genre.ADVENTURE,"status":BookStatus.COMPLETED,
     "description":"Professor Aronnax is taken captive aboard the Nautilus, the submarine of the reclusive genius Captain Nemo. An astonishing voyage through the wonders and terrors of the deep.",
     "cover_emoji":"🦑","is_adult":False,"is_featured":False,
     "tags":["Приключение","Классика","Путешествие","Природа"],"views_count":94000,"likes_count":7700,"rating":4.74},

    # ── Mark Twain ────────────────────────────────────────────────
    {"source":"engdb","engdb_id":669,"is_russian":False,
     "title":"The Adventures of Tom Sawyer","author_username":"mark_twain",
     "genre":Genre.ADVENTURE,"status":BookStatus.COMPLETED,
     "description":"Tom Sawyer's irrepressible adventures on the Mississippi: whitewashing a fence, witnessing a murder in the graveyard, and hunting buried pirate treasure.",
     "cover_emoji":"🎣","is_adult":False,"is_featured":False,
     "tags":["Приключение","Дружба","Классика","Дети"],"views_count":103000,"likes_count":8600,"rating":4.74},

    {"source":"engdb","engdb_id":666,"is_russian":False,
     "title":"Adventures of Huckleberry Finn","author_username":"mark_twain",
     "genre":Genre.ADVENTURE,"status":BookStatus.COMPLETED,
     "description":"Huck Finn and the runaway slave Jim float down the Mississippi River toward freedom. Twain's masterpiece and a searing critique of racism and moral hypocrisy.",
     "cover_emoji":"🚣","is_adult":False,"is_featured":False,
     "tags":["Приключение","Классика","Дружба","Выживание"],"views_count":112000,"likes_count":9200,"rating":4.80},

    # ── Charles Dickens ───────────────────────────────────────────
    {"source":"engdb","engdb_id":40,"is_russian":False,
     "title":"A Tale of Two Cities","author_username":"charles_dickens",
     "genre":Genre.HISTORICAL,"status":BookStatus.COMPLETED,
     "description":"London and Paris on the eve of the French Revolution. A sweeping story of sacrifice, resurrection, and a love that ultimately transcends death.",
     "cover_emoji":"🏰","is_adult":False,"is_featured":True,
     "tags":["Классика","Исторический","Предательство","Война"],"views_count":138000,"likes_count":10600,"rating":4.84},

    {"source":"engdb","engdb_id":222,"is_russian":False,
     "title":"Great Expectations","author_username":"charles_dickens",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Orphan Pip's humble life is transformed by a mysterious anonymous benefactor. Dickens' masterpiece about ambition, class, loyalty, and what it truly means to be a gentleman.",
     "cover_emoji":"🎩","is_adult":False,"is_featured":False,
     "tags":["Классика","Семья","Психология","Реализм"],"views_count":119000,"likes_count":9400,"rating":4.80},

    {"source":"engdb","engdb_id":416,"is_russian":False,
     "title":"Oliver Twist","author_username":"charles_dickens",
     "genre":Genre.DRAMA,"status":BookStatus.COMPLETED,
     "description":"Young Oliver, born in a workhouse, escapes into the criminal underworld of Victorian London. Dickens' fierce attack on the Poor Law system and the hypocrisy of respectable society.",
     "cover_emoji":"🥣","is_adult":False,"is_featured":False,
     "tags":["Классика","Реализм","Дети","Преступление"],"views_count":97000,"likes_count":7900,"rating":4.75},

    # ── Oscar Wilde ───────────────────────────────────────────────
    {"source":"engdb","engdb_id":885,"is_russian":False,
     "title":"The Picture of Dorian Gray","author_username":"oscar_wilde",
     "genre":Genre.MYSTERY,"status":BookStatus.COMPLETED,
     "description":"Dorian Gray's portrait bears the marks of age and sin while he remains forever beautiful. Wilde's only novel — a dazzling fable of vanity, corruption, and damnation.",
     "cover_emoji":"🖼️","is_adult":True,"is_featured":True,
     "tags":["Мистика","Классика","Психология","Символизм"],"views_count":142000,"likes_count":11300,"rating":4.86},

    # ── Jack London ───────────────────────────────────────────────
    {"source":"engdb","engdb_id":709,"is_russian":False,
     "title":"The Call of the Wild","author_username":"jack_london",
     "genre":Genre.ADVENTURE,"status":BookStatus.COMPLETED,
     "description":"Buck, a pampered California dog, is stolen and sold to Yukon sled teams during the Gold Rush. A primal tale of survival, instinct, and the call of the wilderness.",
     "cover_emoji":"🐕","is_adult":False,"is_featured":False,
     "tags":["Приключение","Классика","Выживание","Природа"],"views_count":88000,"likes_count":7200,"rating":4.73},

    # ── Alexandre Dumas ───────────────────────────────────────────
    {"source":"engdb","engdb_id":730,"is_russian":False,
     "title":"The Count of Monte Cristo","author_username":"alexandre_dumas",
     "genre":Genre.ADVENTURE,"status":BookStatus.COMPLETED,
     "description":"Wrongfully imprisoned Edmond Dantès escapes after years of suffering and returns as the fabulously wealthy Count of Monte Cristo to exact perfect vengeance on his betrayers.",
     "cover_emoji":"💎","is_adult":False,"is_featured":True,
     "tags":["Приключение","Классика","Предательство","Исторический"],"views_count":198000,"likes_count":16500,"rating":4.92},

    {"source":"engdb","engdb_id":967,"is_russian":False,
     "title":"The Three Musketeers","author_username":"alexandre_dumas",
     "genre":Genre.ADVENTURE,"status":BookStatus.COMPLETED,
     "description":"Young Gascon d'Artagnan rides to Paris and befriends the three legendary musketeers — Athos, Porthos and Aramis. Together they foil Cardinal Richelieu's schemes against the queen.",
     "cover_emoji":"⚔️","is_adult":False,"is_featured":False,
     "tags":["Приключение","Классика","Исторический","Дружба"],"views_count":156000,"likes_count":12800,"rating":4.88},

]

# ══════════════════════════════════════════════════════════════════════════════
# REVIEW TEXTS
# ══════════════════════════════════════════════════════════════════════════════

REVIEWS_RU = [
    "Абсолютный шедевр. Каждая страница — откровение. Перечитывал несколько раз.",
    "Одна из лучших книг в моей жизни. Язык безупречен, образы незабываемы.",
    "Глубокая, пронзительная проза. После прочтения долго не мог прийти в себя.",
    "Классика на все времена. Каждое поколение открывает в этом тексте что-то своё.",
    "Читал на одном дыхании. Невозможно оторваться от первой до последней страницы.",
    "Гениально и просто одновременно. Автор говорит о вечном очень понятно.",
    "После этой книги смотришь на мир по-другому. Настоятельно рекомендую.",
    "Знал по школьной программе, а теперь понял заново. Совсем другое восприятие.",
    "Психологическая глубина поразительная. Каждый персонаж — живой человек.",
    "Одно из тех произведений, которые остаются с тобой навсегда.",
]
REVIEWS_EN = [
    "A masterpiece that stands the test of time. Every chapter draws you deeper.",
    "Incredible prose and unforgettable characters. One of the best I've ever read.",
    "The author's genius is evident on every page. A must-read for any book lover.",
    "Captivating from first page to last. I couldn't put it down.",
    "A perfect blend of suspense and beauty. The writing is simply outstanding.",
    "An absolute classic. Changed the way I see the world.",
    "Brilliant storytelling with complex, richly drawn characters.",
    "I was completely transported to another world. Extraordinary.",
    "One of those rare books that leaves you thinking for days after finishing.",
    "Simply stunning. Every sentence is crafted with care.",
]


# ══════════════════════════════════════════════════════════════════════════════
# SEED
# ══════════════════════════════════════════════════════════════════════════════

async def seed():
    # Validate dataset
    if not os.path.isdir(DATASET_DIR):
        print(f"⚠️  Dataset not found at: {DATASET_DIR}")
        print("   Place the extracted archive.zip contents at that path.")
        print("   (Should contain prose/, poems/ subdirectories)")
        sys.exit(1)

    ru_count = sum(1 for b in BOOKS if b.get("is_russian"))
    en_count = sum(1 for b in BOOKS if not b.get("is_russian"))
    print(f"📦 Dataset: {DATASET_DIR}")
    print(f"📚 Books in catalogue: {len(BOOKS)} ({ru_count} RU + {en_count} EN)")
    print("🔧 Ensuring tables exist …")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:

        # 1. Wipe
        print("\n🗑  Removing all existing data …")
        for tbl in ("reading_progress", "bookmarks", "reviews",
                    "book_tags", "chapters", "books", "tags"):
            await db.execute(sa_text(f"DELETE FROM {tbl}"))
        await db.execute(sa_delete(User).where(User.role != UserRole.ADMIN))
        await db.commit()
        print("   ✓ Cleared")

        # 1b. Ensure admin user exists (preserved across re-seeds)
        print("\n👑 Ensuring admin user exists …")
        from app.core.config import settings as _s
        admin = (await db.execute(
            sa_select(User).where(User.username == _s.FIRST_ADMIN_USERNAME)
        )).scalar_one_or_none()
        if not admin:
            admin = User(
                username=_s.FIRST_ADMIN_USERNAME,
                email=_s.FIRST_ADMIN_EMAIL,
                hashed_password=hash_password(_s.FIRST_ADMIN_PASSWORD),
                display_name="Администратор",
                role=UserRole.ADMIN,
                is_active=True,
                is_verified=True,
            )
            db.add(admin)
            await db.commit()
            print(f"   ✓ Admin created: {_s.FIRST_ADMIN_USERNAME} / {_s.FIRST_ADMIN_PASSWORD}")
        else:
            print(f"   ✓ Admin already exists: {_s.FIRST_ADMIN_USERNAME}")

        # 2. Tags
        print("\n🏷  Creating tags …")
        tag_map: dict[str, Tag] = {}
        for name, slug in ALL_TAGS.items():
            t = Tag(name=name, slug=slug, usage_count=random.randint(50, 8000))
            db.add(t)
            await db.flush()
            tag_map[name] = t
        await db.commit()
        print(f"   ✓ {len(tag_map)} tags")

        # 3. Authors
        print("\n✍️  Creating authors …")
        author_map: dict[str, User] = {}
        for a in ALL_AUTHORS:
            u = User(
                username=a["username"][:50],
                email=a["email"][:255],
                hashed_password=hash_password("Author1234!"),
                display_name=a["display_name"][:100],
                bio=a["bio"],
                role=UserRole.AUTHOR,
                is_active=True,
                is_verified=True,
            )
            db.add(u)
            await db.flush()
            author_map[a["username"]] = u
        await db.commit()
        print(f"   ✓ {len(author_map)} authors")

        # 4. Readers
        print("\n📖 Creating readers …")
        readers: list[User] = []
        reader_names = [
            "Анна Морозова", "Иван Петров", "Мария Соколова", "Алексей Волков",
            "Елена Козлова", "Дмитрий Новиков", "Наташа Орлова", "Павел Белов",
            "Юлия Зайцева", "Сергей Фёдоров",
        ]
        for i, name in enumerate(reader_names):
            u = User(
                username=f"reader_{i}",
                email=f"reader{i}@lh.ru",
                hashed_password=hash_password("Reader1234!"),
                display_name=name,
                role=UserRole.READER,
                is_active=True,
                is_verified=True,
            )
            db.add(u)
            await db.flush()
            readers.append(u)
        await db.commit()
        print(f"   ✓ {len(readers)} readers")

        # 5. Books
        print(f"\n📚 Loading {len(BOOKS)} books …\n")
        all_books: list[Book] = []
        failed: list[str] = []
        used_slugs: set[str] = set()

        for bdef in BOOKS:
            title = bdef["title"]
            is_ru = bdef.get("is_russian", False)
            print(f"   📖  {title}")

            raw: str | None = None
            chs: list[dict] | None = None

            if bdef["source"] == "dataset":
                raw = load_from_dataset(bdef["dataset_path"])
                if raw:
                    raw = clean_russian_text(raw)
                    print(f"         ✓ dataset — {len(raw):,} chars")
                else:
                    print(f"         ✗ not found in dataset: {bdef['dataset_path']}")

            elif bdef["source"] == "engdb":
                chs = load_english_book(bdef["engdb_id"], max_ch=25)
                if chs:
                    total_w = sum(c["words_count"] for c in chs)
                    print(f"         ✓ engdb #{bdef['engdb_id']} — "
                          f"{len(chs)} chapters, {total_w:,} words")
                else:
                    print(f"         ✗ engdb #{bdef['engdb_id']} — not available")

            # Russian books still go through parse_chapters()
            if raw and chs is None:
                chs = parse_chapters(raw, is_russian=is_ru, max_ch=25,
                                     min_words=50 if not is_ru else 200)

            if not chs:
                print(f"         ✗ Skipping — no chapters")
                failed.append(title)
                continue
            print(f"         ✓ {len(chs)} chapters, "
                  f"{sum(c['words_count'] for c in chs):,} words")

            author = author_map.get(bdef["author_username"])
            if not author:
                print(f"         ✗ Unknown author '{bdef['author_username']}'")
                continue

            # Unique slug
            slug = make_slug(title)
            base_slug, ctr = slug, 0
            while slug in used_slugs:
                ctr += 1
                slug = f"{base_slug}-{ctr}"
            used_slugs.add(slug)

            words_total = sum(c["words_count"] for c in chs)
            book = Book(
                title=title[:295],
                slug=slug[:345],
                description=bdef["description"],
                cover_emoji=(bdef.get("cover_emoji") or "📚")[:10],
                author_id=author.id,
                genre=bdef["genre"],
                status=bdef.get("status", BookStatus.COMPLETED),
                is_published=True,
                is_adult=bdef.get("is_adult", False),
                is_featured=bdef.get("is_featured", False),
                views_count=bdef.get("views_count", 10000),
                likes_count=bdef.get("likes_count", 1000),
                bookmarks_count=random.randint(300, 6000),
                chapters_count=len(chs),
                words_count=words_total,
                rating=bdef.get("rating", 4.5),
            )
            db.add(book)
            await db.flush()

            for ch in chs:
                db.add(Chapter(
                    book_id=book.id,
                    number=ch["number"],
                    title=ch["title"][:295],
                    content=ch["content"],
                    words_count=ch["words_count"],
                    is_published=True,
                ))

            for tag_name in bdef.get("tags", []):
                t = tag_map.get(tag_name)
                if t:
                    db.add(BookTag(book_id=book.id, tag_id=t.id))

            await db.flush()
            all_books.append(book)

        await db.commit()
        skipped_msg = f" — skipped: {', '.join(failed[:6])}" if failed else ""
        print(f"\n   ✅ {len(all_books)} books saved  "
              f"({len(failed)} failed{skipped_msg})")

        # 6. Reviews
        print("\n💬 Adding reviews …")
        rev = 0
        for book in all_books:
            pool = REVIEWS_RU if book.title and any(ord(c) > 127 for c in book.title) else REVIEWS_EN
            for reader in random.sample(readers, k=random.randint(2, 6)):
                db.add(Review(
                    user_id=reader.id,
                    book_id=book.id,
                    rating=round(random.uniform(3.8, 5.0), 1),
                    text=random.choice(pool),
                    is_spoiler=False,
                ))
                rev += 1
        await db.commit()
        print(f"   ✓ {rev} reviews")

        # 7. Bookmarks
        print("\n🔖 Adding bookmarks …")
        bm = 0
        for reader in readers:
            for book in random.sample(all_books, k=min(len(all_books), random.randint(5, 14))):
                db.add(Bookmark(user_id=reader.id, book_id=book.id))
                bm += 1
        await db.commit()
        print(f"   ✓ {bm} bookmarks")

    print()
    print("=" * 65)
    print("✅  Seed complete!")
    print("=" * 65)
    ru_saved = sum(1 for b in all_books if any(ord(c) > 127 for c in b.title))
    en_saved = len(all_books) - ru_saved
    print(f"  📚  Books:    {len(all_books)}  ({ru_saved} RU + {en_saved} EN)")
    if failed:
        print(f"  ⚠️   Failed:   {len(failed)} — {', '.join(failed[:8])}")
    print(f"  ✍️   Authors:  {len(ALL_AUTHORS)}")
    print(f"  👤  Readers:  reader0@lh.ru … reader9@lh.ru / Reader1234!")
    print(f"  💬  Reviews:  {rev}")
    print()
    print("  Russian source: Kaggle 'Russian Literature' dataset")
    print("  English source: archive_eng.zip / books.db (offline)")
    print("=" * 65)

    # Mark database as seeded (read by entrypoint.sh / check_data_loaded.py)
    if _mark_seeded is not None:
        await _mark_seeded()

    # Clean up temp SQLite file
    if _ENG_DB_CONN:
        _ENG_DB_CONN.close()
    if _ENG_DB_TMP and os.path.isfile(_ENG_DB_TMP):
        try:
            os.unlink(_ENG_DB_TMP)
        except OSError:
            pass


if __name__ == "__main__":
    asyncio.run(seed())
