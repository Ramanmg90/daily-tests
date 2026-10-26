"""
ساخت سوال تستی در سطح پایه و مدارس خاص (نمونه دولتی / تیزهوشان) با هوش مصنوعی.

مسیر هر سوال:
  1) تولید  ->  2) بررسی ساختار  ->  3) حذف تکراری (نسبت به questions.txt و سوال‌های قبلاً ساخته‌شده)
  4) حل مستقل توسط یک «حل‌کننده‌ی» جدا که جواب رو نمی‌بینه  ->  فقط سوالی می‌مونه که
     جوابش با کلید یکی باشه، فقط یک گزینه‌ی درست داشته باشه و سختی‌ش توی بازه‌ی سطح انتخاب‌شده باشه
  5) جابه‌جایی تصادفی گزینه‌ها (که جواب همیشه گزینه‌ی ۲ و ۳ نباشه)
"""
import difflib
import json
import random
import re

import ai_client

# ---------------------------------------------------------------- سطح‌ها
LEVELS = {
    "کتاب": {
        "title": "سطح کتاب درسی",
        "range": (1, 3),
        "rubric": (
            "سوال‌ها در حد مثال‌ها و تمرین‌های کتاب درسی باشند. حدود ۴۰٪ ساده و مستقیم، "
            "۴۰٪ متوسط (یک یا دو مرحله حل) و ۲۰٪ کمی چالشی."
        ),
    },
    "نمونه": {
        "title": "مدارس نمونه دولتی",
        "range": (2, 4),
        "rubric": (
            "در حد آزمون‌های ورودی و کلاس‌های ممتاز مدارس نمونه دولتی: ترکیب دو مفهوم، "
            "نیاز به ۲ تا ۳ مرحله استدلال یا محاسبه، دام‌های رایج (خطاهای مشهور دانش‌آموزان). "
            "حدود ۳۰٪ متوسط و ۷۰٪ دشوار. سوال صرفاً حفظی یا تک‌مرحله‌ای ننویس."
        ),
    },
    "تیزهوشان": {
        "title": "مدارس تیزهوشان (سمپاد)",
        "range": (3, 5),
        "rubric": (
            "در حد آزمون ورودی مدارس تیزهوشان: مسئله‌های خلاقانه و چندمرحله‌ای، ترکیب چند مفهوم و پیش‌نیاز، "
            "الگویابی، استدلال منطقی یا یک ایده‌ی هوشمندانه به‌جای محاسبه‌ی صرف؛ "
            "ولی همچنان در چارچوب مفاهیم همین پایه (نه سطح المپیاد). حدود ۲۰٪ متوسط‌به‌بالا و ۸۰٪ دشوار."
        ),
    },
}

ALIASES = {
    "کتاب": "کتاب", "کتاب درسی": "کتاب", "عادی": "کتاب", "معمولی": "کتاب",
    "نمونه": "نمونه", "نمونه دولتی": "نمونه", "نمونه‌دولتی": "نمونه",
    "تیزهوشان": "تیزهوشان", "تیزهوش": "تیزهوشان", "سمپاد": "تیزهوشان",
}


def norm_level(s):
    s = (s or "").strip()
    if not s:
        return "نمونه"
    if s in ALIASES:
        return ALIASES[s]
    raise ValueError(f"سطح «{s}» رو نمی‌شناسم. سطح‌ها: کتاب، نمونه، تیزهوشان")


def level_title(level):
    return LEVELS[norm_level(level)]["title"]


# ---------------------------------------------------------------- فایل سوال‌ها
def split_blocks(raw):
    return [b.strip() for b in re.split(r"^\s*-{3,}\s*$", raw, flags=re.M) if b.strip()]


ANSWER_RE = re.compile(r"^\s*(پاسخ|جواب)\s*[:：]", re.M)


def load_bank(*paths):
    """سوال‌های موجود (questions.txt و generated_questions.txt) -> [(q, a)]"""
    items = []
    for p in paths:
        try:
            raw = open(p, encoding="utf-8").read()
        except FileNotFoundError:
            continue
        for b in split_blocks(raw):
            m = ANSWER_RE.search(b)
            items.append((b[:m.start()].strip(), b[m.start():].strip()) if m else (b, ""))
    return items


