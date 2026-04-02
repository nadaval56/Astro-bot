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
from pathlib import Path
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
CLAUDE_MODEL         = "claude-sonnet-4-6"   # gather, proofread, summary
CLAUDE_MODEL_WRITER  = "claude-opus-4-6"     # generate_message – כתיבה בלבד
CLAUDE_API   = "https://api.anthropic.com/v1/messages"

# ── משתני סביבה ──────────────────────────
ANTHROPIC_API_KEY      = os.environ["ANTHROPIC_API_KEY"]
GREEN_API_INSTANCE     = os.environ["GREEN_API_INSTANCE"]
GREEN_API_TOKEN        = os.environ["GREEN_API_TOKEN"]
WHATSAPP_GROUP_ID      = os.environ["WHATSAPP_GROUP_ID"]   # e.g. "972501234567-1234567890@g.us"


# ══════════════════════════════════════════
# 1. לוח שנה יהודי, זמנים ושבת/חג
# ══════════════════════════════════════════



def get_jewish_date_info() -> dict:
    """
    מחזיר את התאריך העברי הנכון לתצוגה.
    אחרי צאת הכוכבים (~40 דקות אחרי שקיעה) כבר מתחיל היום העברי הבא,
    ומציגים "אור ל[יום הבא]".
    """
    now   = datetime.now(ISRAEL_TZ)
    today = now.date()

    # חישוב שקיעה ישיר עם ephem – עובד כל יום, לא רק ערב שבת
    sunset_dt = None
    try:
        import ephem
        obs        = ephem.Observer()
        obs.lat    = str(LAT)
        obs.lon    = str(LON)
        obs.elev   = ALT
        obs.date   = now.astimezone(pytz.utc)
        sun        = ephem.Sun()
        # previous_setting = שקיעה של היום (גם אם כבר עברה)
        sunset_utc = obs.previous_setting(sun).datetime().replace(tzinfo=pytz.utc)
        sunset_dt  = sunset_utc.astimezone(ISRAEL_TZ)
    except Exception:
        pass

    # Hebcal מחזיר את התאריך העברי הנכון לתאריך לועזי נתון.
    # אין צורך להוסיף יום – today תמיד נכון.
    # after_sunset משמש רק לתצוגה ("אור ל...")
    after_sunset = bool(sunset_dt and now >= sunset_dt + timedelta(minutes=40))
    hebrew_date  = today

    url  = f"https://www.hebcal.com/converter?cfg=json&date={hebrew_date.isoformat()}&g2h=1"
    try:
        data = requests.get(url, timeout=10).json()
    except Exception:
        data = {}

    hd = data.get("hd", 0)
    hm = data.get("hm", "")
    hy = data.get("hy", 0)

    # ניסוח התאריך העברי – "אור ל..." אחרי שקיעה
    if after_sunset:
        hebrew_display = f"אור ל-{hd} {hm} {hy}"
    else:
        hebrew_display = f"{hd} {hm} {hy}"

    return {
        "day":                    hd,
        "month":                  hm,
        "year":                   hy,
        "hebrew_display":         hebrew_display,
        "after_sunset":           after_sunset,
        "is_rosh_chodesh":        hd in [1, 30],
        "is_kiddush_levana":      3 <= hd <= 14,
        "is_last_kiddush_levana": hd == 14,
        "is_erev_rosh_chodesh":   hd == 29,
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

def _azimuth_to_hebrew(az: float) -> str:
    """ממיר אזימוט למעלות לכיוון עברי"""
    dirs = [
        (22.5,  "צפון"),
        (67.5,  "צפון-מזרח"),
        (112.5, "מזרח"),
        (157.5, "דרום-מזרח"),
        (202.5, "דרום"),
        (247.5, "דרום-מערב"),
        (292.5, "מערב"),
        (337.5, "צפון-מערב"),
        (360.0, "צפון"),
    ]
    for limit, name in dirs:
        if az < limit:
            return name
    return "צפון"


def _get_satellite_passes(norad_id: int, name: str, ts, obs) -> list[dict]:
    """מחשב מעברים של לוויין נתון מעל נקודת התצפית"""
    try:
        tle_resp = requests.get(
            f"https://celestrak.org/satcat/tle.php?CATNR={norad_id}", timeout=10
        )
        lines = [l.strip() for l in tle_resp.text.strip().splitlines() if l.strip()]
        if len(lines) < 2:
            return []
        line1, line2 = lines[-2], lines[-1]

        from skyfield.api import EarthSatellite
        sat = EarthSatellite(line1, line2, name, ts)

        now_il = datetime.now(ISRAEL_TZ)
        # חלון: שעה לפני שקיעה עד חצות
        t0 = ts.from_datetime(now_il.replace(hour=17, minute=0, second=0).astimezone(pytz.utc))
        t1 = ts.from_datetime(now_il.replace(hour=23, minute=59, second=0).astimezone(pytz.utc))

        times, events = sat.find_events(obs, t0, t1, altitude_degrees=10.0)

        passes, cur = [], {}
        for ti, ev in zip(times, events):
            dt = ti.astimezone(ISRAEL_TZ)
            if ev == 0:
                cur = {"rise_dt": dt, "rise_ti": ti}
            elif ev == 1:
                cur["peak_dt"] = dt
                cur["peak_ti"] = ti
            elif ev == 2:
                cur["set_dt"] = dt
                if "rise_dt" in cur:
                    passes.append(cur)
                cur = {}

        result = []
        for p in passes:
            # חשב אזימוט בזמן עלייה וירידה
            try:
                diff_rise = (sat - obs).at(p["rise_ti"])
                alt_r, az_r, _ = diff_rise.altaz()
                diff_set  = (sat - obs).at(p.get("peak_ti", p["rise_ti"]))
                alt_p, az_p, _ = diff_set.altaz()

                # כיוון יציאה (שקיעה)
                if "set_dt" in p:
                    set_ti = ts.from_datetime(p["set_dt"].astimezone(pytz.utc))
                    diff_set2 = (sat - obs).at(set_ti)
                    _, az_set, _ = diff_set2.altaz()
                    dir_set = _azimuth_to_hebrew(az_set.degrees)
                else:
                    dir_set = "?"

                az_rise_deg = az_r.degrees
                alt_peak    = round(alt_p.degrees)
                dir_rise    = _azimuth_to_hebrew(az_rise_deg)

                # בהירות לפי גובה שיא
                if alt_peak >= 60:
                    brightness = "בהיר מאוד ✨"
                elif alt_peak >= 35:
                    brightness = "בהיר"
                elif alt_peak >= 20:
                    brightness = "נראה היטב"
                else:
                    brightness = "חלש"

            except Exception:
                dir_rise, dir_set, alt_peak, brightness = "?", "?", "?", ""

            rise_str = p["rise_dt"].strftime("%H:%M")
            peak_str = p.get("peak_dt", p["rise_dt"]).strftime("%H:%M")

            result.append({
                "name":       name,
                "rise_dt":    p["rise_dt"],
                "rise_str":   rise_str,
                "peak_str":   peak_str,
                "dir_rise":   dir_rise,
                "dir_set":    dir_set,
                "alt_peak":   alt_peak,
                "brightness": brightness,
                "az_rise":    round(az_rise_deg) if dir_rise != "?" else "?",
            })

        return result

    except Exception as e:
        print(f"⚠️ שגיאת {name}: {e}")
        return []


def get_station_passes() -> list[str]:
    """
    מחשב מעברים של ISS וטיאנגונג מעל ישראל הלילה.
    מזהה מעברים כפולים (שתי תחנות באותו ערב).
    מחזיר רשימת מחרוזות מעוצבות, או רשימה ריקה אם אין מעברים.
    """
    try:
        from skyfield.api import load, wgs84
        ts  = load.timescale()
        obs = wgs84.latlon(LAT, LON, elevation_m=ALT)

        iss_passes  = _get_satellite_passes(25544, "ISS",      ts, obs)
        css_passes  = _get_satellite_passes(48274, "טיאנגונג", ts, obs)

        result = []

        # זיהוי מעבר כפול – אם שתיהן עוברות בהפרש של פחות מ-10 דקות
        double_pass = False
        if iss_passes and css_passes:
            for ip in iss_passes:
                for cp in css_passes:
                    diff = abs((ip["rise_dt"] - cp["rise_dt"]).total_seconds())
                    if diff < 600:
                        double_pass = True
                        result.append(
                            f"🌟 *מעבר כפול הלילה!* ISS וטיאנגונג בשמיים יחד\n"
                            f"   🛸 ISS: {ip['rise_str']} מ{ip['dir_rise']} לכיוון {ip['dir_set']} "
                            f"(שיא {ip['alt_peak']}°, {ip['brightness']})\n"
                            f"   🛸 טיאנגונג: {cp['rise_str']} מ{cp['dir_rise']} לכיוון {cp['dir_set']} "
                            f"(שיא {cp['alt_peak']}°, {cp['brightness']})"
                        )

        if not double_pass:
            for p in iss_passes[:1]:
                result.append(
                    f"🛸 ISS עובר ב-{p['rise_str']} – "
                    f"מ{p['dir_rise']} לכיוון {p['dir_set']} "
                    f"(שיא {p['alt_peak']}°, {p['brightness']})"
                )
            for p in css_passes[:1]:
                result.append(
                    f"🛸 טיאנגונג עוברת ב-{p['rise_str']} – "
                    f"מ{p['dir_rise']} לכיוון {p['dir_set']} "
                    f"(שיא {p['alt_peak']}°, {p['brightness']})"
                )

        return result

    except Exception as e:
        print(f"⚠️ שגיאת תחנות חלל: {e}")
        return []


# ══════════════════════════════════════════
# 4. ירח וכוכבי לכת (ephem)
# ══════════════════════════════════════════

HISTORY_FILE = Path("message_history.json")
HISTORY_DAYS = 7

DIRECTION_NAMES = ["צפון","צ-מ","מזרח","ד-מ","דרום","ד-מ","מערב","צ-מ"]


# ══════════════════════════════════════════
# היסטוריית הודעות
# ══════════════════════════════════════════

def load_history() -> dict:
    """טוען היסטוריית הודעות מהקובץ"""
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_history(history: dict, today_key: str, summary: dict):
    """
    מוסיף את סיכום היום לקובץ ומנקה ערכים ישנים.
    summary = dict עם נושאים שכוסו היום ואיך.
    """
    history[today_key] = summary

    # מחק ימים ישנים מעבר ל-HISTORY_DAYS
    cutoff = (datetime.now(ISRAEL_TZ) - timedelta(days=HISTORY_DAYS)).strftime("%Y-%m-%d")
    old_keys = [k for k in history if k < cutoff]
    for k in old_keys:
        del history[k]

    HISTORY_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def format_history_for_prompt(history: dict) -> str:
    """
    מעצב את ההיסטוריה לטקסט שנכנס לפרומפט.
    קלוד יקבל תמונה ברורה של מה כוסה לאחרונה.
    """
    if not history:
        return "אין היסטוריה – זו ההודעה הראשונה."

    today = datetime.now(ISRAEL_TZ).date()
    lines = []

    for date_str in sorted(history.keys(), reverse=True)[:5]:
        try:
            d = date.fromisoformat(date_str)
            days_ago = (today - d).days
            when = "אתמול" if days_ago == 1 else f"לפני {days_ago} ימים"
        except Exception:
            when = date_str

        day_data = history[date_str]
        topics = "; ".join(
            f"{k}: {v}" for k, v in day_data.items() if k != "_message_length"
        )
        lines.append(f"  • {when} ({date_str}): {topics}")

    return "\n".join(lines)


def extract_summary_from_message(message: str, payload: dict) -> dict:
    """
    שולח ל-Claude בקשה קצרה לסכם מה כוסה בהודעה – לצורך היסטוריה.
    מחזיר dict קצר לשמירה.
    """
    headers = {
        "x-api-key":         ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type":      "application/json",
    }
    body = {
        "model":      CLAUDE_MODEL,
        "max_tokens": 300,
        "messages": [{
            "role": "user",
            "content": (
                "בהודעה הבאה שנשלחה לקבוצת אסטרונומיה, "
                "תן לי JSON קצר עם הנושאים שכוסו ואיך (ברמה גבוהה). "
                "מפתח = שם הנושא באנגלית קצר (comet, meteor_shower, iss, jupiter וכו'), "
                "ערך = משפט קצר בעברית על מה נאמר. "
                "החזר JSON בלבד, ללא הסברים.\n\n"
                f"ההודעה:\n{message}"
            )
        }]
    }
    try:
        r = requests.post(CLAUDE_API, headers=headers, json=body, timeout=30)
        r.raise_for_status()
        raw = r.json()["content"][0]["text"].strip()
        # נקה ```json אם יש
        raw = raw.replace("```json", "").replace("```", "").strip()
        summary = json.loads(raw)
        summary["_message_length"] = len(message.split())
        return summary
    except Exception as e:
        print(f"⚠️ לא הצלחתי לסכם היסטוריה: {e}")
        return {"_message_length": len(message.split())}

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


# ══════════════════════════════════════════
# 6. יצירת ההודעה עם Claude Opus
# ══════════════════════════════════════════

def proofread_hebrew(message: str) -> str:
    """
    הגהה לשונית של ההודעה – קריאה קצרה לקלוד.
    מתקנת: זכר/נקבה, הטיות, ביטויים לא עבריים, מבנה משפט.
    לא משנה תוכן, לא מקצרת, לא מוסיפה.
    """
    headers = {
        "x-api-key":         ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type":      "application/json",
    }
    body = {
        "model":      CLAUDE_MODEL,
        "max_tokens": 1500,
        "messages": [{
            "role": "user",
            "content": (
                "אתה מגיה עברית מקצועי. תפקידך לתקן שגיאות לשון בלבד.\n"
                "חובה לשמור על:\n"
                "• כל התוכן, המידע והעובדות – ללא שינוי\n"
                "• כל האימוג'י\n"
                "• כל עיצוב הטקסט (*בולד*, שורות ריקות)\n"
                "• אורך ההודעה – אל תקצר ואל תוסיף\n\n"
                "תקן רק:\n"
                "• זכר/נקבה שגוי\n"
                "• הטיות שגויות של פעלים ושמות\n"
                "• ביטויים לא עבריים שאפשר לנסח בעברית טבעית\n"
                "• מבנה משפט מסורבל\n"
                "• 'מקלחת מטאורים' → 'מטר מטאורים'\n"
                "• 'דו-עינית' → 'משקפת'\n"
                "• 'בראייה ערומה' / 'בעין רגילה' → 'בעין בלתי מזוינת'\n\n"
                "החזר את ההודעה המתוקנת בלבד, ללא הסברים.\n\n"
                f"ההודעה:\n{message}"
            )
        }]
    }
    try:
        r = requests.post(CLAUDE_API, headers=headers, json=body, timeout=30)
        r.raise_for_status()
        return r.json()["content"][0]["text"].strip()
    except Exception as e:
        print(f"⚠️ הגהה נכשלה: {e} – שולח הודעה מקורית")
        return message


def gather_space_news(date_str: str, jewish_context: str = "") -> str:
    """
    קריאה 1 – "עיתונאי חלל":
    תפקיד אחד בלבד: חפש ובחר מה מעניין הלילה.
    מחזיר עובדות גולמיות בלי עיצוב, בלי כללי כתיבה.
    """
    headers = {
        "x-api-key":         ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type":      "application/json",
    }

    jewish_section = f"""
אירועים יהודיים-אסטרונומיים ידועים הלילה (כבר מחושבים, אין צורך לחפש):
{jewish_context}
""" if jewish_context else ""

    body = {
        "model":      CLAUDE_MODEL,
        "max_tokens": 800,
        "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        "messages": [{"role": "user", "content": f"""אתה עיתונאי חלל. המשימה שלך היא לחפש ולסנן בלבד – לא לכתוב הודעה.
{jewish_section}
חפש באינטרנט לתאריך {date_str}:
1. חדשות חלל בולטות השבוע – תגליות ג'יימס וב/האבל, שיגורים מיוחדים, גילויים חדשים
2. אירועים אסטרונומיים – שביטים נראים, ליקויים, מטר מטאורים פעיל, Starlink מישראל
3. כל דבר שחובב אסטרונומיה ישראלי לא יידע בלעדיך
4. "ביום זה בהיסטוריה" – חפש this day in space history {date_str} ומצא אירוע היסטורי מעניין שקרה בתאריך הזה (אפשר בכל שנה). עדיפות לאירועים מרשימים: נחיתות, שיגורים ראשונים, תגליות, אסונות.

החזר רשימה קצרה של עובדות גולמיות בלבד:
• שם האירוע/תגלית
• מה קרה בדיוק (עובדה אחת-שתיים, לא יותר)
• האם נראה מישראל? כן/לא/חלקית (לחדשות שוטפות בלבד)
• מתי פורסם / באיזו שנה (תאריך מדויק אם ידוע)

ללא עיצוב, ללא סגנון, ללא המלצות. רק עובדות."""}]
    }

    # המתנה קצרה כדי לא להתנגש עם קריאות קודמות
    time.sleep(3)
    messages = [body["messages"][0].copy()]
    for attempt in range(5):
        try:
            r = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json={**body, "messages": messages},
                timeout=90
            )
            r.raise_for_status()
        except Exception as e:
            if ("429" in str(e) or "529" in str(e)) and attempt < 4:
                # נסה לקרוא את retry-after מה-header
                try:
                    retry_after = int(e.response.headers.get("retry-after", 30))
                except Exception:
                    retry_after = 30 * (attempt + 1)
                print(f"⏳ 429 – ממתין {retry_after} שניות...")
                time.sleep(retry_after)
                continue
            print(f"⚠️ שגיאה ב-gather_space_news: {e}")
            return "אין חדשות חלל זמינות"
        resp = r.json()

        text_blocks = [
            block["text"]
            for block in resp.get("content", [])
            if block.get("type") == "text"
        ]

        if resp.get("stop_reason") == "end_turn":
            return "\n".join(text_blocks).strip()

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

        return "\n".join(text_blocks).strip()

    return "אין חדשות חלל זמינות"


def generate_message(payload: dict) -> str:
    """
    כתיבת ההודעה עם Claude Opus – מודל כתיבה בלבד.
    העובדות הגיעו מ-gather_space_news, אין web_search כאן.
    """
    cloud_pct    = payload["cloud_pct"]
    cloud_desc   = payload["cloud_desc"]
    astro        = payload["astro"]
    iss          = payload["iss"]
    j_events     = payload["jewish_events"]
    jdate        = payload["jdate"]
    date_str     = payload["date_str"]

    kl_message   = payload.get("kl_message")
    tekufa_msg   = payload.get("tekufa_msg")
    upcoming     = payload.get("upcoming", [])
    history_text = payload.get("history_text", "אין היסטוריה.")

    upcoming_str = ""
    if upcoming:
        lines = []
        for ev in upcoming[:5]:
            d = ev["days_away"]
            when = "מחר" if d == 1 else f"בעוד {d} ימים"
            lines.append(f"  • {when}: {ev['title']}")
        upcoming_str = "\n".join(lines)

    # ══════════════════════════════════════════
    # חלק סטטי – נשמר במטמון (cache_control)
    # משתנה רק כשמעדכנים את הקוד
    # ══════════════════════════════════════════
    STATIC_RULES = f"""אתה חובב אסטרונומיה ותיק שמנהל קבוצת WhatsApp לחברים. יש לך קול – חם, סקרן, מדויק. אתה כותב כמו מדריך טיול שמסביר נוף מרהיב: ישיר, אוהב, לא מנסה יותר מדי. כשיש חיבור מעניין בין נתונים – אתה מוצא אותו. כשאין כלום – אתה כנה.

כתוב בעברית תקנית וזורמת. כל משפט אומר משהו מדויק – לא שירה בשביל שירה.
ההודעה תוצג ב-WhatsApp – RTL, עברית בלבד.

═══════════════════════════════
כללים טכניים:
═══════════════════════════════

עיצוב:
• פתח ב"ערב טוב" או "לילה טוב" – קצר וחם
• שורה שנייה: תאריך בפורמט "17.3.2026 | כ״ח אדר תשפ״ו"
• בWhatsApp: *כוכבית אחת* = בולד בלבד
• ו' חיבור לפני בולד – בפנים: *וברכת הלבנה* לא ו*ברכת הלבנה*
• אל תעטוף משפטים שלמים בכוכביות – רק מילות מפתח

תוכן:
• עננות מעל {CLOUD_POOR}% – אל תדכא, ספר מה מחכה בימים הקרובים
• *דבר על מה שהולך לקרות* – הלילה, מחר, השבוע. אירועים שכבר עברו – לא מעניינים
• קידוש לבנה – הצג *אך ורק* את הטקסט מהשדה המצורף. אם ריק – שתיקה מוחלטת
• חדשות חלל ותגליות – עדיפות גבוהה על מיקום כוכבים טכני

תאריך עברי:
• ראש חודש / שבת / חג שמתחיל הלילה – "הלילה", לא "מחר"

סיום:
• סיים תמיד: "שאו מרום עיניכם וראו מי ברא אלה 🌌"

אורך:
• מקסימום 150 מילה. כל משפט מרוויח את מקומו."""

    # ══════════════════════════════════════════
    # חלק דינמי – משתנה כל יום (ללא מטמון)
    # ══════════════════════════════════════════
    DYNAMIC_DATA = f"""═══════════════════════════════
נתוני הערב — {date_str}
═══════════════════════════════

📅 תאריך עברי: {jdate['hebrew_display']}

🌤 עננות: {cloud_pct}%
   הערכה: {cloud_desc}

🌙 הירח: {astro['moon_phase']} ({astro['moon_pct']}% מואר, גיל {astro['moon_age']} ימים)
   זריחה: {astro.get('moon_rise','N/A')} | שקיעה: {astro.get('moon_set','N/A')}

🌅 שקיעת שמש: {astro.get('sunset','N/A')}
🌄 זריחת שמש מחר: {astro.get('sunrise','N/A')}

🪐 כוכבי לכת נראים הלילה:
{chr(10).join(astro['planets_visible']) or "אין כוכבי לכת בולטים בגובה מספיק"}

🛸 מעברי תחנות חלל (ISS / טיאנגונג):
{chr(10).join(iss)}

✡️ אירועים יהודיים היום:
{chr(10).join(j_events) if j_events else "אין אירוע מיוחד הלילה"}

🌙 קידוש לבנה / ברכת הלבנה:
{kl_message or "לא רלוונטי הלילה"}

🌸 תקופות / היפוכי עונות:
{tekufa_msg or "אין תקופה קרובה"}

📅 אירועים יהודיים-אסטרונומיים בשבוע הקרוב:
{upcoming_str or "אין אירועים מיוחדים"}

📜 היום בהיסטוריה (נמצא בחיפוש, כלול בשדה חדשות חלל למעלה):

🗂 היסטוריית הודעות אחרונות:
{history_text}

📡 חדשות חלל ואסטרונומיה (נאספו בנפרד):
{payload.get('space_news', 'אין חדשות זמינות')}"""

    headers = {
        "x-api-key":         ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "anthropic-beta":    "prompt-caching-2024-07-31",
        "content-type":      "application/json",
    }

    initial_message = {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": STATIC_RULES,
                "cache_control": {"type": "ephemeral"}
            },
            {
                "type": "text",
                "text": DYNAMIC_DATA
            }
        ]
    }

    body = {
        "model":      CLAUDE_MODEL_WRITER,   # Opus – כתיבה איכותית
        "max_tokens": 1200,
        "messages":   [initial_message],
        # ללא web_search – העובדות כבר הגיעו מ-gather_space_news
    }

    messages = [initial_message]

    for attempt in range(3):
        try:
            r = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json={**body, "messages": messages},
                timeout=60
            )
            r.raise_for_status()
            break
        except Exception as e:
            if ("429" in str(e) or "529" in str(e)) and attempt < 2:
                try:
                    retry_after = int(e.response.headers.get("retry-after", 30))
                except Exception:
                    retry_after = 30 * (attempt + 1)
                print(f"⏳ {e} – ממתין {retry_after} שניות...")
                time.sleep(retry_after)
            else:
                raise
    resp = r.json()

    usage = resp.get("usage", {})
    cache_read    = usage.get("cache_read_input_tokens", 0)
    cache_written = usage.get("cache_creation_input_tokens", 0)
    if cache_read:
        print(f"💾 מטמון: נחסכו {cache_read} טוקנים (90% הנחה)")
    elif cache_written:
        print(f"💾 מטמון: נכתבו {cache_written} טוקנים למטמון (פעם ראשונה)")

    text_blocks = [
        block["text"]
        for block in resp.get("content", [])
        if block.get("type") == "text"
    ]

    raw = "\n".join(text_blocks).strip()
    for marker in ["ערב טוב", "לילה טוב"]:
        idx = raw.find(marker)
        if idx > 0:
            raw = raw[idx:]
            break
    return raw or "⚠️ לא הצלחתי לייצר הודעה"


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

def is_shabbat_or_yomtov_now() -> bool:
    """
    בודק האם עכשיו שבת או יום טוב.
    הלוגיקה: אם אתמול הייתה הדלקת נרות → היום שבת/חג.
    אם היום הייתה הדלקת נרות שכבר עברה → גם שבת/חג.
    """
    now   = datetime.now(ISRAEL_TZ)
    today = now.date()

    for day_offset in [0, -1]:
        check = today + timedelta(days=day_offset)
        url = (
            f"https://www.hebcal.com/shabbat?cfg=json"
            f"&geonameid={GEONAMEID}&m=50&lg=s"
            f"&yt=G&date={check.isoformat()}"
        )
        try:
            items = requests.get(url, timeout=10).json().get("items", [])
        except Exception:
            continue

        for item in items:
            if item.get("category") == "candles":
                try:
                    candles_dt = datetime.fromisoformat(item["date"]).astimezone(ISRAEL_TZ)
                    if day_offset == -1:
                        # אתמול הייתה הדלקת נרות → היום שבת/חג
                        return True
                    elif day_offset == 0 and candles_dt <= now:
                        # היום הייתה הדלקת נרות שכבר עברה → שבת/חג
                        return True
                except Exception:
                    pass

    return False


def was_sent_today(history: dict) -> bool:
    """בודק אם כבר נשלחה הודעה היום"""
    today_key = datetime.now(ISRAEL_TZ).strftime("%Y-%m-%d")
    return today_key in history


def main():
    now = datetime.now(ISRAEL_TZ)
    print(f"\n🔭 שמי הלילה מתחיל | {now.strftime('%A %d/%m/%Y %H:%M')}\n")

    hour = now.hour  # שעה מקומית ישראל
    history = load_history()

    # ══════════════════════════════════════════
    # לוגיקת שליחה לפי שעת הריצה
    # ══════════════════════════════════════════

    if hour < 17:
        # ── ריצת 13:00 ──
        # שלח אם לא שבת/חג עכשיו
        # (הדלקת נרות בישראל לא יכולה להיות לפני ~15:30)
        if is_shabbat_or_yomtov_now():
            print("✡️ עכשיו שבת/חג – לא שולח")
            sys.exit(0)

    else:
        # ── ריצת 21:00 ──
        # שלח אם: לא נשלח היום, ולא שבת/חג עכשיו

        if was_sent_today(history) and os.environ.get("FORCE_SEND", "false").lower() != "true":
            print("✅ כבר נשלחה הודעה היום – לא שולח שוב (הוסף force_send=true להרצה ידנית)")
            sys.exit(0)

        if is_shabbat_or_yomtov_now():
            print("✡️ עכשיו שבת/חג – לא שולח")
            sys.exit(0)

        print("🌙 ריצת לילה – שולח הודעה")

    # ── איסוף נתונים ────────────────────
    print("📚 טוען היסטוריית הודעות...")
    today_key   = now.strftime("%Y-%m-%d")
    history_text = format_history_for_prompt(history)

    print("📡 מושך נתוני עננות...")
    cloud_pct           = get_cloud_cover()
    cloud_status, cloud_desc = cloud_label(cloud_pct)

    print("🔭 מחשב נתוני ירח וכוכבים...")
    astro = get_astronomical_data()

    print("🛸 מחשב מעברי ISS...")
    iss   = get_station_passes()

    print("✡️ שולף לוח שנה יהודי...")
    jdate    = get_jewish_date_info()
    print(f"🗓️ תאריך עברי: {jdate['hebrew_display']} | after_sunset: {jdate['after_sunset']}")
    j_events = get_jewish_events_today()

    print("🌙 מחשב קידוש לבנה / ברכת הלבנה...")
    kl_info    = get_kiddush_levana_info()
    kl_message = format_kiddush_levana_message(kl_info)

    print("🌸 בודק תקופות קרובות...")
    tekufot     = get_upcoming_tekufot(days_ahead=7)
    tekufa_msg  = format_tekufot_message(tekufot)

    print("📅 מחפש אירועים יהודיים בשבוע הקרוב...")
    upcoming    = get_upcoming_jewish_highlights(days_ahead=7)

    date_str   = now.strftime("%d/%m/%Y")

    print("📡 מחפש חדשות חלל ואסטרונומיה...")
    # בונה הקשר יהודי-אסטרונומי לקריאת החיפוש
    jewish_context_parts = []
    if kl_message:
        jewish_context_parts.append(kl_message)
    if tekufa_msg:
        jewish_context_parts.append(tekufa_msg)
    if j_events:
        jewish_context_parts.extend(j_events)
    if upcoming:
        for ev in upcoming[:3]:
            jewish_context_parts.append(f"בעוד {ev['days_away']} ימים: {ev['title']}")
    jewish_context = "\n".join(jewish_context_parts)
    space_news = gather_space_news(date_str, jewish_context)

    # המתנה קצרה בלבד – retry יטפל ב-429 אם יגיע
    time.sleep(5)

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
        "history_text":  history_text,
        "space_news":    space_news,
    }
    message = generate_message(payload)

    print("✍️ מגיה עברית...")
    message = proofread_hebrew(message)

    print("\n" + "═"*50)
    print(message)
    print("═"*50 + "\n")

    # ── שליחה ───────────────────────────
    print("📱 שולח WhatsApp...")
    send_whatsapp(message)

    # ── שמירת היסטוריה ──────────────────
    print("📚 מסכם ושומר היסטוריה...")
    summary = extract_summary_from_message(message, payload)
    save_history(history, today_key, summary)
    print(f"✅ נשמר: {summary}")
    print("✅ הכל הושלם!")


if __name__ == "__main__":
    main()
