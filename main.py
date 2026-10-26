import os, json, re, datetime, html, requests

# ================== تنظیمات ==================
SUBJECT   = (os.getenv("SUBJECT") or "ریاضی")
GRADE     = (os.getenv("GRADE") or "پایه نهم")
PER_DAY   = int(os.getenv("COUNT") or 10)   # تعداد سوال در هر بار ارسال
QUESTIONS_FILE = "questions.txt"    # فایل سوال و جواب‌های خودت
STATE_FILE = "history.json"         # اینجا فقط شماره‌ی سوال بعدی ذخیره می‌شه
GENERATED_FILE = "generated_questions.txt"   # سوال‌هایی که AI ساخته (برای جلوگیری از تکرار)
TOPICS    = os.getenv("TOPICS") or ""        # مبحث/فصل، مثلاً «مجموعه‌ها و عددهای حقیقی»
LEVEL     = os.getenv("LEVEL") or "نمونه"    # کتاب | نمونه | تیزهوشان
MODE      = (os.getenv("MODE") or "bank").lower()   # bank: اول questions.txt بعد AI | ai: همیشه AI
# ============================================

import ai_client

import local_secrets as _s
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or _s.TELEGRAM_BOT_TOKEN
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID") or _s.TELEGRAM_CHAT_ID

ANSWER_RE = re.compile(r"^\s*(پاسخ|جواب)\s*[:：]", re.M)


def load_questions():
    """هر سوال با یک خط شامل --- جدا می‌شه. از اولین خطی که با «پاسخ:» شروع بشه، بخش جواب حساب می‌شه."""
    raw = open(QUESTIONS_FILE, encoding="utf-8").read()
    items = []
    for b in re.split(r"^\s*-{3,}\s*$", raw, flags=re.M):
        b = b.strip()
        if not b:
            continue
        m = ANSWER_RE.search(b)
        if m:
            q, a = b[:m.start()].strip(), b[m.start():].strip()
        else:
            q, a = b, "پاسخ برای این سوال ثبت نشده."
        items.append((q, a))
    return items


def load_cursor():
    try:
        data = json.load(open(STATE_FILE, encoding="utf-8"))
        return int(data.get("next", 0)) if isinstance(data, dict) else 0
    except Exception:
        return 0


def save_cursor(n):
    json.dump({"next": n}, open(STATE_FILE, "w", encoding="utf-8"))


def strip_number(text):
    lines = text.splitlines()
    lines[0] = re.sub(r"^\s*[\d۰-۹]+\s*[\.\-\)]\s*", "", lines[0])
    return "\n".join(lines)


def fmt(text):
    return html.escape(text).replace("\n", "<br>")


OPT_RE = re.compile(r"^\s*([1-4۱-۴]|الف|ب|ج|د|[A-Da-d])\s*[\)\-\.]\s*(.*)$")


def parse_question(q):
    """سوال رو به متن سوال و گزینه‌ها تقسیم می‌کنه."""
    stem, opts = [], []
    for line in strip_number(q).splitlines():
        m = OPT_RE.match(line)
        if m:
            opts.append([m.group(1), m.group(2)])
        elif opts:
            opts[-1][1] += " " + line.strip()
        else:
            stem.append(line)
    return "\n".join(stem).strip(), opts


def parse_answer(a):
    lines = [l.strip() for l in a.splitlines() if l.strip()]
    head = re.sub(r"^(پاسخ|جواب)\s*[:：]\s*", "", lines[0]) if lines else ""
    reason = "\n".join(lines[1:])
    reason = re.sub(r"^(دلیل|توضیح)\s*[:：]\s*", "", reason)
    return head, reason


# ---------- تاریخ شمسی ----------
MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
WEEKDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]  # بر اساس weekday() پایتون


def g2j(gy, gm, gd):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + gd + g_d_m[gm - 1]
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm, jd = 1 + days // 31, 1 + days % 31
    else:
        jm, jd = 7 + (days - 186) // 30, 1 + (days - 186) % 30
    return jy, jm, jd


def fa(n):
    return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def jalali_today():
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3, minutes=30)))
    jy, jm, jd = g2j(now.year, now.month, now.day)
    return f"{WEEKDAYS[now.weekday()]} {fa(jd)} {MONTHS[jm-1]} {fa(jy)}"