def save_generated(items, path):
    """سوال‌های ساخته‌شده رو ته فایل اضافه می‌کنه تا دفعه‌ی بعد تکراری نسازه."""
    with open(path, "a", encoding="utf-8") as f:
        for q, a in items:
            f.write(f"{q}\n{a}\n---\n")


# ---------------------------------------------------------------- کمک‌ها
def extract_json(text):
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S).strip()
    starts = [i for i in (t.find("["), t.find("{")) if i != -1]
    if not starts:
        raise ValueError("JSON توی پاسخ پیدا نشد")
    s = min(starts)
    e = t.rfind("]" if t[s] == "[" else "}")
    if e <= s:
        raise ValueError("JSON ناقص بود")
    return json.loads(t[s:e + 1])


_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩يك", "01234567890123456789یک")


def _norm(s):
    return re.sub(r"[\W_]+", "", s.translate(_DIGITS))


def _question_text(c):
    return c["stem"] + "\n" + "\n".join(f"{i}) {o}" for i, o in enumerate(c["options"], 1))


def _is_dup(fp, seen, thr=0.9):
    for s in seen:
        if fp == s or difflib.SequenceMatcher(None, fp, s).ratio() >= thr:
            return True
    return False


def _clean(x):
    """ساختار یک سوال رو چک و تمیز می‌کنه؛ اگه خراب بود None."""
    try:
        stem = re.sub(r"^\s*-{3,}\s*$", "", str(x["stem"]), flags=re.M).strip()
        opts = [str(o).strip() for o in x["options"]]
        ans = int(x["answer"])
        expl = str(x.get("explanation", "")).strip()
    except Exception:  # noqa: BLE001
        return None
    if len(stem) < 10 or len(opts) != 4 or not all(opts) or not 1 <= ans <= 4 or not expl:
        return None
    if len({_norm(o) for o in opts}) != 4:  # گزینه‌ی تکراری
        return None
    return {"stem": stem, "options": opts, "answer": ans, "explanation": expl}


META = re.compile(r"(همه|هیچ|هر\s*دو|هر\s*سه|هر\s*چهار|موارد|گزینه)")


def _shuffle(c):
    """اگه گزینه‌ها به هم ارجاع ندارن («همه‌ی موارد» و ...)، جای‌شون رو عوض می‌کنه."""
    if any(META.search(o) for o in c["options"]):
        return c
    idx = list(range(4))
    random.shuffle(idx)
    return {**c, "options": [c["options"][i] for i in idx], "answer": idx.index(c["answer"] - 1) + 1}


def _to_text(c):
    return _question_text(c), f"پاسخ: گزینه {c['answer']}\nدلیل: {c['explanation']}"


# ---------------------------------------------------------------- پرامپت‌ها
GEN_SYSTEM = """تو یک طراح سوال باتجربه‌ی آزمون‌های مدارس خاص ایران (نمونه دولتی و تیزهوشان) و دبیر ارشد درس «{subject}» هستی.
قانون‌هایی که همیشه رعایت می‌کنی:
1. فقط از مباحث «{grade}» و پیش‌نیازهای مستقیمش سوال بساز. مبحث خواسته‌شده رو رعایت کن.
2. هر سوال ۴ گزینه دارد و دقیقاً یکی از گزینه‌ها درست است. سوال نباید ابهام یا داده‌ی ناقص داشته باشد.
3. گزینه‌های غلط باید از «خطاهای واقعی و رایج دانش‌آموزان» ساخته شوند (مثلاً اشتباه علامت، فراموش کردن یک حالت، خلط دو مفهوم)، نه گزینه‌های بی‌ربط.
4. گزینه‌ها هم‌سبک و هم‌طول باشند تا جواب از روی ظاهر قابل حدس نباشد. از «همه‌ی موارد» و «هیچ‌کدام» فقط در موارد واقعاً لازم استفاده کن.
5. چون خروجی در PDF متنی چاپ می‌شود: فرمول‌ها را با نماد ساده بنویس (x² ، √ ، ÷ ، × ، a/b ، ≤ ، ∈ ، ∪ ، ∩) و هرگز LaTeX ننویس. ارقام را لاتین بنویس.
6. هیچ سوالی ننویس که به شکل، نمودار یا جدول تصویری نیاز دارد. شکل‌های هندسی را کامل با کلمات توصیف کن.
7. اگر سوال چند گزاره دارد، گزاره‌ها را با «•» شروع کن؛ هرگز با «الف)»، «ب)»، «1)» شماره‌گذاری نکن (این‌ها برای گزینه‌هاست).
8. «explanation» یک راه‌حل کوتاه و دقیق مرحله‌به‌مرحله است که حتماً با گزینه‌ی درست سازگار باشد.
9. سوال‌هایی که قبلاً ساخته شده را تکرار نکن و تنوع مهارتی داشته باش (محاسبه، استدلال، تشخیص خطا، مسئله‌ی کلامی، الگویابی و ...).
10. خروجی فقط یک آرایه‌ی JSON است، بدون هیچ متن اضافه و بدون ```."""

