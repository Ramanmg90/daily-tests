"""
RoboRam: همون چت‌بات قبلی + ساخت آزمون در سطح مدارس خاص.

اجرا:  python roboram.py
"""
import datetime
import os
import re

import ai_client
import question_gen
import main as dt          # PDF ساز و ارسال تلگرام پروژه‌ی تست روزانه

OUT_DIR = "output"

SYSTEM = (
    "تو RoboRam هستی، یک دستیار هوش مصنوعی فارسی‌زبان. "
    "صمیمی، دقیق و کاربردی پاسخ بده. "
    "تو می‌تونی آزمون تستی در سطح پایه‌ها و مدارس خاص (نمونه دولتی و تیزهوشان) بسازی؛ "
    "کاربر با دستور /test یا با گفتن «برام تست بساز» این کار رو شروع می‌کنه. "
    "وقتی آزمونی ساخته می‌شه متنش با پاسخ‌ها توی همین گفتگو برای تو ثبت می‌شه و می‌تونی درباره‌ش توضیح بدی."
)

HELP = """
دستورها:
  /test                  ساخت آزمون با پرسش قدم‌به‌قدم
  /test درس | پایه | مبحث | سطح | تعداد
        مثال:  /test ریاضی | نهم | مجموعه‌ها | تیزهوشان | 10
  /help                  همین راهنما
  exit                   خروج
سطح‌ها: کتاب  |  نمونه (نمونه دولتی)  |  تیزهوشان (سمپاد)
یا ساده بنویس: «۱۰ تا تست ریاضی نهم از فصل مجموعه‌ها در سطح تیزهوشان بساز»
"""

INTENT_RE = re.compile(
    r"(تست|آزمون|امتحان|سوال|سؤال).*(بساز|طراحی|درست کن|بنویس|بده)"
    r"|(بساز|طراحی کن|درست کن).*(تست|آزمون|امتحان|سوال|سؤال)"
)

EXTRACT_PROMPT = """از پیام کاربر مشخصات آزمون رو در قالب JSON دربیار. فقط JSON بده، بدون متن اضافه.
کلیدها: subject (درس)، grade (پایه، مثل «نهم»)، topic (مبحث/فصل یا رشته‌ی خالی)،
level (یکی از: کتاب، نمونه، تیزهوشان؛ اگه نگفته رشته‌ی خالی)، count (عدد؛ اگه نگفته 0).
اگه چیزی گفته نشده، رشته‌ی خالی بگذار؛ چیزی از خودت اضافه نکن.
پیام کاربر: """


def ask_field(label, default):
    v = input(f"  {label} [{default}]: ").strip()
    return v or default


def parse_pipe_args(arg):
    p = [x.strip() for x in arg.split("|")] + [""] * 5
    return p[:5]