CSS = """
@page {
  size: A4; margin: 1.3cm 1.6cm 1.6cm 1.6cm;
  @bottom-left { content: "RoboRam"; font-size: 9px; color: #94a3b8; letter-spacing: 2px; }
  @bottom-right { content: counter(page); font-size: 9px; color: #94a3b8; }
}
body { font-family: 'Vazirmatn','Noto Naskh Arabic','Noto Sans Arabic','DejaVu Sans',sans-serif;
       font-size: 12px; line-height: 1.75; color: #0f172a; margin: 0; }
table { border-collapse: collapse; width: 100%; }
td { vertical-align: top; padding: 0; }
.head td { vertical-align: middle; }
.title { font-size: 21px; font-weight: bold; }
.sub { color: #64748b; font-size: 11.5px; }
.logo { height: 58px; }
.bar { height: 3px; background: #0f172a; margin: 8px 0 10px 0; }
.info { margin-bottom: 14px; }
.info td { padding: 5px 0; font-size: 11.5px; }
.line { border-bottom: 1px dashed #94a3b8; }
.lab { color: #475569; white-space: nowrap; padding-left: 6px; }
.chip { background: #0f172a; color: #fff; padding: 1px 12px; border-radius: 3px; font-weight: bold; }
.q { margin: 0 0 11px 0; page-break-inside: avoid; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px; }
.q .n { width: 24px; font-weight: bold; color: #0f172a; font-size: 13px; }
.stem { font-weight: bold; margin-bottom: 3px; }
.opts td { width: 50%; padding: 1px 0; }
.lbl { display: inline-block; width: 15px; height: 15px; line-height: 15px; text-align: center; border: 1px solid #0f172a;
       border-radius: 50%; font-size: 9px; margin-left: 5px; }
.atitle { font-size: 17px; font-weight: bold; border-right: 5px solid #0f172a; padding-right: 10px; margin-bottom: 12px; }
.a { margin-bottom: 8px; page-break-inside: avoid; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px; }
.a .n { width: 24px; font-weight: bold; }
.ahead { font-weight: bold; background: #0f172a; color: #fff; padding: 0 9px; border-radius: 3px; }
.reason { color: #334155; margin-top: 3px; }
.wm { position: fixed; top: 27%; left: 14%; width: 72%; opacity: 0.07; }
.wm img { width: 100%; }
"""


def build_pdf(items, path, start=0, total=0, subject=None, grade=None, show_day=True):
    from weasyprint import HTML
    e = html.escape
    subject, grade = subject or SUBJECT, grade or GRADE
    day = start // PER_DAY + 1
    chip = f"<span class='chip'>روز {fa(day)}</span>" if show_day else ""
    day_suffix = f" — روز {fa(day)}" if show_day else ""
    here = os.path.dirname(os.path.abspath(__file__))
    logo = "<img class='logo' src='logo.png'>" if os.path.exists(os.path.join(here, "logo.png")) else ""

    body = (f"<table class='head'><tr><td><div class='title'>آزمون {e(subject)}</div>"
            f"<div class='sub'>{e(grade)} &nbsp;|&nbsp; {e(jalali_today())}</div></td>"
            f"<td style='text-align:left'>{logo}</td></tr></table><div class='bar'></div>"
            f"<table class='info'><tr>"
            f"<td class='lab' style='width:1%'>نام و نام‌خانوادگی:</td><td class='line' style='width:55%'>&nbsp;</td>"
            f"<td style='text-align:left'>{chip}</td></tr></table>")

    for i, (q, _) in enumerate(items, 1):
        stem, opts = parse_question(q)
        cells = [f"<td><span class='lbl'>{e(fa(l) if l.isdigit() else l)}</span>{e(t)}</td>" for l, t in opts]
        rows = ""
        for k in range(0, len(cells), 2):
            pair = cells[k:k + 2]
            if len(pair) == 1:
                pair.append("<td></td>")
            rows += "<tr>" + "".join(pair) + "</tr>"
        otable = f"<table class='opts'>{rows}</table>" if rows else ""
        body += (f"<div class='q'><table><tr><td class='n'>{fa(i)}.</td>"
                 f"<td><div class='stem'>{fmt(stem)}</div>{otable}</td></tr></table></div>")

    body += (f"<div style='page-break-before:always'></div><div class='atitle'>پاسخنامه{day_suffix}</div>")
    for i, (_, a) in enumerate(items, 1):
        head, reason = parse_answer(a)
        r = f"<div class='reason'>{fmt(reason)}</div>" if reason else ""
        body += (f"<div class='a'><table><tr><td class='n'>{fa(i)}.</td>"
                 f"<td><span class='ahead'>{e(head)}</span>{r}</td></tr></table></div>")

    wm = "<div class='wm'><img src='logo.png'></div>" if logo else ""
    doc = f"<html dir='rtl'><head><meta charset='utf-8'><style>{CSS}</style></head><body>{body}{wm}</body></html>"
    HTML(string=doc, base_url=here + "/").write_pdf(path)


