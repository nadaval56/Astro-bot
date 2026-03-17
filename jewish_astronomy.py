#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
jewish_astronomy.py – מודול אסטרונומיה יהודית

תיקונים מאומתים:
  1. molad=on נוסף לבקשת Hebcal (היה חסר!)
  2. תקופות שמואל נשלפות מ-Hebcal (לא חישוב עצמי שגוי)
  3. בדיקת שבת מדויקת לפי שעת שקיעה, לא רק יום שבוע
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
    """שולף אירועים חודשיים מ-Hebcal כולל molad=on"""
    url = (
        f"https://www.hebcal.com/hebcal?v=1&cfg=json"
        f"&maj=on&min=on&mod=on&nx=on&mf=on&ss=on"
        f"&molad=on"
        f"&year={year}&month={month}"
        f"&c=on&geo=geoname&geonameid={GEONAMEID}&M=on&s=on"
    )
    return requests.get(url, timeout=10).json().get("items", [])


def _get_special_date(items: list[dict], search_title: str) -> Optional[date]:
    for item in items:
        if search_title.lower() in item.get("title", "").lower():
            try:
                return date.fromisoformat(item["date"][:10])
            except Exception:
                pass
    return None


def _get_sunset(for_date: date) -> Optional[datetime]:
    """
    מחזיר שעת שקיעה אמיתית מ-Hebcal לתאריך נתון.
    candle-lighting = 18 דקות לפני שקיעה, לכן מוסיפים חזרה.
    """
    url = (
        f"https://www.hebcal.com/shabbat?cfg=json"
        f"&geonameid={GEONAMEID}&M=on&b=18"
        f"&date={for_date.isoformat()}"
    )
    try:
        items = requests.get(url, timeout=10).json().get("items", [])
        for item in items:
            if item.get("category") == "candles":
                dt = datetime.fromisoformat(item["date"]).astimezone(ISRAEL_TZ)
                return dt + timedelta(minutes=18)
    except Exception:
        pass
    # fallback: שקיעה ממוצעת
    return datetime.combine(for_date, datetime.min.time()).replace(
        tzinfo=ISRAEL_TZ
    ).replace(hour=18, minute=30)


# ══════════════════════════════════════════
# מולד וחלון קידוש/ברכה
# ══════════════════════════════════════════

LUNAR_CYCLE_DAYS    = 29.530589
WINDOW_CLOSE_OFFSET = timedelta(days=14, hours=18, minutes=22)
ASHKENAZ_OPEN_HOURS = 72   # 3 ימים מלאים (אשכנזים)
SEPHARDIC_OPEN_DAYS = 7    # 7 ימים מלאים (ספרדים)


