#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""מסלול הקריאה ל-Claude: CLI על המנוי, ו-API כגיבוי.

`claude` מזויף על ה-PATH – סקריפט שמדפיס את מה שב-FAKE_CLAUDE_OUT
ורושם אם ANTHROPIC_API_KEY דלף לסביבה שלו. בלי רשת ובלי קריאה אמיתית.
"""
import json
import os
import stat
import tempfile
from pathlib import Path

from helpers import S, Results

r = Results("מסלול Claude: CLI ראשי + API גיבוי")

tmp = Path(tempfile.mkdtemp())
leak_file = tmp / "leak"
fake = tmp / "claude"
fake.write_text(
    "#!/usr/bin/env python3\n"
    "import os, sys\n"
    "sys.stdin.read()\n"
    f"open({str(leak_file)!r}, 'w').write(str('ANTHROPIC_API_KEY' in os.environ))\n"
    "print(os.environ['FAKE_CLAUDE_OUT'])\n"
)
fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
os.environ["PATH"] = f"{tmp}{os.pathsep}{os.environ['PATH']}"


def cli_says(**data):
    base = {"type": "result", "subtype": "success", "is_error": False,
            "num_turns": 1, "duration_ms": 1000, "result": ""}
    os.environ["FAKE_CLAUDE_OUT"] = json.dumps({**base, **data})


api_calls = []


class FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {"stop_reason": "end_turn",
                "content": [{"type": "text", "text": "מה-API"}]}


def fake_post(*args, **kwargs):
    api_calls.append(kwargs.get("json"))
    return FakeResponse()


S.requests.post = fake_post


def ask():
    return S.ask_claude("שלום", model="m", effort="low",
                        max_tokens=100, timeout=30)


# 1. CLI מצליח – ה-API לא נקרא
S.ANTHROPIC_API_KEY = "sk-test"
os.environ["ANTHROPIC_API_KEY"] = "sk-test"
cli_says(result="מה-CLI")
api_calls.clear()
r.check("CLI מצליח → הטקסט מה-CLI", ask(), "מה-CLI")
r.check("CLI מצליח → אין קריאת API", str(len(api_calls)), "0")
r.check("ANTHROPIC_API_KEY לא דולף ל-CLI (אחרת היה מחייב API)",
        leak_file.read_text(), "False")

# 2. CLI נכשל (מכסה נגמרה) – נופל ל-API
cli_says(subtype="error_during_execution", is_error=True,
         result="usage limit reached")
api_calls.clear()
r.check("CLI נכשל → נופל ל-API", ask(), "מה-API")
r.check("CLI נכשל → קריאת API אחת", str(len(api_calls)), "1")

# 3. פלט שבור מה-CLI – נופל ל-API
os.environ["FAKE_CLAUDE_OUT"] = "not json"
r.check("פלט לא תקין → נופל ל-API", ask(), "מה-API")

# 4. CLI נכשל ואין מפתח API – חריגה (הקוראים תופסים אותה)
cli_says(is_error=True, subtype="error")
S.ANTHROPIC_API_KEY = ""
try:
    ask()
    got = "לא נזרקה חריגה"
except RuntimeError as e:
    got = str(e)
r.check("CLI נכשל בלי מפתח → חריגה", got, "אין מסלול זמין")

# 5. CLAUDE_BACKEND=api – מדלג על ה-CLI
S.ANTHROPIC_API_KEY = "sk-test"
S.CLAUDE_BACKEND = "api"
cli_says(result="מה-CLI")
r.check("CLAUDE_BACKEND=api → ישר ל-API", ask(), "מה-API")
S.CLAUDE_BACKEND = "auto"

# 6. רשימת המקורות של WebSearch נחתכת
news = "== חדשות שוטפות ==\n• פריט\n\nSources:\n- [a](https://x)"
r.check("strip_sources חותך Sources", repr(S.strip_sources(news)),
        repr("== חדשות שוטפות ==\n• פריט"))
r.check("strip_sources בלי מקורות – ללא שינוי",
        S.strip_sources("טקסט רגיל"), "טקסט רגיל")

# 7. בלוקים בפורמט API (כמו ב-generate_message) מאוחדים לטקסט אחד
blocks = [{"type": "text", "text": "כללים", "cache_control": {}},
          {"type": "text", "text": "נתונים"}]
r.check("content_to_text מאחד בלוקים", S.content_to_text(blocks),
        "כללים\n\nנתונים")

r.done()
