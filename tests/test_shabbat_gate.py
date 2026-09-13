#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
בדיקות לשער השבת/חג (shabbat_status) ולהחלטת השליחה שנגזרת ממנו.

הרקע: עד 12.9.2026 ריצת הערב לא נבדקה כלל מול הלוח, מתוך הנחה שהיא נופלת
ממילא אחרי צאת השבת. ההנחה נשברת בחג דו-יומי המחובר לשבת. הבדיקות מזייפות
את תשובות Hebcal, כי אין תלות ברשת בזמן בדיקה.
"""
from datetime import date

from helpers import S, Results, at, freeze

# אירועי Hebcal בקירוב מציאותי (ישראל, m=50, שעון קיץ UTC+3)
EVENTS = [
    ("2026-09-04T18:39:00+03:00", "candles"),    # ערב שבת רגילה
    ("2026-09-05T19:48:00+03:00", "havdalah"),   # מוצאי שבת רגילה
    ("2026-09-11T18:30:00+03:00", "candles"),    # ערב ר"ה (שישי)
    ("2026-09-12T19:40:00+03:00", "candles"),    # ליל ר"ה ב' – בלי הבדלה
    ("2026-09-13T19:38:00+03:00", "havdalah"),   # מוצאי ר"ה (ראשון)
    ("2027-07-02T19:34:00+03:00", "candles"),    # שבת הקיץ המאוחרת בשנה
    ("2027-07-03T20:47:00+03:00", "havdalah"),
]


class FakeResponse:
    def __init__(self, items):
        self._items = items

    def json(self):
        return {"items": self._items}


def fake_get(url, timeout=10):
    """מדמה את /shabbat של Hebcal: מחזיר אירועים בטווח ±2 ימים מהתאריך."""
    assert "hebcal.com/shabbat" in url, f"כתובת לא צפויה: {url}"
    qdate = date.fromisoformat(url.split("&date=")[1][:10])
    items = [
        {"category": cat, "date": iso, "title": cat}
        for iso, cat in EVENTS
        if abs((date.fromisoformat(iso[:10]) - qdate).days) <= 2
    ]
    return FakeResponse(items)


def failing_get(url, timeout=10):
    raise OSError("hebcal unreachable")


def decide(ts: str) -> str:
    """משחזר את החלטת main() עבור הזמן הנתון – בלי שליחה וללא המתנה אמיתית."""
    now = at(ts)
    freeze(ts)
    if not S.in_send_window(now):
        return "SKIP: מחוץ לחלון"
    may_send, resume_at = S.shabbat_status(now)
    if may_send:
        return "SEND"
    if now.hour < 17 or resume_at is None:
        return "SKIP: שבת/חג"
    wait_min = (resume_at - now).total_seconds() / 60
    if wait_min > S.MAX_WAIT_MIN:
        return f"SKIP: יציאה רק ב-{resume_at:%d/%m %H:%M}"
    if not S.in_send_window(resume_at):
        return "SKIP: היציאה מחוץ לחלון"
    return f"WAIT {wait_min:.0f} דק' → SEND ב-{resume_at:%H:%M}"


def main() -> None:
    r = Results("✡️ שער שבת/חג")
    S.requests.get = fake_get

    # ── ראש השנה המחובר לשבת: היציאה רק במוצאי ראשון ──
    r.check("ר\"ה שבת 12.9, ריצת ערב בזמן", decide("2026-09-12 19:30"), "SKIP")
    r.check("ר\"ה שבת 12.9, ריצת ערב מאחרת", decide("2026-09-12 21:30"), "SKIP")
    r.check("ר\"ה שבת 12.9, ריצת צהריים", decide("2026-09-12 16:30"), "SKIP")
    r.check("ערב ר\"ה שישי 11.9 בערב", decide("2026-09-11 20:00"), "SKIP")
    r.check("ערב ר\"ה שישי 11.9 בצהריים", decide("2026-09-11 16:30"), "SEND")
    r.check("מוצאי ר\"ה ראשון 13.9", decide("2026-09-13 21:00"), "SEND")

    # ── שבת רגילה: ריצה שמקדימה את צאת השבת ממתינה במקום לוותר ──
    r.check("שבת 5.9, 10 דק' לפני ההבדלה", decide("2026-09-05 19:38"), "WAIT")
    r.check("שבת 5.9, בדיוק בזמן הקרון", decide("2026-09-05 19:30"), "WAIT")
    r.check("שבת 5.9, בתוך מרווח 30 הדק'", decide("2026-09-05 19:50"), "WAIT")
    r.check("שבת 5.9, אחרי המרווח", decide("2026-09-05 20:28"), "SEND")
    r.check("שבת 5.9, ריצת צהריים", decide("2026-09-05 16:30"), "SKIP")

    # ── שבת הקיץ המאוחרת: חייבת להיכנס מתחת ל-MAX_WAIT_MIN ──
    r.check("שבת 3.7.27 בזמן הקרון – ממתין, לא מדלג",
            decide("2027-07-03 19:30"), "WAIT")
    r.check("שבת 3.7.27, ריצה מאחרת", decide("2027-07-03 21:30"), "SEND")

    r.check("יום חול רגיל בערב", decide("2026-09-08 19:30"), "SEND")

    # ── גיבוי מקומי כש-Hebcal לא זמין – מחמיר בכוונה ──
    S.requests.get = failing_get
    r.check("Hebcal נפל בשבת – לא שולח", decide("2026-09-05 19:50"), "SKIP")
    r.check("Hebcal נפל בראש השנה – לא שולח", decide("2026-09-12 21:30"), "SKIP")
    r.check("Hebcal נפל ביום חול – שולח", decide("2026-09-08 19:30"), "SEND")

    # ── טבלת הימים הטובים שהגיבוי המקומי נשען עליה ──
    # 8 ימים טובים בישראל בשנה, בלי חול המועד (שבו הבוט כן שולח).
    from pyluach import dates as pdates
    from datetime import timedelta
    found = []
    d = date(2026, 9, 1)
    while d < date(2027, 10, 1):
        h = pdates.HebrewDate.from_pydate(d)
        if (h.month, h.day) in S.YOM_TOV_ISRAEL:
            found.append(h.holiday(hebrew=True, israel=True))
        d += timedelta(days=1)
    r.check("YOM_TOV_ISRAEL מכסה 8 ימים טובים בשנה", str(len(found)), "8")
    for expected in ("ראש השנה", "יום כיפור", "סוכות", "שמיני עצרת",
                     "פסח", "שבועות"):
        r.check(f"טבלת הימים הטובים כוללת {expected}",
                " ".join(found), expected)

    r.done()


if __name__ == "__main__":
    main()
