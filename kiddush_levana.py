#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kiddush_levana.py – מודול קידוש לבנה דטרמיניסטי

לוגיקה: 4 הודעות בחודש בלבד (3 בתשרי/אב).
  1. ערב פתיחת אשכנזים         → אשכנזים ✅, ספרדים מליל X
  2. למחרת                     → אשכנזים ✅, ספרדים מליל X (תזכורת)
  3. ערב פתיחת ספרדים           → שניהם ✅
  4. הלילה האחרון               → הזדמנות אחרונה!

עיקרון: "הלילה" = הערב של today.
  ליל X (עברי) מתחיל בערב X-1 (לועזי) — אלא אם הפתיחה כבר בערב.
  באב (מוצאי ט"ב 21:00) ובתשרי (מוצאי יו"כ 20:30) — לא מזיזים.
"""

import json
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional
import pytz

ISRAEL_TZ = pytz.timezone("Asia/Jerusalem")

_CALENDAR_FILE = Path(__file__).parent / "kiddush_levana.json"
_CALENDAR = None


def _load_calendar() -> list[dict]:
    global _CALENDAR
    if _CALENDAR is None:
        with open(_CALENDAR_FILE, "r", encoding="utf-8") as f:
            _CALENDAR = json.load(f)["months"]
    return _CALENDAR


def _parse_dt(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=ISRAEL_TZ)


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _evening_of(dt: datetime) -> date:
    """
    מחזיר את התאריך הלועזי שבערבו מתחיל הלילה.
    אם השעה >= 20 → הערב כבר התחיל → אותו יום.
    אם השעה < 20 → הלילה הזה התחיל אתמול בערב → יום קודם.
    """
    if dt.hour >= 20:
        return dt.date()
    else:
        return dt.date() - timedelta(days=1)


def _find_entry(today: date) -> Optional[dict]:
    for e in _load_calendar():
        ash_eve = _evening_of(_parse_dt(e["ashkenaz_open"]))
        last = _parse_date(e["last_night"])
        if ash_eve <= today <= last:
            return e
    return None


def get_kiddush_levana_text(now: Optional[datetime] = None) -> Optional[str]:
    if now is None:
        now = datetime.now(ISRAEL_TZ)

    today = now.date()
    entry = _find_entry(today)
    if entry is None:
        return None

    ash_evening = _evening_of(_parse_dt(entry["ashkenaz_open"]))
    sep_evening = _evening_of(_parse_dt(entry["sephardic_open"]))
    last_date   = _parse_date(entry["last_night"])

    sep_display = _parse_dt(entry["sephardic_open"]).date()
    sep_night   = f"ליל {sep_display.strftime('%d/%m')}"

    # ── הודעה 3: הלילה האחרון (עדיפות עליונה) ──
    if today == last_date:
        return (
            "*קידוש לבנה / ברכת הלבנה:*\n"
            "*שימו לב!* – הלילה הזדמנות אחרונה!"
        )

    # ── הודעה 2: ספרדים נפתחים ──
    if today == sep_evening:
        return (
            "*קידוש לבנה / ברכת הלבנה:*\n"
            "אשכנזים וספרדים – אפשר לומר הלילה ✅"
        )

    # ── הודעה 1: אשכנזים (ערב פתיחה + למחרת) ──
    if today == ash_evening or today == ash_evening + timedelta(days=1):
        # תשרי/אב: ספרדים פתוחים באותו זמן → הודעה 2
        if sep_evening <= today:
            return (
                "*קידוש לבנה / ברכת הלבנה:*\n"
                "אשכנזים וספרדים – אפשר לומר הלילה ✅"
            )
        return (
            "*קידוש לבנה / ברכת הלבנה:*\n"
            f"*אשכנזים* – אפשר לומר הלילה ✅\n"
            f"*ספרדים* – החל מ{sep_night}"
        )

    return None


if __name__ == "__main__":
    now = datetime.now(ISRAEL_TZ)
    print(f"עכשיו: {now.strftime('%d/%m/%Y %H:%M')}\n")
    text = get_kiddush_levana_text(now)
    print(text if text else "(שתיקה)")