def to_count(x, default=10):
    try:
        n = int(str(x).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")))
    except ValueError:
        n = 0
    return max(1, min(n or default, 20))


def make_test(subject, grade, topic, level, count, messages):
    try:
        level_key = question_gen.norm_level(level)
    except ValueError as e:
        print(f"\nRoboRam: {e}")
        return

    title = question_gen.level_title(level_key)
    print(f"\nRoboRam: دارم {count} سوال «{subject} {grade}» در سطح «{title}» می‌سازم.")
    print("   (هر سوال بعد از ساخت، توسط یه حل‌کننده‌ی مستقل دوباره حل و چک می‌شه؛ ممکنه چند دقیقه طول بکشه)")
    items = question_gen.generate(
        subject, grade, topic, count, level_key,
        bank_paths=(dt.QUESTIONS_FILE, dt.GENERATED_FILE),
        log=lambda m: print("   ·", m),
    )
    if not items:
        print("RoboRam: نتونستم سوال معتبر بسازم؛ یه بار دیگه امتحان کن یا مبحث رو دقیق‌تر بگو.")
        return
    if len(items) < count:
        print(f"RoboRam: فقط {len(items)} سوال از {count} تا از بازبینی رد شد؛ بقیه رو کنار گذاشتم تا سوال بد توی آزمون نباشه.")

    question_gen.save_generated(items, dt.GENERATED_FILE)
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    base, k = os.path.join(OUT_DIR, f"test-{stamp}"), 1
    while os.path.exists(base + ".txt"):      # دو آزمون توی یک ثانیه روی هم نوشته نشن
        k += 1
        base = os.path.join(OUT_DIR, f"test-{stamp}-{k}")

    full_text = "\n---\n".join(f"{q}\n{a}" for q, a in items)
    with open(base + ".txt", "w", encoding="utf-8") as f:
        f.write(full_text + "\n")

    pdf_path = base + ".pdf"
    try:
        dt.build_pdf(items, pdf_path, subject=subject, grade=grade, show_day=False)
        print(f"\nRoboRam: آماده شد ✅\n   PDF: {pdf_path}\n   متن: {base}.txt")
    except (ImportError, OSError) as e:
        pdf_path = None
        print(f"\nRoboRam: سوال‌ها ساخته شد ✅ ولی ساخت PDF نشد ({e}).\n"
              f"   متن: {base}.txt\n   برای PDF: pip install weasyprint")

    if pdf_path and dt.BOT_TOKEN:
        if input("   بفرستمش توی تلگرام؟ (بله/نه): ").strip().lower() in ("بله", "آره", "y", "yes"):
            try:
                dt.send_pdf(pdf_path, f"{len(items)} تست {subject} {grade} ({title})")
                print("   ارسال شد 📨")
            except Exception as e:  # noqa: BLE001
                print(f"   ارسال نشد: {e}")

    # سوال‌ها توی حافظه‌ی گفتگو می‌رن تا بشه ازش‌شون پرسید («سوال ۳ رو توضیح بده»)
    messages.append({"role": "user", "content": f"یه آزمون {subject} {grade} (مبحث: {topic or 'کلی'}) در سطح {title} برام ساختی."})
    messages.append({"role": "assistant", "content": "این آزمونیه که ساخته شد (با پاسخ‌ها):\n" + full_text})


def handle_test_command(arg, messages):
    if arg:
        s, g, t, lv, c = parse_pipe_args(arg)
        subject, grade = s or dt.SUBJECT, g or dt.GRADE
        topic, level, count = t or dt.TOPICS, lv or dt.LEVEL, to_count(c)
    else:
        print("\nRoboRam: چند تا سوال لازم دارم (Enter = مقدار پیش‌فرض)")
        subject = ask_field("درس", dt.SUBJECT)
        grade = ask_field("پایه", dt.GRADE)
        topic = ask_field("مبحث/فصل (خالی = کل کتاب)", dt.TOPICS or "-")
        topic = "" if topic == "-" else topic
        level = ask_field("سطح (کتاب / نمونه / تیزهوشان)", dt.LEVEL)
        count = to_count(ask_field("تعداد", "10"))
    make_test(subject, grade, topic, level, count, messages)


def handle_natural_request(text, messages):
    """«۱۰ تا تست ریاضی نهم بساز» -> مشخصات رو درمیاره، تأیید می‌گیره، می‌سازه. True یعنی رسیدگی شد."""
    try:
        data = question_gen.extract_json(ai_client.ask(
            [{"role": "user", "content": EXTRACT_PROMPT + text}], retries=2))
        if not isinstance(data, dict):
            return False
    except Exception:  # noqa: BLE001
        return False

    subject = (data.get("subject") or "").strip() or dt.SUBJECT
    grade = (data.get("grade") or "").strip() or dt.GRADE
    topic = (data.get("topic") or "").strip() or dt.TOPICS
    level = (data.get("level") or "").strip() or dt.LEVEL
    count = to_count(data.get("count"))
    try:
        level_title = question_gen.level_title(level)
    except ValueError:
        level, level_title = dt.LEVEL, question_gen.level_title(dt.LEVEL)

    print(f"\nRoboRam: برداشتم اینه → درس: {subject} | پایه: {grade} | مبحث: {topic or 'کلی'} | سطح: {level_title} | تعداد: {count}")
    if input("   درسته؟ (بله/نه): ").strip().lower() not in ("بله", "آره", "درسته", "y", "yes"):
        print("RoboRam: باشه؛ با /test دقیق‌تر وارد کن یا دوباره توضیح بده.")
        return True
    make_test(subject, grade, topic, level, count, messages)
    return True


def main():
    if not ai_client.available():
        raise SystemExit("متغیر محیطی AVALAI_API_KEY تنظیم نشده.")

    messages = [{"role": "system", "content": SYSTEM}]

    print("=" * 40)
    print("       RoboRam AI 🤖")
    print("برای خروج بنویس exit  |  راهنما: /help")
    print("=" * 40)

    while True:
        try:
            user_input = input("\nشما: ").strip()

            if user_input.lower() == "exit":
                print("RoboRam: خداحافظ! 👋")
                break
            if not user_input:
                continue
            if user_input in ("/help", "راهنما"):
                print(HELP)
                continue
            if user_input.startswith("/test"):
                handle_test_command(user_input[5:].strip(), messages)
                continue
            if INTENT_RE.search(user_input) and handle_natural_request(user_input, messages):
                continue

            messages.append({"role": "user", "content": user_input})
            answer = ai_client.ask(messages, retries=2)
            print(f"\nRoboRam: {answer}")
            messages.append({"role": "assistant", "content": answer})

        except KeyboardInterrupt:
            print("\nبرنامه بسته شد.")
            break

        except Exception as error:  # noqa: BLE001
            print(f"\nخطا: {error}")
            if messages and messages[-1]["role"] == "user":
                messages.pop()


if __name__ == "__main__":
    main()
