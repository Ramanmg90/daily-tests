"""اتصال به AvalAI (همون روشی که توی چت‌بات RoboRam استفاده می‌شد)."""
import os
import time

MODEL = os.getenv("AI_MODEL") or "gpt-6-astra"
BASE_URL = os.getenv("AI_BASE_URL") or "https://api.avalai.ir/v1"

_client = None


def _key():
    k = os.getenv("AVALAI_API_KEY")
    if k:
        return k
    try:  # برای اجرای لوکال: می‌تونی AVALAI_API_KEY رو توی local_secrets.py هم بذاری
        import local_secrets as s
        return getattr(s, "AVALAI_API_KEY", "") or ""
    except Exception:
        return ""


def available():
    return bool(_key())


def client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(api_key=_key(), base_url=BASE_URL)
    return _client


def ask(messages, retries=3):
    """messages: لیستی از {"role","content"}؛ متن پاسخ رو برمی‌گردونه. خطاهای موقتی رو دوباره امتحان می‌کنه."""
    last = None
    for i in range(retries):
        try:
            r = client().responses.create(model=MODEL, input=messages)
            return r.output_text
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"درخواست به AI ناموفق بود: {last}")