GEN_USER = """درس: {subject}
پایه: {grade}
مبحث: {topic}
سطح: {level_title}
راهنمای سختی: {rubric}

تعداد سوال: {n}

نمونه‌هایی از قالب و لحن سوال‌های این پروژه (فقط برای سبک نوشتن، نه برای سختی یا موضوع):
{examples}

سوال‌هایی که از قبل داریم و نباید تکرارشان کنی (فقط ابتدای هر کدام):
{avoid}

خروجی دقیقاً با این ساختار:
[{{"stem": "متن سوال", "options": ["گزینه ۱", "گزینه ۲", "گزینه ۳", "گزینه ۴"], "answer": 1 تا 4, "explanation": "راه‌حل کوتاه", "skill": "مهارت اصلی سوال"}}]"""

VERIFY_SYSTEM = """تو یک معلم و حل‌کننده‌ی مستقل هستی. چند سوال تستی بدون کلید به تو داده می‌شود.
هر سوال را از صفر و دقیق حل کن، بدون این‌که به هیچ فرضی اعتماد کنی. سپس برای هر سوال داوری کن:
- answer: شماره‌ی گزینه‌ای که خودت درست می‌دانی (اگر هیچ گزینه‌ای درست نیست 0؛ اگر بیش از یک گزینه درست است همان یکی از آن‌ها را بنویس و ok را false بگذار)
- ok: فقط وقتی true باشد که سوال بی‌ابهام است، داده‌ی کافی دارد و دقیقاً یک گزینه درست است
- grade_fit: آیا سوال از مباحث همان پایه (و پیش‌نیازهای مستقیمش) است؟
- difficulty: عدد 1 تا 5 — 1: مستقیم/حفظی، 2: کاربرد یک‌مرحله‌ای، 3: دو مرحله یا ترکیب دو مفهوم، 4: چندمرحله با دام یا ایده‌ی هوشمندانه، 5: در حد المپیاد
- issue: اگر ایرادی هست یک جمله بنویس، وگرنه رشته‌ی خالی
خروجی فقط آرایه‌ی JSON، به ترتیب این کلیدها (ابتدا work برای حل خلاصه و بعد بقیه):
[{"n": 1, "work": "حل خلاصه", "answer": 2, "ok": true, "grade_fit": true, "difficulty": 3, "issue": ""}]"""


# ---------------------------------------------------------------- مراحل
def _prompt_generate(subject, grade, topic, level_key, n, bank):
    L = LEVELS[level_key]
    pool = [q for q, _ in bank]
    ex = random.sample(pool, min(3, len(pool)))
    avoid = random.sample(pool, min(25, len(pool)))
    return [
        {"role": "system", "content": GEN_SYSTEM.format(subject=subject, grade=grade)},
        {"role": "user", "content": GEN_USER.format(
            subject=subject, grade=grade, topic=topic or "کل کتاب (مباحث متنوع)",
            level_title=L["title"], rubric=L["rubric"], n=n,
            examples="\n\n".join(ex) if ex else "(نمونه‌ای موجود نیست)",
            avoid="\n".join("- " + a.splitlines()[0][:80] for a in avoid) if avoid else "(چیزی موجود نیست)",
        )},
    ]