def get_kiddush_levana_info() -> dict:
    now   = datetime.now(ISRAEL_TZ)
    today = now.date()

    conv_url = f"https://www.hebcal.com/converter?cfg=json&date={today.isoformat()}&g2h=1"
    conv     = requests.get(conv_url, timeout=10).json()
    hmonth   = conv.get("hm", "")
    hday     = conv.get("hd", 0)

    # מצא מולד מ-Hebcal
    molad = None
    for month_offset in range(-1, 3):
        check = today + timedelta(days=30 * month_offset)
        items = _hebcal_items(check.year, check.month)
        for item in items:
            if item.get("category") == "molad":
                try:
                    dt  = datetime.fromisoformat(item["date"]).astimezone(ISRAEL_TZ)
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

    ashkenaz_open  = molad + timedelta(hours=ASHKENAZ_OPEN_HOURS)
    sephardic_open = molad + timedelta(days=SEPHARDIC_OPEN_DAYS)
    window_close   = molad + WINDOW_CLOSE_OFFSET

    # חודשים מיוחדים
    special_note = None
    items_now    = _hebcal_items(today.year, today.month)

    if hmonth == "Tishri":
        yom_kippur = _get_special_date(items_now, "Yom Kippur")
        if yom_kippur:
            motzei_yk = datetime.combine(yom_kippur, datetime.min.time()).replace(
                tzinfo=ISRAEL_TZ).replace(hour=21, minute=0)
            ashkenaz_open  = max(ashkenaz_open,  motzei_yk)
            sephardic_open = max(sephardic_open, motzei_yk)
            special_note   = "בתשרי נהוג לברך במוצאי יום הכיפורים"

    elif hmonth == "Av":
        tisha_bav = _get_special_date(items_now, "Tisha B'Av")
        if tisha_bav:
            motzei_tb = datetime.combine(tisha_bav, datetime.min.time()).replace(
                tzinfo=ISRAEL_TZ).replace(hour=21, minute=30)
            ashkenaz_open  = max(ashkenaz_open,  motzei_tb)
            sephardic_open = max(sephardic_open, motzei_tb)
            special_note   = "באב נהוג לברך לאחר תשעה באב"

    # בדיקת שבת מדויקת לפי שעת שקיעה
    close_date      = window_close.date()
    shabbat_warning = False
    last_night      = window_close
    weekday         = close_date.weekday()  # 4=שישי, 5=שבת

    if weekday == 5:
        last_night      = window_close - timedelta(days=2)
        shabbat_warning = True
    elif weekday == 4:
        sunset = _get_sunset(close_date)
        if sunset and window_close >= sunset:
            last_night      = window_close - timedelta(days=1)
            shabbat_warning = True

    days_remaining = (window_close.date() - today).days

    if now < ashkenaz_open:
        hrs = (ashkenaz_open - now).total_seconds() / 3600
        today_status = f"טרם נפתח החלון (אשכנזים בעוד {round(hrs)} שעות)"
    elif now < sephardic_open:
        hrs = (sephardic_open - now).total_seconds() / 3600
        today_status = f"✅ אשכנזים פתוח | ⏳ ספרדים בעוד {round(hrs)} שעות"
    elif now > window_close:
        today_status = "❌ החלון נסגר לחודש זה"
    elif shabbat_warning and today >= last_night.date():
        today_status = "⚠️ הלילה האחרון לברכה! (שבת מקדימה את הסגירה)"
    elif days_remaining == 0:
        today_status = "⚠️ הלילה האחרון לברכה!"
    elif days_remaining == 1:
        today_status = "🔔 מחר הלילה האחרון לברכה!"
    elif days_remaining <= 3:
        today_status = f"🌙 {days_remaining} ימים עד סגירת החלון"
    else:
        today_status = f"🌙 החלון פתוח ({days_remaining} ימים נותרו)"

    return {
        "molad":             molad,
        "ashkenaz_open":     ashkenaz_open,
        "sephardic_open":    sephardic_open,
        "window_close":      window_close,
        "last_night":        last_night,
        "shabbat_warning":   shabbat_warning,
        "today_status":      today_status,
        "days_remaining":    days_remaining,
        "hebrew_month":      hmonth,
        "hebrew_day":        hday,
        "special_note":      special_note,
        "is_open_ashkenaz":  ashkenaz_open  <= now <= window_close,
        "is_open_sephardic": sephardic_open <= now <= window_close,
    }


def format_kiddush_levana_message(info: dict) -> Optional[str]:
    if "error" in info:
        return None

    now          = datetime.now(ISRAEL_TZ)
    close_str    = info["window_close"].strftime("%d/%m בשעה %H:%M")
    last_str     = info["last_night"].strftime("%d/%m") if hasattr(info["last_night"], "strftime") else ""
    ash_open_str = info["ashkenaz_open"].strftime("%d/%m בשעה %H:%M")
    sep_open_str = info["sephardic_open"].strftime("%d/%m בשעה %H:%M")
    dr           = info["days_remaining"]

    lines = ["🌙 *קידוש לבנה / ברכת הלבנה*"]

    def _fmt(label: str, is_open: bool, open_str: str) -> str:
        if not is_open:
            if now < info["ashkenaz_open"] if "אשכנזים" in label else now < info["sephardic_open"]:
                return f"   {label}: עדיין לא – החל מ-{open_str}"
            return f"   {label}: הזמן עבר לחודש זה"
        if info["shabbat_warning"]:
            return (
                f"   {label}: אפשר לברך עד {last_str} בלילה\n"
                f"   ⚠️ שים לב: מכיוון שהסגירה חלה בשבת, חלון הזמן מתקצר –\n"
                f"   הלילה האחרון לברכה הוא ליל {last_str}"
            )
        if dr == 0:
            return f"   {label}: אפשר לברך – ⚠️ הלילה האחרון!"
        if dr == 1:
            return f"   {label}: אפשר לברך – 🔔 מחר הלילה האחרון"
        return f"   {label}: אפשר לברך עד {close_str}"

    lines.append(_fmt("קידוש לבנה (אשכנזים)", info["is_open_ashkenaz"],  ash_open_str))
    lines.append(_fmt("ברכת הלבנה (ספרדים)",  info["is_open_sephardic"], sep_open_str))

    if info.get("special_note"):
        lines.append(f"   📝 {info['special_note']}")

    return "\n".join(lines)


# ══════════════════════════════════════════
# תקופות שמואל – נשלפות מ-Hebcal
# ══════════════════════════════════════════