def tg(method, **kw):
    r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", timeout=120, **kw)
    r.raise_for_status()


def send_pdf(path, caption=""):
    global CHAT_ID
    if not CHAT_ID:
        CHAT_ID = find_chat_id()
    with open(path, "rb") as f:
        tg("sendDocument", data={"chat_id": CHAT_ID, "caption": caption}, files={"document": f})


def find_chat_id():
    r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates", timeout=60)
    r.raise_for_status()
    for upd in reversed(r.json().get("result", [])):
        msg = upd.get("message") or upd.get("edited_message")
        if msg:
            return str(msg["chat"]["id"])
    raise RuntimeError("اول توی تلگرام به باتت پیام Start بده، بعد دوباره اجرا کن.")


def main():
    global CHAT_ID
    if not CHAT_ID:
        CHAT_ID = find_chat_id()

    all_q = load_questions()
    cur = load_cursor()
    # AI وقتی وارد می‌شه که MODE=ai باشه یا سوال‌های فایل تموم شده باشن
    use_ai = MODE == "ai" or cur >= len(all_q)
    if use_ai and not ai_client.available():
        if MODE == "ai":
            raise RuntimeError("MODE=ai است ولی AVALAI_API_KEY تنظیم نشده.")
        tg("sendMessage", data={"chat_id": CHAT_ID, "text": "✅ همه‌ی سوال‌های فایل تموم شد! از اول شروع می‌کنم. (برای ساخت سوال تازه با AI، کلید AVALAI_API_KEY رو توی Secrets بذار.)"})
        cur, use_ai = 0, False
    if not all_q and not use_ai:
        raise RuntimeError("فایل questions.txt خالیه!")

    if use_ai:
        import question_gen
        items = question_gen.generate(SUBJECT, GRADE, TOPICS, PER_DAY, LEVEL,
                                      bank_paths=(QUESTIONS_FILE, GENERATED_FILE))
        if not items:
            raise RuntimeError("AI نتونست سوال معتبر بسازه؛ دوباره اجرا کن.")
        intro = (f"⏰ وقت تست حل کردنه!\nدرس: {SUBJECT}\nسطح: {question_gen.level_title(LEVEL)}\n"
                 f"{len(items)} سوال تازه که امروز ساخته و دوباره بازبینی شد 👇")
        show_day, start = False, 0
    else:
        items = all_q[cur: cur + PER_DAY]
        end = cur + len(items)
        intro = (f"⏰ وقت تست حل کردنه!\nدرس: {SUBJECT}\nروز {cur // PER_DAY + 1} "
                 f"(سوال‌های {cur+1} تا {end} از {len(all_q)})\nتا چند لحظه دیگه می‌رسن 👇")
        show_day, start = True, cur

    tg("sendMessage", data={"chat_id": CHAT_ID, "text": intro})
    pdf_path = f"tests-{datetime.date.today().isoformat()}.pdf"
    build_pdf(items, pdf_path, start, len(all_q), show_day=show_day)
    with open(pdf_path, "rb") as f:
        tg("sendDocument", data={"chat_id": CHAT_ID, "caption": f"{len(items)} تست امروز ✅"}, files={"document": f})
    if use_ai:
        question_gen.save_generated(items, GENERATED_FILE)
    else:
        save_cursor(end)


if __name__ == "__main__":
    main()