def _verify(chunk, subject, grade, level_key):
    """یک دسته سوال رو به حل‌کننده‌ی مستقل می‌ده. [True/False] به ترتیب برمی‌گردونه."""
    lo, hi = LEVELS[level_key]["range"]
    listing = "\n\n".join(
        f"سوال {i}:\n{c['stem']}\n" + "\n".join(f"{j}) {o}" for j, o in enumerate(c["options"], 1))
        for i, c in enumerate(chunk, 1)
    )
    raw = ai_client.ask([
        {"role": "system", "content": VERIFY_SYSTEM},
        {"role": "user", "content": f"درس: {subject}\nپایه: {grade}\n\n{listing}"},
    ])
    verdict = {int(d["n"]): d for d in extract_json(raw)}
    res, why = [], []
    for i, c in enumerate(chunk, 1):
        v = verdict.get(i)
        try:
            ok = (v is not None and bool(v.get("ok")) and bool(v.get("grade_fit", True))
                  and int(v["answer"]) == c["answer"] and lo <= int(v["difficulty"]) <= hi)
        except Exception:  # noqa: BLE001
            ok = False
        res.append(ok)
        if not ok:
            why.append((v or {}).get("issue") or "جواب یا سطح نخورد")
    return res, why


def generate(subject, grade, topic="", count=10, level="نمونه", bank_paths=(), log=print, max_rounds=5):
    """
    count سوال معتبر می‌سازه و به شکل [(متن_سوال_با_گزینه‌ها, "پاسخ: گزینه N\\nدلیل: ...")] برمی‌گردونه
    (همون قالب questions.txt). اگه بعد از max_rounds دور به تعداد نرسید، همون‌هایی که تأیید شدن رو برمی‌گردونه.
    """
    level_key = norm_level(level)
    bank = load_bank(*bank_paths)
    seen = [_norm(q) for q, _ in bank]
    accepted, stats = [], {"تکراری": 0, "ساختار خراب": 0, "رد در بازبینی": 0}

    for rnd in range(1, max_rounds + 1):
        need = count - len(accepted)
        if need <= 0:
            break
        n = min(need + 2, 8)  # دسته‌ی کوچک‌تر = کیفیت بالاتر
        log(f"دور {rnd}: درخواست {n} سوال (تأییدشده تا الان: {len(accepted)}/{count})")
        try:
            raw = ai_client.ask(_prompt_generate(subject, grade, topic, level_key, n, bank + [
                (_question_text(c), "") for c in accepted]))
            cands = extract_json(raw)
            if isinstance(cands, dict):
                cands = cands.get("questions", [])
        except Exception as e:  # noqa: BLE001
            log(f"  خطا در تولید: {e}")
            continue

        fresh = []
        for x in cands:
            c = _clean(x)
            if not c:
                stats["ساختار خراب"] += 1
                continue
            fp = _norm(_question_text(c))
            if _is_dup(fp, seen):
                stats["تکراری"] += 1
                continue
            fresh.append((c, fp))

        for k in range(0, len(fresh), 5):
            chunk = fresh[k:k + 5]
            try:
                res, why = _verify([c for c, _ in chunk], subject, grade, level_key)
            except Exception as e:  # noqa: BLE001
                log(f"  بازبینی ناموفق بود، این دسته کنار گذاشته شد: {e}")
                stats["رد در بازبینی"] += len(chunk)
                continue
            for (c, fp), ok in zip(chunk, res):
                if ok and len(accepted) < count:
                    accepted.append(c)
                    seen.append(fp)
                elif not ok:
                    stats["رد در بازبینی"] += 1
            for w in why:
                log(f"  ردشد: {w}")

    log(f"خلاصه: {len(accepted)}/{count} سوال تأیید شد | {stats}")
    return [_to_text(_shuffle(c)) for c in accepted]
