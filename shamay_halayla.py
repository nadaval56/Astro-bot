#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔭 שמי הלילה – בוט אסטרונומיה יהודי יומי
=========================================
שולח הודעת WhatsApp יומית לקבוצה עם:
  • תחזית עננות + עצת צפייה
  • מעברי ISS מעל ישראל
  • כוכבי לכת נראים
  • שלב הירח
  • אירועים יהודיים-אסטרונומיים
    (קידוש לבנה, ברכת החודש, ראש חודש, מולד, תקופות...)
  • אירוע היסטורי ליום זה
  • אירועים בינלאומיים מיוחדים

לוגיקת שבת/חג:
  • ערב שבת/חג  → לא שולח כלל
  • מוצאי שבת/חג → ממתין לצאת הכוכבים + 30 דקות
"""

import os, sys, json, math, time
from datetime import datetime, timedelta, date
import requests
import pytz
from jewish_astronomy import (
    get_kiddush_levana_info,
    format_kiddush_levana_message,
    get_upcoming_tekufot,
    format_tekufot_message,
    get_upcoming_jewish_highlights,
)

# ══════════════════════════════════════════
# קבועים
# ══════════════════════════════════════════
ISRAEL_TZ  = pytz.timezone("Asia/Jerusalem")
LAT        = 31.7683    # מרכז ישראל
LON        = 35.2137
ALT        = 200        # גובה ממוצע (מטר)
GEONAMEID  = "293397"   # תל-אביב ב-Hebcal

# סף עננות (%)
CLOUD_CLEAR       = 25   # בהיר – לילה מושלם
CLOUD_HOPEFUL     = 55   # חלקי – אפשרי עם תקווה
CLOUD_POOR        = 80   # מעורפל – כבד, אך ייתכן פתח

# Claude
CLAUDE_MODEL = "claude-sonnet-4-6"
CLAUDE_API   = "https://api.anthropic.com/v1/messages"

# ── משתני סביבה ──────────────────────────
ANTHROPIC_API_KEY      = os.environ["ANTHROPIC_API_KEY"]
GREEN_API_INSTANCE     = os.environ["GREEN_API_INSTANCE"]
GREEN_API_TOKEN        = os.environ["GREEN_API_TOKEN"]
WHATSAPP_GROUP_ID      = os.environ["WHATSAPP_GROUP_ID"]   # e.g. "972501234567-1234567890@g.us"


# ══════════════════════════════════════════
# 1. לוח שנה יהודי, זמנים ושבת/חג
# ══════════════════════════════════════════

def get_shabbat_info() -> dict:
    """
    בודק מ-Hebcal:
      - האם היום ערב שבת/חג (הדלקת נרות)
      - האם היום מוצאי שבת/חג (הבדלה)
      - זמן ההבדלה המדויק
      - שם הפרשה/חג
    """
    today = datetime.now(ISRAEL_TZ).date()
    url = (
        f"https://www.hebcal.com/shabbat?cfg=json"
        f"&geonameid={GEONAMEID}&m=50&lg=s"
        f"&yt=G&date={today.isoformat()}"
    )
    data = requests.get(url, timeout=10).json()

    result = {
        "is_erev":       False,
        "is_motzei":     False,
        "havdalah_time": None,
        "parasha":       None,
        "holiday":       None,
    }

    for item in data.get("items", []):
        cat   = item.get("category", "")
        title = item.get("title", "")

        if cat == "parashat":
            result["parasha"] = title

        if cat == "holiday":
            result["holiday"] = title

        if cat == "candles":
            dt = datetime.fromisoformat(item["date"]).astimezone(ISRAEL_TZ)
            if dt.date() == today:
                result["is_erev"] = True

        if cat == "havdalah":
            dt = datetime.fromisoformat(item["date"]).astimezone(ISRAEL_TZ)
            result["havdalah_time"] = dt
            if dt.date() == today:
                result["is_motzei"] = True

    return result


def get_jewish_date_info() -> dict:
    """
    ממיר תאריך לועזי לעברי ומחזיר:
      יום בחודש, שם החודש, שנה עברית
    מחשב גם:
      - האם בחלון קידוש לבנה (ג'–י"ד בחודש)
      - האם הלילה האחרון לקידוש לבנה (י"ד)
      - ראש חודש (א'–ב' / ל')
    """
    today = datetime.now(ISRAEL_TZ).date()
    url   = f"https://www.hebcal.com/converter?cfg=json&date={today.isoformat()}&g2h=1"
    data  = requests.get(url, timeout=10).json()

    hd = data.get("hd", 0)
    hm = data.get("hm", "")
    hy = data.get("hy", 0)

    return {
        "day":                   hd,
        "month":                 hm,
        "year":                  hy,
        "is_rosh_chodesh":       hd in [1, 2, 30],
        "is_kiddush_levana":     3 <= hd <= 14,
        "is_last_kiddush_levana": hd == 14,
        "is_erev_rosh_chodesh":  hd == 29,  # אפשר להזכיר ערב ר"ח
    }


def get_jewish_events_today() -> list[str]:
    """
    שולף אירועים יהודיים מיוחדים מה-Hebcal ומוסיף חישובים עצמאיים.
    מחזיר רשימת מחרוזות לתצוגה.
    """
    today = datetime.now(ISRAEL_TZ).date()
    url = (
        f"https://www.hebcal.com/hebcal?v=1&cfg=json"
        f"&maj=on&min=on&mod=on&nx=on&mf=on&ss=on"
        f"&year={today.year}&month={today.month}"
        f"&c=on&geo=geoname&geonameid={GEONAMEID}&M=on&s=on"
    )
    data  = requests.get(url, timeout=10).json()
    jdate = get_jewish_date_info()
    events = []

    # ── ראש חודש ──
    if jdate["is_rosh_chodesh"]:
        events.append(f"🌑 ראש חודש {jdate['month']} – חודש טוב!")

    # ── ערב ראש חודש ──
    if jdate["is_erev_rosh_chodesh"]:
        events.append(f"📅 מחר ראש חודש {jdate['month']} – ערב טוב לברכת ראש חודש")

    # ── קידוש לבנה / ברכת הלבנה ──
    if jdate["is_last_kiddush_levana"]:
        events.append("⚠️ הלילה האחרון לקידוש לבנה! (י\"ד בחודש) – אל תחמיצו!")
    elif jdate["is_kiddush_levana"]:
        days_left = 14 - jdate["day"]
        events.append(
            f"🌙 אנחנו בחלון קידוש לבנה "
            f"(יום {jdate['day']} ב{jdate['month']}, עוד {days_left} ימים)"
        )

    # ── אירועים מ-Hebcal ──
    RELEVANT_CATS = {"holiday", "roshchodesh", "minor", "zmanim", "mevarchim"}
    for item in data.get("items", []):
        try:
            item_date = date.fromisoformat(item["date"][:10])
        except Exception:
            continue
        if item_date != today:
            continue
        cat = item.get("category", "")
        if cat in RELEVANT_CATS:
            title = item.get("title", "")
            heb   = item.get("hebrew", "")
            label = heb if heb else title
            if label and label not in [e.split("–")[0].strip() for e in events]:
                prefix = "✡️" if cat == "holiday" else "📿"
                events.append(f"{prefix} {label}")

    # ── ברכת החודש ──
    # Hebcal מחזיר "Shabbat Mevarchim" בשבת לפני ר"ח
    # בדיקה נוספת: ב-Hebcal אפשר לבדוק לפי title
    for item in data.get("items", []):
        if "mevarchim" in item.get("category", "").lower() or \
           "mevarchim" in item.get("title", "").lower():
            try:
                item_date = date.fromisoformat(item["date"][:10])
            except Exception:
                continue
            if item_date == today:
                month_name = item.get("title", "").replace("Shabbat Mevarchim", "").strip()
                events.append(f"🙏 שבת מברכים את חודש {month_name if month_name else jdate['month']}")

    return events


# ══════════════════════════════════════════
# 2. עננות – Open-Meteo (חינמי)
# ══════════════════════════════════════════

def get_cloud_cover() -> int:
    """ממוצע עננות ב-20:00–23:00 בישראל"""
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        f"&hourly=cloudcover"
        f"&timezone=Asia%2FJerusalem"
        f"&forecast_days=1"
    )
    data  = requests.get(url, timeout=10).json()
    times  = data["hourly"]["time"]
    clouds = data["hourly"]["cloudcover"]

    evening = [c for t, c in zip(times, clouds)
               if 20 <= int(t.split("T")[1][:2]) <= 23]
    return round(sum(evening) / len(evening)) if evening else 50


def cloud_label(pct: int) -> tuple[str, str]:
    """(status_key, תיאור בעברית)"""
    if pct < CLOUD_CLEAR:
        return "clear",        f"שמיים בהירים ({pct}%) – לילה מושלם לצפייה! 🌟"
    elif pct < CLOUD_HOPEFUL:
        return "partial",      f"עננות חלקית ({pct}%) – יש סיכוי טוב לחלונות פתוחים בשמיים 🤞"
    elif pct < CLOUD_POOR:
        return "mostly_cloudy",f"עננות גבוהה ({pct}%) – בתקווה שהענן ייפתח ויאפשר הצצה 🌥️"
    else:
        return "cloudy",       f"עננות כבדה ({pct}%) – לא מומלץ לצאת לצפייה הלילה ☁️"


# ══════════════════════════════════════════
# 3. ISS – מעברים (Skyfield + Celestrak TLE)
# ══════════════════════════════════════════

def get_iss_passes() -> list[str]:
    """מחשב מעברי ISS מעל ישראל הערב (20:00–23:59)"""
    try:
        from skyfield.api import load, EarthSatellite, wgs84
        import pytz as _tz

        tle_resp = requests.get(
            "https://celestrak.org/satcat/tle.php?CATNR=25544", timeout=10
        )
        lines = [l.strip() for l in tle_resp.text.strip().splitlines() if l.strip()]
        if len(lines) < 2:
            return ["⚠️ לא ניתן לקבל נתוני ISS"]

        line1, line2 = lines[-2], lines[-1]
        ts  = load.timescale()
        sat = EarthSatellite(line1, line2, "ISS", ts)
        obs = wgs84.latlon(LAT, LON, elevation_m=ALT)

        now_il  = datetime.now(ISRAEL_TZ)
        t0 = ts.from_datetime(now_il.replace(hour=20, minute=0, second=0).astimezone(pytz.utc))
        t1 = ts.from_datetime(now_il.replace(hour=23, minute=59, second=0).astimezone(pytz.utc))

        times, events = sat.find_events(obs, t0, t1, altitude_degrees=15.0)

        passes, cur = [], {}
        for ti, ev in zip(times, events):
            dt = ti.astimezone(ISRAEL_TZ)
            if ev == 0:
                cur = {"rise": dt}
            elif ev == 1:
                cur["peak"] = dt
            elif ev == 2:
                cur["set"] = dt
                if "rise" in cur:
                    passes.append(cur)
                cur = {}

        result = []
        for p in passes[:2]:
            rise = p["rise"].strftime("%H:%M")
            peak = p.get("peak", p["rise"]).strftime("%H:%M")
            result.append(f"🛸 ISS מעביר ב-{rise} (שיא ב-{peak})")
        return result if result else ["אין מעבר בולט של ISS הלילה"]

    except Exception as e:
        print(f"⚠️ שגיאת ISS: {e}")
        return ["לא ניתן לחשב מעברי ISS הלילה"]


# ══════════════════════════════════════════
# 4. ירח וכוכבי לכת (ephem)
# ══════════════════════════════════════════

DIRECTION_NAMES = ["צפון","צ-מ","מזרח","ד-מ","דרום","ד-מ","מערב","צ-מ"]

def deg_to_dir(deg: float) -> str:
    return DIRECTION_NAMES[round(deg / 45) % 8]


def get_astronomical_data() -> dict:
    """מחשב מיקום ירח, שלב הירח, כוכבי לכת נראים מישראל הערב"""
    try:
        import ephem

        obs       = ephem.Observer()
        obs.lat   = str(LAT)
        obs.lon   = str(LON)
        obs.elev  = ALT
        obs.date  = datetime.now(pytz.utc)

        # ── ירח ──
        moon = ephem.Moon(obs)
        pct  = round(moon.moon_phase * 100)

        prev_new = ephem.previous_new_moon(obs.date)
        age = float(obs.date - prev_new)   # ימים מאז ירח חדש

        if   age <  1.5: phase_name = "🌑 ירח חדש"
        elif age <  7.0: phase_name = "🌒 סהר גדל"
        elif age <  8.5: phase_name = "🌓 רבע ראשון"
        elif age < 14.0: phase_name = "🌔 ירח גדל"
        elif age < 15.5: phase_name = "🌕 ירח מלא"
        elif age < 21.0: phase_name = "🌖 ירח פוחת"
        elif age < 22.5: phase_name = "🌗 רבע אחרון"
        else:            phase_name = "🌘 סהר פוחת"

        def fmt_rise_set(body, ev_fn):
            try:
                return ephem.localtime(ev_fn(body)).strftime("%H:%M")
            except Exception:
                return None

        moon_rise = fmt_rise_set(moon, obs.next_rising)
        moon_set  = fmt_rise_set(moon, obs.next_setting)

        # ── כוכבי לכת ──
        planet_defs = [
            ("נוגה ♀",  ephem.Venus),
            ("מאדים ♂", ephem.Mars),
            ("צדק ♃",   ephem.Jupiter),
            ("שבתאי ♄", ephem.Saturn),
            ("אורנוס ⛢",ephem.Uranus),
        ]
        planets_visible = []
        for name, cls in planet_defs:
            body    = cls(obs)
            alt_deg = math.degrees(float(body.alt))
            if alt_deg > 10:
                az  = math.degrees(float(body.az))
                mag = round(float(body.mag), 1)
                planets_visible.append(
                    f"{name} – גובה {round(alt_deg)}°, כיוון {deg_to_dir(az)}, בהירות {mag}"
                )

        # ── שמש ──
        sun = ephem.Sun(obs)
        try:
            sunset  = ephem.localtime(obs.next_setting(sun)).strftime("%H:%M")
            sunrise = ephem.localtime(obs.next_rising(sun)).strftime("%H:%M")
        except Exception:
            sunset = sunrise = "N/A"

        return {
            "moon_pct":        pct,
            "moon_phase":      phase_name,
            "moon_age":        round(age, 1),
            "moon_rise":       moon_rise,
            "moon_set":        moon_set,
            "planets_visible": planets_visible,
            "sunset":          sunset,
            "sunrise":         sunrise,
        }

    except ImportError:
        print("⚠️ ephem לא מותקן – מחזיר נתונים חלקיים")
        return {
            "moon_pct": 50, "moon_phase": "🌔 ירח גדל",
            "moon_rise": None, "moon_set": None,
            "planets_visible": [], "sunset": "N/A", "sunrise": "N/A",
        }


# ══════════════════════════════════════════
# 5. אירועים היסטוריים
# ══════════════════════════════════════════

HISTORY: dict[tuple[int,int], str] = {
    (1,  1): "1925 – ססיליה פיין-גפוסקין הוכיחה שהשמש עשויה ממימן והליום",
    (1,  4): "2004 – רכב החלל Spirit נחת בהצלחה על מאדים",
    (1, 27): "1967 – אסון אפולו 1: שלושה אסטרונאוטים נספו באש",
    (2, 14): "1990 – תמונת 'Pale Blue Dot' – כדור הארץ ממרחק 6 מיליארד ק\"מ",
    (2, 20): "1962 – ג'ון גלן – האמריקאי הראשון שהקיף את כדור הארץ",
    (3, 13): "1781 – ויליאם הרשל גילה את כוכב אורנוס",
    (3, 14): "1879 – נולד אלברט איינשטיין",
    (4, 12): "1961 – יורי גגרין – האדם הראשון בחלל",
    (4, 24): "1990 – טלסקופ החלל האבל שוגר לחלל",
    (5,  5): "1961 – אלן שפרד – האמריקאי הראשון בחלל",
    (5, 25): "1961 – נשיא קנדי הכריז על מטרת נחיתה על הירח עד סוף העשור",
    (6,  3): "1965 – הליכת החלל האמריקאית הראשונה (אד ווייט)",
    (7,  4): "1997 – Mars Pathfinder נחת על מאדים",
    (7, 20): "1969 – 🌑 נחיתת אפולו 11 – 'One small step for man...'",
    (8, 25): "2012 – וויאג'ר 1 יצא מגבולות המערכת השמשית לחלל הבין-כוכבי",
    (9,  1): "1979 – Pioneer 11 עבר לראשונה ליד שבתאי",
    (10, 4): "1957 – שיגור ספוטניק 1 – הלוויין המלאכותי הראשון בהיסטוריה",
    (11, 9): "1967 – ניסוי שיגור Saturn V לראשונה",
    (12, 7): "1972 – צוות אפולו 17 צילם את 'הכדור הכחול'",
    (12,21): "1968 – אפולו 8 שוגר לירח – ראשונה שהקיף את הירח",
    (12,24): "1968 – אסטרונאוטי אפולו 8 צילמו את 'Earthrise'",
}

def get_historical_event() -> str | None:
    today = datetime.now(ISRAEL_TZ)
    return HISTORY.get((today.month, today.day))


# ══════════════════════════════════════════
# 6. יצירת ההודעה עם Claude Sonnet
# ══════════════════════════════════════════

def generate_message(payload: dict) -> str:
    """
    שולח את כל הנתונים ל-Claude עם כלי web_search.
    Claude יחפש אוטומטית אירועים שוטפים:
      כוכבי שביט, ליקויים, מטאורים, שיגורי Starlink, תגליות חדשות.
    תשובת Claude עוברת עיבוד שמשרשר את כל בלוקי הטקסט.
    """
    cloud_pct    = payload["cloud_pct"]
    cloud_desc   = payload["cloud_desc"]
    astro        = payload["astro"]
    iss          = payload["iss"]
    j_events     = payload["jewish_events"]
    jdate        = payload["jdate"]
    historical   = payload["historical"]
    date_str     = payload["date_str"]

    kl_message   = payload.get("kl_message")
    tekufa_msg   = payload.get("tekufa_msg")
    upcoming     = payload.get("upcoming", [])

    # עיצוב אירועים קרובים
    upcoming_str = ""
    if upcoming:
        lines = []
        for ev in upcoming[:5]:
            d = ev["days_away"]
            when = "מחר" if d == 1 else f"בעוד {d} ימים"
            lines.append(f"  • {when}: {ev['title']}")
        upcoming_str = "\n".join(lines)

    prompt = f"""
אתה כותב הודעה יומית לקבוצת WhatsApp של חובבי אסטרונומיה בישראל – קהל מעורב (אשכנזים וספרדים).
כתוב בעברית תקנית, ידידותית ומרתקת. השתמש באימוג'י במידה.
ההודעה תוצג ב-WhatsApp – שמור על כתיבה RTL נקייה ובעברית בלבד.
אל תשלב אותיות ערביות, לטיניות או כל שפה אחרת בתוך מילים עבריות.

לפני שתכתוב – חפש באינטרנט אירועים אסטרונומיים מעניינים לתאריך {date_str}:
  • כוכבי שביט הנראים כרגע (comets visible tonight)
  • ליקויי ירח/שמש בימים הקרובים
  • גשמי מטאורים פעילים כעת
  • שיגורי Starlink הנראים מהמזרח התיכון
  • אירועים אסטרונומיים בולטים השבוע

═══════════════════════════════
נתוני הערב — {date_str}
═══════════════════════════════

📅 תאריך עברי: {jdate['day']} ב{jdate['month']} {jdate['year']}

🌤 עננות: {cloud_pct}%
   הערכה: {cloud_desc}

🌙 הירח: {astro['moon_phase']} ({astro['moon_pct']}% מואר, גיל {astro['moon_age']} ימים)
   זריחה: {astro.get('moon_rise','N/A')} | שקיעה: {astro.get('moon_set','N/A')}

🌅 שקיעת שמש: {astro.get('sunset','N/A')}
🌄 זריחת שמש מחר: {astro.get('sunrise','N/A')}

🪐 כוכבי לכת נראים הלילה:
{chr(10).join(astro['planets_visible']) or "אין כוכבי לכת בולטים בגובה מספיק"}

🛸 מעברי ISS:
{chr(10).join(iss)}

✡️ אירועים יהודיים היום:
{chr(10).join(j_events) if j_events else "אין אירוע מיוחד הלילה"}

🌙 קידוש לבנה / ברכת הלבנה:
{kl_message or "לא רלוונטי הלילה"}

🌸 תקופות / היפוכי עונות:
{tekufa_msg or "אין תקופה קרובה"}

📅 אירועים יהודיים-אסטרונומיים בשבוע הקרוב:
{upcoming_str or "אין אירועים מיוחדים"}

📜 היום לפני X שנים:
{historical or "אין אירוע מיוחד ביומן"}

═══════════════════════════════
הוראות כתיבה:
═══════════════════════════════
1. כותרת קצרה + תאריך בפתיחה
2. עננות – התייחסות לפי הסטטוס:
   • עד {CLOUD_CLEAR}%     → לילה מושלם! שבח את השמיים
   • {CLOUD_CLEAR}–{CLOUD_HOPEFUL}%  → "יש סיכוי לחלונות פתוחים"
   • {CLOUD_HOPEFUL}–{CLOUD_POOR}%  → "בתקווה שהענן ייפתח..."
   • מעל {CLOUD_POOR}%    → אל תדכא – ספר מה מחכה בימים הקרובים
3. ISS – ציין רק אם עננות מאפשרת (מתחת ל-{CLOUD_POOR}%)
4. קידוש לבנה – ציין בנפרד לאשכנזים ולספרדים; אם יש אזהרת שבת – הדגש!
5. תקופות – הסבר בעברית פשוטה מה משמעות ההיפוך/השוויון,
   כולל ההיבט ההלכתי בקצרה
6. "הכנת קרקע" – אם יש אירוע מעניין בימים הקרובים
   (גשם מטאורים, ליקוי, תקופה, סגירת חלון לבנה) – זרוק עליו מילה:
   "ביום חמישי מגיע שיא... כדאי לסמן ביומן!"
7. אירוע היסטורי – "עובדת יום" מרתקת
8. אירועים שוטפים (מהחיפוש) – שלב בטבעיות;
   אם אינם נראים מישראל – ציין זאת בבירור
9. סיים בברכה קצרה או עובדה קוסמית מפתיעה
10. אורך: 250–400 מילה (קצת יותר בגלל התוכן העשיר)
11. עברית בלבד – ללא ערבוב שפות
"""

    headers = {
        "x-api-key":         ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type":      "application/json",
    }
    body = {
        "model":      CLAUDE_MODEL,
        "max_tokens": 2000,   # יותר מרווח כי יש גם חיפוש
        "tools": [
            {
                "type": "web_search_20250305",
                "name": "web_search"
            }
        ],
        "messages": [{"role": "user", "content": prompt}],
    }

    # Claude עשוי להחזיר מספר סבבים (חיפוש → תשובה)
    # ממשיכים עד שמקבלים stop_reason == "end_turn"
    messages = [{"role": "user", "content": prompt}]

    for attempt in range(5):
        r = requests.post(CLAUDE_API, headers=headers,
                          json={**body, "messages": messages}, timeout=60)
        r.raise_for_status()
        resp = r.json()

        # אוספים את כל בלוקי הטקסט מהתשובה
        text_blocks = [
            block["text"]
            for block in resp.get("content", [])
            if block.get("type") == "text"
        ]

        if resp.get("stop_reason") == "end_turn":
            return "\n".join(text_blocks).strip()

        # אם Claude השתמש בכלי חיפוש – מוסיפים לשרשרת ומשלחים
        if resp.get("stop_reason") == "tool_use":
            messages.append({"role": "assistant", "content": resp["content"]})
            tool_results = []
            for block in resp["content"]:
                if block.get("type") == "tool_use":
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block["id"],
                        "content":     block.get("content", "no results"),
                    })
            messages.append({"role": "user", "content": tool_results})
            continue

        # כל מקרה אחר – מחזירים מה שיש
        return "\n".join(text_blocks).strip() or "⚠️ לא הצלחתי לייצר הודעה"

    return "⚠️ חריגת ניסיונות – Claude לא השלים את התשובה"


# ══════════════════════════════════════════
# 7. שליחת WhatsApp (Green API)
# ══════════════════════════════════════════

def send_whatsapp(message: str):
    url = (
        f"https://api.green-api.com/waInstance{GREEN_API_INSTANCE}"
        f"/sendMessage/{GREEN_API_TOKEN}"
    )
    payload = {"chatId": WHATSAPP_GROUP_ID, "message": message}
    r = requests.post(url, json=payload, timeout=15)
    r.raise_for_status()
    print(f"✅ נשלח | idMessage: {r.json().get('idMessage','?')}")


# ══════════════════════════════════════════
# 8. נקודת כניסה ראשית
# ══════════════════════════════════════════

def main():
    now = datetime.now(ISRAEL_TZ)
    print(f"\n🔭 שמי הלילה מתחיל | {now.strftime('%A %d/%m/%Y %H:%M')}\n")

    # ── בדיקת שבת / חג ──────────────────
    shabbat = get_shabbat_info()

    if shabbat["is_erev"]:
        label = f"חג {shabbat['holiday']}" if shabbat["holiday"] else "שבת"
        print(f"🕯️ ערב {label} – לא שולח הודעה")
        sys.exit(0)

    if shabbat["is_motzei"] and shabbat["havdalah_time"]:
        send_time = shabbat["havdalah_time"] + timedelta(minutes=30)
        wait_sec  = (send_time - now).total_seconds()
        if wait_sec > 0:
            label = f"חג {shabbat['holiday']}" if shabbat["holiday"] else "שבת"
            print(f"✡️ מוצאי {label} – ממתין עד {send_time.strftime('%H:%M')} "
                  f"({round(wait_sec/60)} דקות)")
            time.sleep(wait_sec)

    # ── איסוף נתונים ────────────────────
    print("📡 מושך נתוני עננות...")
    cloud_pct           = get_cloud_cover()
    cloud_status, cloud_desc = cloud_label(cloud_pct)

    print("🔭 מחשב נתוני ירח וכוכבים...")
    astro = get_astronomical_data()

    print("🛸 מחשב מעברי ISS...")
    iss   = get_iss_passes()

    print("✡️ שולף לוח שנה יהודי...")
    jdate    = get_jewish_date_info()
    j_events = get_jewish_events_today()

    print("🌙 מחשב קידוש לבנה / ברכת הלבנה...")
    kl_info    = get_kiddush_levana_info()
    kl_message = format_kiddush_levana_message(kl_info)

    print("🌸 בודק תקופות קרובות...")
    tekufot     = get_upcoming_tekufot(days_ahead=7)
    tekufa_msg  = format_tekufot_message(tekufot)

    print("📅 מחפש אירועים יהודיים בשבוע הקרוב...")
    upcoming    = get_upcoming_jewish_highlights(days_ahead=7)

    historical = get_historical_event()
    date_str   = now.strftime("%d/%m/%Y")

    # ── יצירת הטקסט ─────────────────────
    print("🤖 Claude מייצר הודעה בעברית...")
    payload = {
        "date_str":      date_str,
        "cloud_pct":     cloud_pct,
        "cloud_status":  cloud_status,
        "cloud_desc":    cloud_desc,
        "astro":         astro,
        "iss":           iss,
        "jewish_events": j_events,
        "jdate":         jdate,
        "kl_message":    kl_message,
        "tekufa_msg":    tekufa_msg,
        "upcoming":      upcoming,
        "historical":    historical,
    }
    message = generate_message(payload)

    print("\n" + "═"*50)
    print(message)
    print("═"*50 + "\n")

    # ── שליחה ───────────────────────────
    print("📱 שולח WhatsApp...")
    send_whatsapp(message)
    print("✅ הכל הושלם!")


if __name__ == "__main__":
    main()
