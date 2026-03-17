#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
jewish_astronomy.py
===================
מודול אסטרונומיה יהודית:
  • חלון קידוש לבנה (אשכנזים) / ברכת הלבנה (ספרדים)
  • חישוב ממולד הלבנה המדויק
  • חודשים מיוחדים: תשרי, אב
  • בדיקת שבת בסגירת החלון
  • תקופות השנה (ניסן/תמוז/תשרי/טבת) עם רקע הלכתי
  • "הכנת קרקע" – אירועים יהודיים-אסטרונומיים בשבוע הקרוב
"""

from datetime import datetime, timedelta, date
from typing import Optional
import requests
import pytz

ISRAEL_TZ = pytz.timezone("Asia/Jerusalem")
GEONAMEID = "293397"   # תל-אביב ב-Hebcal


# ══════════════════════════════════════════
# עזרים – Hebcal
# ══════════════════════════════════════════

def _hebcal_items(year: int, month: int) -> list[dict]:
    """שולף אירועים חודשיים מ-Hebcal"""
    url = (
        f"https://www.hebcal.com/hebcal?v=1&cfg=json"
        f"&maj=on&min=on&mod=on&nx=on&mf=on&ss=on"
        f"&year={year}&month={month}"
        f"&c=on&geo=geoname&geonameid={GEONAMEID}&M=on&s=on"
    )
    return requests.get(url, timeout=10).json().get("items", [])


def _get_molad(hebrew_year: int, hebrew_month_name: str) -> Optional[datetime]:
    """
    מחזיר את זמן המולד המדויק מ-Hebcal.
    Hebcal מחזיר אירוע מסוג 'molad' בתוך אירועי החודש.
    """
    # מחשבים את החודש הלועזי המתאים לחיפוש
    today = datetime.now(ISRAEL_TZ)
    for month_offset in range(-1, 3):
        check_date = today + timedelta(days=30 * month_offset)
        items = _hebcal_items(check_date.year, check_date.month)
        for item in items:
            if item.get("category") == "molad":
                try:
                    dt = datetime.fromisoformat(item["date"]).astimezone(ISRAEL_TZ)
                    # בדוק אם זה המולד של החודש הנכון
                    if hebrew_month_name.lower() in item.get("title", "").lower():
                        return dt
                except Exception:
                    pass
    return None


def _get_special_date(items: list[dict], search_title: str) -> Optional[date]:
    """מחפש תאריך של אירוע לפי כותרת"""
    for item in items:
        if search_title.lower() in item.get("title", "").lower():
            try:
                return date.fromisoformat(item["date"][:10])
            except Exception:
                pass
    return None


# ══════════════════════════════════════════
# מולד ו-חלון קידוש/ברכה
# ══════════════════════════════════════════

# משך מחזור ירח (ימים)
LUNAR_CYCLE_DAYS = 29.530589

# סגירת החלון: מולד + 14 ימים 18 שעות 22 דקות
WINDOW_CLOSE_OFFSET = timedelta(days=14, hours=18, minutes=22)

# פתיחת חלון
ASHKENAZ_OPEN_HOURS  = 72   # 3 ימים מלאים אחרי המולד (אשכנזים)
SEPHARDIC_OPEN_DAYS  = 7    # 7 ימים מלאים אחרי המולד (ספרדים)


def get_kiddush_levana_info() -> dict:
    """
    מחשב חלון קידוש לבנה/ברכת הלבנה לחודש הנוכחי.

    מחזיר:
        molad           – זמן המולד המדויק
        ashkenaz_open   – פתיחת חלון אשכנזים
        sephardic_open  – פתיחת חלון ספרדים
        window_close    – סגירת החלון (שניהם)
        last_night      – הלילה האחרון לברכה (מתחשב בשבת)
        shabbat_warning – האם לילה אחרון הוא לפני שבת
        today_status    – תיאור מצב היום
        days_remaining  – ימים עד סגירה (שלילי = עבר)
        special_note    – הערה לחודשים מיוחדים
    """
    now        = datetime.now(ISRAEL_TZ)
    today      = now.date()

    # ── שלב 1: קבל מידע על החודש העברי הנוכחי ──
    conv_url = f"https://www.hebcal.com/converter?cfg=json&date={today.isoformat()}&g2h=1"
    conv     = requests.get(conv_url, timeout=10).json()
    hmonth   = conv.get("hm", "")   # שם החודש באנגלית
    hday     = conv.get("hd", 0)
    hyear    = conv.get("hy", 0)

    # ── שלב 2: מצא את זמן המולד מ-Hebcal ──
    molad = None
    for month_offset in range(-1, 3):
        check = today + timedelta(days=30 * month_offset)
        items = _hebcal_items(check.year, check.month)
        for item in items:
            if item.get("category") == "molad":
                try:
                    dt = datetime.fromisoformat(item["date"]).astimezone(ISRAEL_TZ)
                    # ודא שזה המולד הרלוונטי (לא עתידי מדי / עבר מדי)
                    age = (now - dt).total_seconds() / 86400
                    if -1 <= age <= LUNAR_CYCLE_DAYS:
                        molad = dt
                        break
                except Exception:
                    pass
        if molad:
            break

    if not molad:
        return {"error": "לא נמצא מולד", "today_status": "לא זמין"}

    # ── שלב 3: חשב חלונות ──
    ashkenaz_open  = molad + timedelta(hours=ASHKENAZ_OPEN_HOURS)
    sephardic_open = molad + timedelta(days=SEPHARDIC_OPEN_DAYS)
    window_close   = molad + WINDOW_CLOSE_OFFSET

    # ── שלב 4: חודשים מיוחדים – דחיית פתיחה ──
    special_note = None
    items_now = _hebcal_items(today.year, today.month)

    if hmonth == "Tishri":
        yom_kippur = _get_special_date(items_now, "Yom Kippur")
        if yom_kippur:
            motzei_yk = datetime.combine(
                yom_kippur, datetime.min.time()
            ).replace(tzinfo=ISRAEL_TZ).replace(hour=21, minute=0)
            if ashkenaz_open < motzei_yk:
                ashkenaz_open = motzei_yk
            if sephardic_open < motzei_yk:
                sephardic_open = motzei_yk
            special_note = "בתשרי נהוג לברך לאחר מוצאי יום הכיפורים"

    elif hmonth == "Av":
        tisha_bav = _get_special_date(items_now, "Tisha B'Av")
        if tisha_bav:
            motzei_tb = datetime.combine(
                tisha_bav, datetime.min.time()
            ).replace(tzinfo=ISRAEL_TZ).replace(hour=21, minute=30)
            if ashkenaz_open < motzei_tb:
                ashkenaz_open = motzei_tb
            if sephardic_open < motzei_tb:
                sephardic_open = motzei_tb
            special_note = "באב נהוג לברך לאחר מוצאי תשעה באב"

    # ── שלב 5: בדיקת שבת בסגירת החלון ──
    close_date = window_close.date()
    shabbat_warning = False
    last_night      = window_close

    # אם הסגירה ביום שישי, שבת, או מוצאי שבת לפני הזמן –
    # הלילה האחרון הוא ליל חמישי
    weekday = close_date.weekday()  # 0=שני ... 4=שישי ... 5=שבת
    if weekday == 4:   # שישי – הלילה מתחיל בשקיעה שהיא כבר שבת
        last_night      = window_close - timedelta(days=1)
        shabbat_warning = True
    elif weekday == 5:  # שבת
        last_night      = window_close - timedelta(days=2)
        shabbat_warning = True

    # ── שלב 6: מצב היום ──
    days_remaining = (window_close.date() - today).days

    if now < ashkenaz_open:
        delta_hours = (ashkenaz_open - now).total_seconds() / 3600
        today_status = f"טרם נפתח החלון (אשכנזים בעוד {round(delta_hours)} שעות)"
    elif now < sephardic_open:
        delta_hours = (sephardic_open - now).total_seconds() / 3600
        today_status = (
            f"✅ אשכנזים – החלון פתוח!\n"
            f"⏳ ספרדים – בעוד {round(delta_hours)} שעות"
        )
    elif now > window_close:
        today_status = "❌ החלון נסגר לחודש זה"
    elif shabbat_warning and today >= last_night.date():
        today_status = "⚠️ הלילה האחרון לברכה! (מחר/מחרתיים שבת)"
    elif days_remaining == 0:
        today_status = "⚠️ הלילה האחרון לברכה!"
    elif days_remaining == 1:
        today_status = "🔔 מחר הלילה האחרון לברכה!"
    elif days_remaining <= 3:
        today_status = f"🌙 {days_remaining} ימים עד סגירת החלון"
    else:
        today_status = f"🌙 החלון פתוח ({days_remaining} ימים נותרו)"

    return {
        "molad":            molad,
        "ashkenaz_open":    ashkenaz_open,
        "sephardic_open":   sephardic_open,
        "window_close":     window_close,
        "last_night":       last_night,
        "shabbat_warning":  shabbat_warning,
        "today_status":     today_status,
        "days_remaining":   days_remaining,
        "hebrew_month":     hmonth,
        "hebrew_day":       hday,
        "special_note":     special_note,
        "is_open_ashkenaz":  ashkenaz_open  <= now <= window_close,
        "is_open_sephardic": sephardic_open <= now <= window_close,
    }


def format_kiddush_levana_message(info: dict) -> Optional[str]:
    """
    מחזיר מחרוזת מעוצבת להכללה בהודעת WhatsApp.
    מחזיר None אם החלון לא פתוח ואין הודעה מיוחדת.
    """
    if "error" in info:
        return None

    now   = datetime.now(ISRAEL_TZ)
    lines = []

    close_str     = info["window_close"].strftime("%d/%m בשעה %H:%M")
    last_str      = info["last_night"].strftime("%d/%m") if hasattr(info["last_night"], "strftime") else ""
    ash_open_str  = info["ashkenaz_open"].strftime("%d/%m בשעה %H:%M")
    sep_open_str  = info["sephardic_open"].strftime("%d/%m בשעה %H:%M")

    lines.append("🌙 *קידוש לבנה / ברכת הלבנה*")

    # ── אשכנזים ──
    if not info["is_open_ashkenaz"]:
        if now < info["ashkenaz_open"]:
            lines.append(f"   קידוש לבנה (אשכנזים): עדיין לא – החל מ-{ash_open_str}")
        else:
            lines.append(f"   קידוש לבנה (אשכנזים): הזמן עבר לחודש זה")
    else:
        if info["shabbat_warning"]:
            lines.append(
                f"   קידוש לבנה (אשכנזים): אפשר לברך עד {last_str} בלילה\n"
                f"   ⚠️ שים לב: מכיוון שי\"ד חל בשבת, חלון הזמן מתקצר –\n"
                f"   הלילה האחרון לברכה הוא ליל {last_str}"
            )
        elif info["days_remaining"] == 0:
            lines.append(f"   קידוש לבנה (אשכנזים): אפשר לברך – ⚠️ הלילה האחרון!")
        elif info["days_remaining"] == 1:
            lines.append(f"   קידוש לבנה (אשכנזים): אפשר לברך – 🔔 מחר הלילה האחרון")
        else:
            lines.append(f"   קידוש לבנה (אשכנזים): אפשר לברך עד {close_str}")

    # ── ספרדים ──
    if not info["is_open_sephardic"]:
        if now < info["sephardic_open"]:
            lines.append(f"   ברכת הלבנה (ספרדים): עדיין לא – החל מ-{sep_open_str}")
        else:
            lines.append(f"   ברכת הלבנה (ספרדים): הזמן עבר לחודש זה")
    else:
        if info["shabbat_warning"]:
            lines.append(
                f"   ברכת הלבנה (ספרדים): אפשר לברך עד {last_str} בלילה\n"
                f"   ⚠️ שים לב: מכיוון שי\"ד חל בשבת, חלון הזמן מתקצר –\n"
                f"   הלילה האחרון לברכה הוא ליל {last_str}"
            )
        elif info["days_remaining"] == 0:
            lines.append(f"   ברכת הלבנה (ספרדים): אפשר לברך – ⚠️ הלילה האחרון!")
        elif info["days_remaining"] == 1:
            lines.append(f"   ברכת הלבנה (ספרדים): אפשר לברך – 🔔 מחר הלילה האחרון")
        else:
            lines.append(f"   ברכת הלבנה (ספרדים): אפשר לברך עד {close_str}")

    # ── הערה לחודשים מיוחדים ──
    if info.get("special_note"):
        lines.append(f"   📝 {info['special_note']}")

    return "\n".join(lines)


# ══════════════════════════════════════════
# תקופות השנה
# ══════════════════════════════════════════

# תקופות שמואל (המקובלות להלכה) – נקודת התחלה ידועה:
# תקופת ניסן שנת 1 = 7 באפריל 3761 לפנה"ס, שעה 6:00
# מחזור = 91 יום 7.5 שעות (365.25 / 4)

TEKUFA_CYCLE_DAYS = 365.25 / 4          # ~91.3125 יום
TEKUFA_EPOCH      = datetime(2024, 4, 7, 6, 0, tzinfo=pytz.utc)   # תקופת ניסן תשפ"ד

TEKUFA_NAMES = {
    0: ("ניסן",  "🌸", "אביב", "שוויון יום-לילה של האביב"),
    1: ("תמוז",  "☀️", "קיץ",  "היפוך הקיץ – הלילה הקצר בשנה"),
    2: ("תשרי",  "🍂", "סתיו", "שוויון יום-לילה של הסתיו"),
    3: ("טבת",   "❄️", "חורף", "היפוך החורף – הלילה הארוך בשנה"),
}


def get_upcoming_tekufot(days_ahead: int = 14) -> list[dict]:
    """
    מחזיר תקופות שיחולו בימים הקרובים.
    כולל הלכות ומנהגים רלוונטיים.
    """
    now    = datetime.now(ISRAEL_TZ)
    result = []

    # חשב כמה מחזורים עברו מאז ה-epoch
    elapsed_days = (now.astimezone(pytz.utc) - TEKUFA_EPOCH.replace(tzinfo=pytz.utc)).total_seconds() / 86400
    current_cycle_pos = elapsed_days % TEKUFA_CYCLE_DAYS

    # בדוק את 8 התקופות הקרובות (כדי לכסות days_ahead)
    for i in range(8):
        # התקופה הבאה
        days_to_next = TEKUFA_CYCLE_DAYS - (current_cycle_pos % TEKUFA_CYCLE_DAYS) + i * TEKUFA_CYCLE_DAYS
        tekufa_dt    = now + timedelta(days=days_to_next - TEKUFA_CYCLE_DAYS * (i // 4))

        # חשב את שם התקופה
        total_tekufot = int(elapsed_days / TEKUFA_CYCLE_DAYS)
        tekufa_index  = (total_tekufot + i + 1) % 4

        days_away = (tekufa_dt - now).days
        if 0 <= days_away <= days_ahead:
            name, emoji, season, desc = TEKUFA_NAMES[tekufa_index]
            halacha = _tekufa_halacha(name)
            result.append({
                "name":      name,
                "emoji":     emoji,
                "season":    season,
                "desc":      desc,
                "datetime":  tekufa_dt,
                "days_away": days_away,
                "halacha":   halacha,
            })

    return result


def _tekufa_halacha(name: str) -> str:
    """מחזיר הלכות ומנהגים לתקופה"""
    base = "ברכת 'עושה מעשה בראשית' על שינוי הטבע"
    notes = {
        "ניסן":  f"{base}. תקופת האביב – קרובה לפסח.",
        "תמוז":  f"{base}. היפוך הקיץ – מכאן הלילות מתארכים.",
        "תשרי":  f"{base}. קרובה לימים הנוראים – שוויון יום-לילה.",
        "טבת":   f"{base}. היפוך החורף – מכאן הלילות מתקצרים. "
                  "יש הנזהרים לא לשתות מים בשעת חלוף התקופה.",
    }
    return notes.get(name, base)


def format_tekufot_message(tekufot: list[dict]) -> Optional[str]:
    """מעצב הודעת תקופות לWhatsApp"""
    if not tekufot:
        return None

    lines = []
    for t in tekufot:
        if t["days_away"] == 0:
            when = "הלילה!"
        elif t["days_away"] == 1:
            when = "מחר"
        else:
            when = f"בעוד {t['days_away']} ימים ({t['datetime'].strftime('%d/%m')})"

        lines.append(
            f"{t['emoji']} *תקופת {t['name']}* – {when}\n"
            f"   {t['desc']}\n"
            f"   📿 {t['halacha']}"
        )

    return "\n\n".join(lines)


# ══════════════════════════════════════════
# "הכנת קרקע" – אירועים בשבוע הקרוב
# ══════════════════════════════════════════

def get_upcoming_jewish_highlights(days_ahead: int = 7) -> list[dict]:
    """
    מחזיר אירועים יהודיים-אסטרונומיים חשובים בשבוע הקרוב
    (לא כולל היום עצמו – אלה כבר בחלק הרגיל).
    מיועד ל"הכנת קרקע" בהודעה.
    """
    today    = datetime.now(ISRAEL_TZ).date()
    upcoming = []

    for d in range(1, days_ahead + 1):
        check = today + timedelta(days=d)
        items = _hebcal_items(check.year, check.month)

        for item in items:
            try:
                item_date = date.fromisoformat(item["date"][:10])
            except Exception:
                continue
            if item_date != check:
                continue

            cat   = item.get("category", "")
            title = item.get("title", "")
            heb   = item.get("hebrew", title)

            if cat in {"holiday", "roshchodesh"} or "molad" in cat:
                upcoming.append({
                    "date":      check,
                    "days_away": d,
                    "title":     heb,
                    "category":  cat,
                })

    # הוסף תקופות קרובות
    for t in get_upcoming_tekufot(days_ahead):
        upcoming.append({
            "date":      t["datetime"].date(),
            "days_away": t["days_away"],
            "title":     f"תקופת {t['name']} ({t['desc']})",
            "category":  "tekufa",
        })

    # הוסף אזהרת קידוש לבנה אם החלון נסגר בקרוב
    kl = get_kiddush_levana_info()
    if "error" not in kl and 1 <= kl.get("days_remaining", 99) <= 3:
        upcoming.append({
            "date":      kl["window_close"].date(),
            "days_away": kl["days_remaining"],
            "title":     f"סגירת חלון קידוש לבנה {'⚠️ לפני שבת!' if kl['shabbat_warning'] else ''}",
            "category":  "kiddush_levana",
        })

    return sorted(upcoming, key=lambda x: x["days_away"])


# ══════════════════════════════════════════
# נקודת בדיקה
# ══════════════════════════════════════════

if __name__ == "__main__":
    print("=== קידוש לבנה ===")
    kl = get_kiddush_levana_info()
    for k, v in kl.items():
        print(f"  {k}: {v}")
    print()
    msg = format_kiddush_levana_message(kl)
    print("הודעה:")
    print(msg)

    print("\n=== תקופות קרובות ===")
    tekufot = get_upcoming_tekufot(60)
    for t in tekufot:
        print(f"  {t['name']} – {t['datetime'].strftime('%d/%m/%Y %H:%M')}")
    print(format_tekufot_message(tekufot))

    print("\n=== אירועים יהודיים השבוע ===")
    for ev in get_upcoming_jewish_highlights():
        print(f"  +{ev['days_away']} ימים: {ev['title']}")