TEKUFA_META = {
    "nisan":  ("ניסן",  "🌸", "תקופת האביב לפי שמואל (~7 באפריל). יש הנזהרים מאיסור שתיית מים בשעת חילוף התקופה."),
    "tammuz": ("תמוז",  "☀️", "תקופת הקיץ לפי שמואל (~7 ביולי). מכאן הלילות מתארכים. יש הנזהרים מאיסור שתיית מים."),
    "tishrei":("תשרי",  "🍂", "תקופת הסתיו לפי שמואל (~7 באוקטובר). קרובה לימים הנוראים. יש הנזהרים מאיסור שתיית מים."),
    "tevet":  ("טבת",   "❄️", "תקופת החורף לפי שמואל (~26 בדצמבר). מכאן הלילות מתקצרים. יש הנזהרים מאיסור שתיית מים."),
}


def get_upcoming_tekufot(days_ahead: int = 14) -> list[dict]:
    """
    מחזיר תקופות שמואל בימים הקרובים – נשלפות מ-Hebcal.
    Hebcal מחשב תקופות שמואל נכון (לא השוויון האסטרונומי).
    """
    now   = datetime.now(ISRAEL_TZ)
    today = now.date()
    result, seen = [], set()

    for month_offset in range(0, 4):
        check = today + timedelta(days=30 * month_offset)
        items = _hebcal_items(check.year, check.month)

        for item in items:
            title = item.get("title", "").lower()
            if "tekufat" not in title and "tekufa" not in title:
                continue
            uid = item.get("title", "")
            if uid in seen:
                continue

            try:
                item_dt = datetime.fromisoformat(item["date"]).astimezone(ISRAEL_TZ)
            except Exception:
                try:
                    item_dt = datetime.combine(
                        date.fromisoformat(item["date"][:10]),
                        datetime.min.time()
                    ).replace(tzinfo=ISRAEL_TZ)
                except Exception:
                    continue

            days_away = (item_dt.date() - today).days
            if 0 <= days_away <= days_ahead:
                seen.add(uid)
                # מצא מטא-נתונים
                meta = None
                for key, val in TEKUFA_META.items():
                    if key in title:
                        meta = val
                        break
                if not meta:
                    meta = (item.get("hebrew", uid), "🌀", uid)

                name, emoji, desc = meta
                result.append({
                    "name":      name,
                    "emoji":     emoji,
                    "desc":      desc,
                    "datetime":  item_dt,
                    "days_away": days_away,
                })

    return sorted(result, key=lambda x: x["days_away"])


def format_tekufot_message(tekufot: list[dict]) -> Optional[str]:
    if not tekufot:
        return None
    lines = []
    for t in tekufot:
        if t["days_away"] == 0:
            when = f"היום! ({t['datetime'].strftime('%H:%M')})"
        elif t["days_away"] == 1:
            when = f"מחר ({t['datetime'].strftime('%d/%m %H:%M')})"
        else:
            when = f"בעוד {t['days_away']} ימים ({t['datetime'].strftime('%d/%m %H:%M')})"
        lines.append(f"{t['emoji']} *תקופת {t['name']}* – {when}\n   {t['desc']}")
    return "\n\n".join(lines)


# ══════════════════════════════════════════
# הכנת קרקע – אירועים בשבוע הקרוב
# ══════════════════════════════════════════

def get_upcoming_jewish_highlights(days_ahead: int = 7) -> list[dict]:
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
            cat = item.get("category", "")
            heb = item.get("hebrew", item.get("title", ""))
            if cat in {"holiday", "roshchodesh"} or "molad" in cat:
                upcoming.append({"date": check, "days_away": d, "title": heb, "category": cat})

    for t in get_upcoming_tekufot(days_ahead):
        upcoming.append({
            "date":      t["datetime"].date(),
            "days_away": t["days_away"],
            "title":     f"תקופת {t['name']} ({t['datetime'].strftime('%d/%m %H:%M')})",
            "category":  "tekufa",
        })

    kl = get_kiddush_levana_info()
    if "error" not in kl and 1 <= kl.get("days_remaining", 99) <= 3:
        suffix = " ⚠️ שבת מקדימה!" if kl["shabbat_warning"] else ""
        upcoming.append({
            "date":      kl["window_close"].date(),
            "days_away": kl["days_remaining"],
            "title":     f"סגירת חלון קידוש לבנה{suffix}",
            "category":  "kiddush_levana",
        })

    return sorted(upcoming, key=lambda x: x["days_away"])


if __name__ == "__main__":
    print("=== קידוש לבנה ===")
    kl = get_kiddush_levana_info()
    for k, v in kl.items():
        print(f"  {k}: {v}")
    print("\n", format_kiddush_levana_message(kl))

    print("\n=== תקופות (60 יום) ===")
    tekufot = get_upcoming_tekufot(60)
    if tekufot:
        print(format_tekufot_message(tekufot))
    else:
        print("  אין תקופות בחלון")

    print("\n=== אירועים השבוע ===")
    for ev in get_upcoming_jewish_highlights():
        print(f"  +{ev['days_away']} ימים: {ev['title']}")
