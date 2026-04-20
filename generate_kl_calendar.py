#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_kl_calendar.py – מייצר לוח קידוש לבנה לשנתיים קדימה.

הרצה חד-פעמית: python generate_kl_calendar.py
פלט: kiddush_levana.json

כל חודש עברי מכיל:
  - molad: תאריך ושעת המולד (ירושלים)
  - ashkenaz_open: ליל פתיחה לאשכנזים (מולד +3 ימים, מעוגל ללילה)
  - sephardic_open: ליל פתיחה לספרדים (מולד +7 ימים, מעוגל ללילה)
  - window_close: סגירת חלון (מולד + 14 ימים 18 שעות 22 דקות)
  - hebrew_month: שם החודש העברי
"""

import json
from datetime import datetime, timedelta, date
from pyluach import dates as pdates, hebrewcal
import pytz

ISRAEL_TZ = pytz.timezone("Asia/Jerusalem")

# קבועים הלכתיים
ASHKENAZ_HOURS = 72           # 3 ימים
SEPHARDIC_DAYS = 7            # 7 ימים
WINDOW_CLOSE   = timedelta(days=14, hours=18, minutes=22)


def molad_to_datetime(molad: dict, rc_date: date) -> datetime:
    """
    ממיר מולד pyluach (weekday, hours, parts) ל-datetime ישראלי.
    
    pyluach weekday: 1=ראשון..7=שבת
    python weekday:  0=שני..6=ראשון
    המרה: py_wd = (pyluach_wd - 2) % 7
    
    המולד תמיד ב-0..4 ימים לפני ראש חודש.
    """
    py_molad_wd = (molad['weekday'] - 2) % 7
    minutes = molad['parts'] / 18
    hours = molad['hours']
    
    # חפש את היום שמתאים ל-weekday, עד 4 ימים לפני ר"ח
    for delta in range(0, 5):
        candidate = rc_date - timedelta(days=delta)
        if candidate.weekday() == py_molad_wd:
            dt = datetime(
                candidate.year, candidate.month, candidate.day,
                hours, int(minutes), int((minutes % 1) * 60),
                tzinfo=ISRAEL_TZ
            )
            return dt
    
    # fallback
    return datetime.combine(rc_date, datetime.min.time()).replace(tzinfo=ISRAEL_TZ)


def round_to_night(dt: datetime) -> datetime:
    """קידוש לבנה תמיד בלילה — אם הזמן ביום, מעגל ל-20:00"""
    if 5 <= dt.hour < 20:
        return dt.replace(hour=20, minute=0, second=0, microsecond=0)
    return dt


def generate_calendar(start_year: int = 5786, num_years: int = 2) -> list[dict]:
    """מייצר לוח קידוש לבנה לכל החודשים בטווח"""
    entries = []
    
    for year in range(start_year, start_year + num_years):
        max_month = 13 if hebrewcal.Year(year).leap else 12
        for month_num in range(1, max_month + 1):
            try:
                month = hebrewcal.Month(year, month_num)
                molad_raw = month.molad()
                month_name_heb = month.month_name(hebrew=True)
                month_name_en = month.month_name()
                
                # ראש חודש
                rc_date = pdates.HebrewDate(year, month_num, 1).to_pydate()
                
                # מולד → datetime
                molad_dt = molad_to_datetime(molad_raw, rc_date)
                
                # חלונות – לא מעגלים ללילה כאן, _evening_of ב-lookup מטפל בזה
                ash_open = molad_dt + timedelta(hours=ASHKENAZ_HOURS)
                sep_open = molad_dt + timedelta(days=SEPHARDIC_DAYS)
                close    = molad_dt + WINDOW_CLOSE
                
                # חודשים מיוחדים: תשרי (אחרי יו"כ), אב (אחרי ט' באב)
                special = None
                if month_name_en == "Tishrei":
                    # יום כיפור = י' תשרי
                    yk_date = pdates.HebrewDate(year, month_num, 10).to_pydate()
                    motzei_yk = datetime.combine(yk_date, datetime.min.time()).replace(
                        tzinfo=ISRAEL_TZ, hour=20, minute=30)
                    ash_open = max(ash_open, motzei_yk)
                    sep_open = max(sep_open, motzei_yk)
                    special = "תשרי – לאחר מוצאי יום הכיפורים"
                elif month_name_en == "Av":
                    # ט' באב = ט' אב
                    tb_date = pdates.HebrewDate(year, month_num, 9).to_pydate()
                    motzei_tb = datetime.combine(tb_date, datetime.min.time()).replace(
                        tzinfo=ISRAEL_TZ, hour=21, minute=0)
                    ash_open = max(ash_open, motzei_tb)
                    sep_open = max(sep_open, motzei_tb)
                    special = "אב – לאחר מוצאי תשעה באב"
                
                # ── חישוב הלילה האחרון ──
                # שלב 1: אם הסגירה לפני צאת הכוכבים (~20:00), הלילה של יום הסגירה לא זמין
                if close.hour < 20:
                    last_night = close - timedelta(days=1)  # הערב הקודם
                else:
                    last_night = close  # ליל הסגירה עצמו עדיין זמין
                
                # שלב 2: אם הלילה האחרון חל בליל שבת (שישי ערב), דחה לליל חמישי
                shabbat_warning = False
                last_night_wd = last_night.date().weekday()  # 4=שישי
                if last_night_wd == 4:  # ליל שישי = שבת
                    last_night = last_night - timedelta(days=1)
                    shabbat_warning = True
                
                entry = {
                    "hebrew_year":     year,
                    "hebrew_month":    month_name_heb,
                    "hebrew_month_en": month_name_en,
                    "month_num":       month_num,
                    "rosh_chodesh":    rc_date.isoformat(),
                    "molad":           molad_dt.strftime("%Y-%m-%d %H:%M"),
                    "ashkenaz_open":   ash_open.strftime("%Y-%m-%d %H:%M"),
                    "sephardic_open":  sep_open.strftime("%Y-%m-%d %H:%M"),
                    "window_close":    close.strftime("%Y-%m-%d %H:%M"),
                    "last_night":      last_night.strftime("%Y-%m-%d"),
                    "shabbat_warning": shabbat_warning,
                    "special":         special,
                }
                entries.append(entry)
                
                print(f"  {month_name_heb:8s} {year} | מולד {molad_dt.strftime('%d/%m %H:%M')} | "
                      f"אשכנז {ash_open.strftime('%d/%m')} | ספרד {sep_open.strftime('%d/%m')} | "
                      f"סגירה {close.strftime('%d/%m %H:%M')}"
                      f"{' ⚠️ שבת' if shabbat_warning else ''}"
                      f"{' [' + special + ']' if special else ''}")
            except Exception as e:
                print(f"  ⚠️ שגיאה חודש {month_num}/{year}: {e}")
    
    return entries


if __name__ == "__main__":
    print("🌙 מייצר לוח קידוש לבנה...\n")
    entries = generate_calendar(5786, 2)
    
    output = {
        "generated":   datetime.now(ISRAEL_TZ).isoformat(),
        "description": "לוח קידוש לבנה / ברכת הלבנה – מחושב מראש מ-pyluach",
        "months":      entries,
    }
    
    with open("kiddush_levana.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ נשמר: kiddush_levana.json ({len(entries)} חודשים)")
