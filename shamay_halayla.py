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
from kiddush_levana import get_kiddush_levana_text

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
    מחזיר את התאריך העברי הנכון באמצעות pyluach – חישוב מקומי, ללא API.
    pyluach משנה תאריך עברי בחצות. אחרי שקיעה (17:00+) מוסיפים יום.
    """
    from pyluach import dates as pdates, hebrewcal

    now          = datetime.now(ISRAEL_TZ)
    today_il     = now.date()  # תאריך ישראלי מפורש, לא date.today() של המערכת
    after_sunset = now.hour >= 17  # ריצת 21:00 = תמיד אחרי שקיעה

    hdate = pdates.HebrewDate.from_pydate(today_il)
    print(f"📅 pyluach: {today_il} → {hdate.hebrew_day()} {hdate.month_name(hebrew=True)}")
    if after_sunset:
        hdate = hdate + 1  # ריצת 21:00 → יום עברי הבא תמיד

    hd = hdate.day
    hm = hdate.month_name(hebrew=True)
    hy = hebrewcal.Year(hdate.year).year_string()

    # תצוגה
    if after_sunset:
        hebrew_display = f"אור ל-{hdate.hebrew_day()} {hm} {hy}"
    else:
        hebrew_display = f"{hdate.hebrew_day()} {hm} {hy}"

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
    שולף אירועים יהודיים – חגים מ-pyluach, זמנים מ-Hebcal.
    """
    from pyluach import dates as pdates, hebrewcal as pheb

    now        = datetime.now(ISRAEL_TZ)
    today      = now.date()
    is_evening = now.hour >= 17

    jdate  = get_jewish_date_info()
    hdate  = pdates.HebrewDate.from_pydate(today)
    if is_evening:
        hdate = hdate + 1

    events = []

    # ── חג / יו"ט מ-pyluach ──
    holiday = hdate.holiday(hebrew=True, israel=True)
    if holiday:
        events.append(f"✡️ {holiday}")

    # ── צום מ-pyluach ──
    fast = pheb.fast_day(hdate, hebrew=True)
    if fast:
        events.append(f"🕯️ {fast}")

    # ── ראש חודש ──
    if jdate["is_rosh_chodesh"]:
        # יום ל׳ = ראש חודש של החודש הבא, לא הנוכחי
        if jdate["day"] == 30:
            from pyluach import dates as pdates, hebrewcal as pheb
            hdate = pdates.HebrewDate.from_pydate(today)
            if jdate["after_sunset"]:
                hdate = hdate + 1
            next_month = pheb.Month(hdate.year, hdate.month) + 1
            rc_month = next_month.month_name(hebrew=True)
        else:
            rc_month = jdate["month"]
        events.append(f"🌑 ראש חודש {rc_month} – חודש טוב!")

    # ── ערב ראש חודש ──
    if jdate["is_erev_rosh_chodesh"]:
        from pyluach import dates as pdates, hebrewcal as pheb
        hdate = pdates.HebrewDate.from_pydate(today)
        if jdate["after_sunset"]:
            hdate = hdate + 1
        next_month = pheb.Month(hdate.year, hdate.month) + 1
        events.append(f"📅 מחר ראש חודש {next_month.month_name(hebrew=True)}")

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
                "Summarize this astronomy WhatsApp message in a JSON object.\n"
                "Rules: English keys only, short Hebrew values (max 10 words each).\n"
                "Use these keys: weather, moon, planets, iss, space_news, jewish\n"
                "IMPORTANT: this_day_history key = ONLY for 'X years ago today' anniversary events.\n"
                "Current news/discoveries go in space_news, NOT in this_day_history.\n"
                "Return ONLY the JSON object, no markdown, no explanation.\n\n"
                f"Message:\n{message[:1500]}"
            )
        }]
    }
    raw = ""
    try:
        r = requests.post(CLAUDE_API, headers=headers, json=body, timeout=30)
        r.raise_for_status()
        raw = r.json()["content"][0]["text"].strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        start = raw.find('{')
        end   = raw.rfind('}')
        if start != -1 and end != -1:
            raw = raw[start:end+1]
        summary = json.loads(raw)
        summary["_message_length"] = len(message.split())
        print(f"✅ סיכום נשמר: {list(summary.keys())}")
        return summary
    except Exception as e:
        print(f"⚠️ לא הצלחתי לסכם היסטוריה: {e}")
        print(f"   raw: {raw[:200]}")
        return {"_message_length": len(message.split())}

def deg_to_dir(deg: float) -> str:
    return DIRECTION_NAMES[round(deg / 45) % 8]


def get_astronomical_data() -> dict:
    """
    מחשב מיקום ירח, שלב הירח, כוכבי לכת נראים מישראל הערב.

    חשוב: כל חישובי הכוכבים נעשים לשעת הצפייה (19:30 ישראל),
    לא לשעת הריצה! אחרת כוכבים שנמצאים מעל האופק בבוקר
    אבל שוקעים לפני הערב יופיעו בטעות.
    """
    try:
        import ephem

        obs       = ephem.Observer()
        obs.lat   = str(LAT)
        obs.lon   = str(LON)
        obs.elev  = ALT

        # ══════════════════════════════════════════
        # שלב 1: חישוב שקיעה/זריחה
        # מגדירים זמן צהריים (תמיד לפני שקיעה) כדי ש-next_setting ייתן את שקיעת היום
        # ══════════════════════════════════════════
        noon_il  = datetime.now(ISRAEL_TZ).replace(hour=12, minute=0, second=0, microsecond=0)
        noon_utc = noon_il.astimezone(pytz.utc)
        obs.date = noon_utc

        sun = ephem.Sun(obs)
        try:
            sunset_utc  = obs.next_setting(sun).datetime()
            sunset_dt   = sunset_utc.replace(tzinfo=pytz.utc).astimezone(ISRAEL_TZ)
            sunset      = sunset_dt.strftime("%H:%M")
            # next_rising מצהריים → זריחת מחר בבוקר (שזה מה שאנחנו רוצים)
            sunrise_utc = obs.next_rising(sun).datetime()
            sunrise     = sunrise_utc.replace(tzinfo=pytz.utc).astimezone(ISRAEL_TZ).strftime("%H:%M")
        except Exception:
            sunset_dt  = None
            sunset = sunrise = "N/A"

        # ══════════════════════════════════════════
        # שלב 2: מעבר לזמן ערב (19:30 ישראל) לכל שאר החישובים
        # כוכבי לכת, ירח, מיקומים – הכל לשעת תחילת הצפייה
        # ══════════════════════════════════════════
        evening_il  = datetime.now(ISRAEL_TZ).replace(hour=19, minute=30, second=0, microsecond=0)
        evening_utc = evening_il.astimezone(pytz.utc)
        obs.date    = evening_utc

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

        # ── ירח – זריחה/שקיעה ביחס לחלון הצפייה (אחרי שקיעת השמש) ──
        obs_evening = ephem.Observer()
        obs_evening.lat  = obs.lat
        obs_evening.lon  = obs.lon
        obs_evening.elev = obs.elev
        if sunset_dt:
            obs_evening.date = ephem.Date(sunset_utc.strftime("%Y/%m/%d %H:%M:%S"))
        else:
            obs_evening.date = obs.date

        moon_evening = ephem.Moon(obs_evening)

        # מצא: מתי הירח עולה ומתי שוקע במהלך חלון 20:00-02:00
        moon_rise = None
        moon_set  = None
        try:
            rise_utc = obs_evening.next_rising(moon_evening).datetime()
            rise_dt  = rise_utc.replace(tzinfo=pytz.utc).astimezone(ISRAEL_TZ)
            if 19 <= rise_dt.hour or rise_dt.hour < 6:
                moon_rise = rise_dt.strftime("%H:%M")
        except Exception:
            pass
        try:
            set_utc = obs_evening.next_setting(moon_evening).datetime()
            set_dt  = set_utc.replace(tzinfo=pytz.utc).astimezone(ISRAEL_TZ)
            if 19 <= set_dt.hour or set_dt.hour < 6:
                moon_set = set_dt.strftime("%H:%M")
        except Exception:
            pass

        # האם הירח גלוי בתחילת הלילה?
        moon_alt_evening = math.degrees(float(moon_evening.alt))
        moon_visible_evening = moon_alt_evening > 0

        # ── כוכבי לכת – מחושבים ב-19:30 ישראל ──
        planet_defs = [
            ("נוגה ♀",  ephem.Venus),
            ("מאדים ♂", ephem.Mars),
            ("צדק ♃",   ephem.Jupiter),
            ("שבתאי ♄", ephem.Saturn),
            ("אורנוס ⛢",ephem.Uranus),
        ]
        planets_visible = []
        for name, cls in planet_defs:
            body    = cls(obs)   # obs.date = 19:30 ישראל
            alt_deg = math.degrees(float(body.alt))
            if alt_deg > 10:
                az  = math.degrees(float(body.az))
                mag = round(float(body.mag), 1)
                planets_visible.append(
                    f"{name} – גובה {round(alt_deg)}°, כיוון {deg_to_dir(az)}, בהירות {mag}"
                )

        # ── שמש (כבר חושב למעלה) ──
        return {
            "moon_pct":             pct,
            "moon_phase":           phase_name,
            "moon_age":             round(age, 1),
            "moon_rise":            moon_rise,
            "moon_set":             moon_set,
            "moon_visible_evening": moon_visible_evening,
            "planets_visible":      planets_visible,
            "sunset":               sunset,
            "sunrise":              sunrise,
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

from auto_fix import auto_fix


def fix_opening(message: str, payload: dict) -> str:
    """
    Python בלבד – מתקן את שורת הפתיחה לפי שעה.
    ודאי 100%, לא תלוי ב-AI.
    ראש חודש → "חודש טוב!" (עדיפות עליונה אחרי מוצ"ש)
    """
    now_hour  = datetime.now(ISRAEL_TZ).hour
    is_motzei = payload.get("is_motzei", False)
    jdate     = payload.get("jdate", {})

    if is_motzei:
        correct = "שבוע טוב"
    elif jdate.get("is_rosh_chodesh", False):
        correct = "חודש טוב"
    elif now_hour >= 21 or now_hour < 6:
        correct = "לילה טוב"
    elif now_hour >= 17:
        correct = "ערב טוב"
    elif now_hour >= 12:
        correct = "צהריים טובים"
    else:
        correct = "בוקר טוב"

    # פצל לשורה ראשונה + שאר
    lines = message.split("\n", 1)
    first_line = lines[0]
    rest       = lines[1] if len(lines) > 1 else ""

    # בדוק אם הפתיחה נכונה
    VALID_OPENINGS = ["ערב טוב", "לילה טוב", "צהריים טובים", "שבוע טוב", "מוצאי שבת", "חודש טוב"]
    needs_fix = not any(first_line.startswith(o) for o in VALID_OPENINGS)
    wrong_opening = any(
        first_line.startswith(o) for o in VALID_OPENINGS
        if o != correct and not (correct == "ערב טוב" and o == "לילה טוב")
    )

    if needs_fix or wrong_opening:
        # מצא את האימוג'י אם יש
        import re
        emoji_match = re.search(r'[\U00010000-\U0010ffff\u2600-\u26FF\u2700-\u27BF]', first_line)
        emoji = " " + emoji_match.group(0) if emoji_match else " 🌙"
        new_first = f"{correct}{emoji}"
        print(f"🔧 fix_opening: '{first_line.strip()}' → '{new_first}'")
        return new_first + "\n" + rest

    return message


def fix_date_line(message: str, payload: dict) -> str:
    """
    Python בלבד – כופה את שורת התאריך הנכונה בשורה השנייה.
    Opus לפעמים טועה בהעתקת התאריך העברי, אז אנחנו לא סומכים עליו.
    """
    jdate    = payload["jdate"]
    now      = datetime.now(ISRAEL_TZ)
    # פורמט: 20.4.2026 | ג׳ אייר תשפ״ו
    correct_date = f"{now.day}.{now.month}.{now.year} | {jdate['hebrew_display']}"

    lines = message.split("\n")
    if len(lines) < 2:
        return message

    old_date = lines[1].strip()
    if old_date != correct_date:
        print(f"🔧 fix_date_line: '{old_date}' → '{correct_date}'")
        lines[1] = correct_date
        return "\n".join(lines)

    return message


def quality_check(message: str, payload: dict) -> str:
    """
    Sonnet – בקרה לוגית בלבד.
    בודק רק: "הלילה" על אירוע שכבר היה, וחזרות מהיסטוריה.
    הנחיה מחמירה: לא לשנות ניסוח, לא לקצר, לא לערוך.
    """
    sunset       = payload.get("astro", {}).get("sunset", "N/A")
    history_text = payload.get("history_text", "")

    # אם אין היסטוריה – בדוק רק "הלילה"
    history_section = (
        f"\nהיסטוריה אחרונה (בדוק חזרות):\n{history_text[:400]}"
        if history_text and history_text != "אין היסטוריה – זו ההודעה הראשונה."
        else ""
    )

    headers = {
        "x-api-key":         ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type":      "application/json",
    }
    body = {
        "model":      CLAUDE_MODEL,
        "max_tokens": 1200,
        "messages": [{
            "role": "user",
            "content": (
                f"אתה בודק עובדתי של הודעה. שתי משימות בלבד:\n\n"
                f"1. 'הלילה': שקיעה היום ב-{sunset}. "
                f"אם כתוב 'הלילה X' על אירוע שכבר התרחש לפני השקיעה – "
                f"שנה ל'היום X' או מחק לפי הקשר. אחרת – אל תגע.\n"
                f"2. חזרה: רק אם חדשה **ממש אותו אירוע** (לא רק נושא דומה) מופיעה בהיסטוריה – "
                f"הסר את המשפט הספציפי. אירועים היסטוריים ('לפני X שנים') לעולם אינם חזרה.{history_section}\n\n"
                f"חשוב מאוד: אל תשנה ניסוח, אל תקצר, אל תוסיף. "
                f"אם לא מצאת בעיה – החזר את ההודעה כפי שהיא, מילה במילה.\n\n"
                f"ההודעה:\n{message}"
            )
        }]
    }
    try:
        r = requests.post(CLAUDE_API, headers=headers, json=body, timeout=30)
        r.raise_for_status()
        result = r.json()["content"][0]["text"].strip()
        # בדוק שהתוצאה סבירה – לא קצרה משמעותית
        if result and len(result) >= len(message) * 0.85:
            print("✅ quality_check: הושלם")
            return result
        print("⚠️ quality_check: תוצאה קצרה מדי – שומר מקורי")
        return message
    except Exception as e:
        print(f"⚠️ quality_check נכשל: {e} – ממשיך בלי")
        return message


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
                "• זכר/נקבה שגוי – לדוגמה: 'שתי מאורות' → 'שני מאורות' (מאור זכר), 'כל אחת' → 'כל אחד' כשמדובר בגוף זכר\n"
                "• הטיות שגויות של פעלים ושמות\n"
                "• ביטויים לא עבריים שאפשר לנסח בעברית טבעית\n"
                "• מבנה משפט מסורבל\n"
                "• 'מקלחת מטאורים' → 'מטר מטאורים'\n"
                "• 'דו-עינית' → 'משקפת'\n"
                "• 'בראייה ערומה' / 'בעין רגילה' → 'בעין בלתי מזוינת'\n"
                "• מיילים → המר לקילומטרים (1 מייל = 1.609 ק\"מ)\n"
                "• 'קרייטר' / 'קרטר' → 'מכתש'\n"
                "• ו/ה/ב/כ/ל/מ/ש לפני *בולד* – כנס לפנים: *ונוגה* לא ו*נוגה*, *המדוזה* לא ה*מדוזה*\n\n"
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

    history_text = payload.get("history_text", "אין היסטוריה.")
    is_motzei    = payload.get("is_motzei", False)

    # ══════════════════════════════════════════
    # חלק סטטי – נשמר במטמון (cache_control)
    # משתנה רק כשמעדכנים את הקוד
    # ══════════════════════════════════════════
    # קרא כללים מקובץ חיצוני – קל לעריכה ב-GitHub
    rules_file = Path(__file__).parent / "rules.md"
    if rules_file.exists():
        STATIC_RULES = rules_file.read_text(encoding="utf-8")
        print("📋 כללים נטענו מ-rules.md")
    else:
        # fallback – כללים מינימליים
        STATIC_RULES = """אתה חובב אסטרונומיה שמנהל קבוצת WhatsApp. כתוב בעברית תקנית, חמה, מדויקת.
סיים תמיד: "שאו מרום עיניכם וראו מי ברא אלה 🌌"
מקסימום 150 מילה."""
        print("⚠️ rules.md לא נמצא – משתמש בכללים מינימליים")

    # ══════════════════════════════════════════
    # חלק דינמי – משתנה כל יום (ללא מטמון)
    # ══════════════════════════════════════════
    now_il       = datetime.now(ISRAEL_TZ)
    current_time = now_il.strftime("%H:%M")
    is_daytime   = now_il.hour < 17

    DYNAMIC_DATA = f"""═══════════════════════════════
נתוני הערב — {date_str} | שעה: {current_time}
{'⚠️ מוצאי שבת/חג – פתח ב"שבוע טוב"!' if is_motzei else ''}
{'⚠️ שעת אחר הצהריים – פתח ב"צהריים טובים" ולא ב"ערב טוב"!' if is_daytime else ''}
═══════════════════════════════

📅 תאריך עברי עכשיו: {jdate['hebrew_display']}
⚠️ הלילה הקרוב (אחרי שקיעה ב-{astro.get('sunset','N/A')}) יהיה כבר היום העברי הבא – אל תכתוב על אירועי היום כאילו הם "הלילה"!

🌤 עננות: {cloud_pct}%
   הערכה: {cloud_desc}

🌙 הירח: {astro['moon_phase']} ({astro['moon_pct']}% מואר, גיל {astro['moon_age']} ימים)
   {'🌙 גלוי בתחילת הלילה' if astro.get('moon_visible_evening') else '🌙 לא גלוי בתחילת הלילה (שקע לפני החשיכה)'}
   {('🌙 יזרח הלילה ב-' + astro['moon_rise'] + ' (השמיים חשוכים עד אז)') if astro.get('moon_rise') else '🌙 לא יזרח בשעות הלילה'}
   {('🌙 ישקע הלילה ב-' + astro['moon_set']) if astro.get('moon_set') else ''}

🌅 שקיעת שמש: {astro.get('sunset','N/A')}
🌄 זריחת שמש מחר: {astro.get('sunrise','N/A')}

🪐 כוכבי לכת נראים הלילה (מחושב ל-19:30 ישראל):
{chr(10).join(astro['planets_visible']) or "אין כוכבי לכת בולטים בגובה מספיק"}

🛸 מעברי תחנות חלל (ISS / טיאנגונג):
{chr(10).join(iss)}

✡️ אירועים יהודיים היום:
{chr(10).join(j_events) if j_events else "אין אירוע מיוחד הלילה"}

📜 היום בהיסטוריה (נמצא בחיפוש, כלול בשדה חדשות חלל למעלה):

🗂 היסטוריית הודעות אחרונות:
{history_text}

📡 חדשות חלל ואסטרונומיה (נאספו בנפרד):
{payload.get('space_news', 'אין חדשות זמינות')}

⚠️ חשוב: אל תסיים ב"שאו מרום עיניכם..." – שורת החתימה מתווספת אוטומטית.
⚠️ חשוב: אל תכתוב על קידוש לבנה או אירועים קרובים – זה מתווסף אוטומטית."""

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


def build_upcoming_text() -> str:
    """
    Python בלבד – בונה שורת אירועים קרובים.
    לא עובר דרך Opus, כך שבעיות כמו "ערב יום הזיכרון" לא יקרו.
    """
    now   = datetime.now(ISRAEL_TZ)
    today = now.date()
    is_daytime = now.hour < 17

    DAY_NAMES = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]

    # אירועים מ-Hebcal (חגים, ימי זיכרון, ראש חודש) – קריאה אחת-שתיים בלבד
    events = []
    end_date = today + timedelta(days=7)

    months_to_check = {(today.year, today.month)}
    if end_date.month != today.month:
        months_to_check.add((end_date.year, end_date.month))

    for year, month in months_to_check:
        url = (
            f"https://www.hebcal.com/hebcal?v=1&cfg=json"
            f"&maj=on&min=on&mod=on&nx=on"
            f"&year={year}&month={month}"
            f"&c=on&geo=geoname&geonameid={GEONAMEID}&M=on&s=on"
        )
        try:
            items = requests.get(url, timeout=10).json().get("items", [])
            for item in items:
                try:
                    item_date = date.fromisoformat(item["date"][:10])
                except Exception:
                    continue
                days_away = (item_date - today).days
                if not (1 <= days_away <= 7):
                    continue
                cat = item.get("category", "")
                if cat in {"holiday", "roshchodesh"}:
                    heb = item.get("hebrew", item.get("title", ""))
                    events.append({"date": item_date, "days_away": days_away, "title": heb})
        except Exception:
            pass

    events.sort(key=lambda x: x["days_away"])

    if not events:
        return ""

    # סנן כפילויות
    seen = set()
    unique = []
    for ev in events:
        if ev["title"] not in seen:
            seen.add(ev["title"])
            unique.append(ev)
    events = unique[:4]

    # בנה טקסט
    parts = []
    for ev in events:
        d = ev["days_away"]
        ev_day = DAY_NAMES[ev["date"].weekday()]

        # אירועים שמתחילים בערב: "הערב" (ריצת יום, מחר = הערב)
        EVENING_EVENTS = ["יום השואה", "יום הזיכרון", "יום העצמאות",
                          "ראש השנה", "יום כיפור", "סוכות", "פסח",
                          "שבועות", "פורים", "חנוכה"]
        is_evening_start = any(e in ev["title"] for e in EVENING_EVENTS)

        if d == 1 and is_daytime and is_evening_start:
            parts.append(f"הערב *{ev['title']}*")
        elif d == 1:
            parts.append(f"מחר *{ev['title']}*")
        else:
            parts.append(f"*{ev['title']}* ביום {ev_day}")

    return "השבוע: " + ", ".join(parts) + "." if parts else ""


def build_footer(payload: dict) -> str:
    """
    בונה את התוספת שמודבקת אחרי הודעת Opus:
    1. אירועים קרובים (אם יש)
    2. קידוש לבנה (אם רלוונטי)
    3. שורת חתימה
    הכל Python – ללא AI.
    """
    lines = []

    # אירועים קרובים
    upcoming = build_upcoming_text()
    if upcoming:
        lines.append(upcoming)

    # קידוש לבנה
    kl = get_kiddush_levana_text()
    if kl:
        lines.append("")
        lines.append(kl)

    # חתימה
    lines.append("")
    lines.append("שאו מרום עיניכם וראו מי ברא אלה 🌌")

    return "\n".join(lines)


def strip_closing_line(message: str) -> str:
    """מסיר את שורת החתימה אם Opus הוסיף אותה בכל זאת"""
    lines = message.rstrip().split("\n")
    while lines and ("שאו מרום" in lines[-1] or lines[-1].strip() == ""):
        lines.pop()
    return "\n".join(lines)


# ══════════════════════════════════════════
# 8. נקודת כניסה ראשית
# ══════════════════════════════════════════

def is_shabbat_or_yomtov_now(daytime_run: bool) -> bool:
    """
    ריצת 13:00 (daytime_run=True):  אם אתמול היו נרות → חג → לא שולח
    ריצת 21:00 (daytime_run=False): החג כבר יצא → תמיד False
    """
    if not daytime_run:
        return False  # ב-21:00 החג תמיד יצא כבר

    now   = datetime.now(ISRAEL_TZ)
    today = now.date()
    yesterday = today - timedelta(days=1)

    url = (
        f"https://www.hebcal.com/shabbat?cfg=json"
        f"&geonameid={GEONAMEID}&m=50&lg=s"
        f"&yt=G&date={yesterday.isoformat()}"
    )
    try:
        items = requests.get(url, timeout=10).json().get("items", [])
        for item in items:
            if item.get("category") == "candles":
                try:
                    candles_dt = datetime.fromisoformat(item["date"]).astimezone(ISRAEL_TZ)
                    if candles_dt.date() == yesterday:
                        return True  # אתמול היו נרות ביום אתמול עצמו → היום שבת/חג
                except Exception:
                    pass
    except Exception:
        pass

    # בדוק גם אם היום הייתה הדלקת נרות שכבר עברה
    url_today = (
        f"https://www.hebcal.com/shabbat?cfg=json"
        f"&geonameid={GEONAMEID}&m=50&lg=s"
        f"&yt=G&date={today.isoformat()}"
    )
    try:
        items = requests.get(url_today, timeout=10).json().get("items", [])
        for item in items:
            if item.get("category") == "candles":
                dt = datetime.fromisoformat(item["date"]).astimezone(ISRAEL_TZ)
                if dt <= now:
                    return True  # הדלקת נרות כבר עברה היום
    except Exception:
        pass

    return False


def was_sent_today(history: dict) -> bool:
    """בודק אם כבר נשלחה הודעה היום"""
    today_key = datetime.now(ISRAEL_TZ).strftime("%Y-%m-%d")
    return today_key in history


def detect_motzei(now: datetime) -> bool:
    """בודק אם עכשיו מוצאי שבת/חג – הבדלה הייתה היום לאחרונה (עד 4 שעות אחורה)"""
    today = now.date()
    url = (
        f"https://www.hebcal.com/shabbat?cfg=json"
        f"&geonameid={GEONAMEID}&m=50&lg=s"
        f"&yt=G&date={today.isoformat()}"
    )
    try:
        items = requests.get(url, timeout=10).json().get("items", [])
        for item in items:
            if item.get("category") == "havdalah":
                dt = datetime.fromisoformat(item["date"]).astimezone(ISRAEL_TZ)
                hours_since = (now - dt).total_seconds() / 3600
                if dt.date() == today and 0 <= hours_since <= 4:
                    return True
    except Exception:
        pass
    return False


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
        if is_shabbat_or_yomtov_now(daytime_run=True):
            print("✡️ עכשיו שבת/חג – לא שולח")
            sys.exit(0)

    else:
        # ── ריצת 21:00 ──
        # שלח אם: לא נשלח היום, ולא שבת/חג עכשיו

        if was_sent_today(history) and os.environ.get("FORCE_SEND", "false").lower() != "true":
            print("✅ כבר נשלחה הודעה היום – לא שולח שוב (הוסף force_send=true להרצה ידנית)")
            sys.exit(0)

        if is_shabbat_or_yomtov_now(daytime_run=False):
            print("✡️ עכשיו שבת/חג – לא שולח")
            sys.exit(0)

        print("🌙 ריצת לילה – שולח הודעה")

    # זיהוי מוצאי שבת/חג
    is_motzei = (hour >= 17) and detect_motzei(now)
    if is_motzei:
        print("✡️ מוצאי שבת/חג – שולח בשבוע טוב")

    # ── איסוף נתונים ────────────────────
    print("📚 טוען היסטוריית הודעות...")
    today_key   = now.strftime("%Y-%m-%d")
    history_text = format_history_for_prompt(history)

    print("📡 מושך נתוני עננות...")
    cloud_pct           = get_cloud_cover()
    cloud_status, cloud_desc = cloud_label(cloud_pct)

    print("🔭 מחשב נתוני ירח וכוכבים (ל-19:30 ישראל)...")
    astro = get_astronomical_data()

    print("🛸 מחשב מעברי ISS...")
    iss   = get_station_passes()

    print("✡️ שולף לוח שנה יהודי...")
    jdate    = get_jewish_date_info()
    print(f"🗓️ תאריך עברי: {jdate['hebrew_display']} | after_sunset: {jdate['after_sunset']}")
    j_events = get_jewish_events_today()
    print("\n" + "─"*40)
    print("✡️ אירועים יהודיים (raw):")
    for e in j_events:
        print(f"  {e}")
    print("─"*40 + "\n")

    print("🌙 קידוש לבנה...")
    kl_text = get_kiddush_levana_text()
    if kl_text:
        print(f"  {kl_text.split(chr(10))[0]}")
    else:
        print("  (לא רלוונטי היום)")

    date_str   = now.strftime("%d/%m/%Y")

    print("📡 מחפש חדשות חלל ואסטרונומיה...")
    # בונה הקשר יהודי-אסטרונומי לקריאת החיפוש
    jewish_context_parts = []
    if j_events:
        jewish_context_parts.extend(j_events)
    jewish_context = "\n".join(jewish_context_parts)
    space_news = gather_space_news(date_str, jewish_context)
    print("\n" + "─"*40)
    print("📡 חדשות שנאספו:")
    print(space_news)
    print("─"*40 + "\n")

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
        "history_text":  history_text,
        "space_news":    space_news,
        "is_motzei":     is_motzei,
    }
    message = generate_message(payload)

    print("🔧 תיקונים אוטומטיים...")
    message = auto_fix(message)

    print("🕐 תיקון פתיחה לפי שעה...")
    message = fix_opening(message, payload)

    print("📅 תיקון שורת תאריך...")
    message = fix_date_line(message, payload)

    print("🔍 בקרה לוגית...")
    message = quality_check(message, payload)

    print("✍️ מגיה עברית...")
    message = proofread_hebrew(message)

    print("🔧 מסיר חתימה (אם Opus הוסיף)...")
    message = strip_closing_line(message)

    print("📎 מוסיף תוספת קבועה (אירועים + קידוש לבנה + חתימה)...")
    footer = build_footer(payload)
    message = message + "\n\n" + footer

    print("\n" + "═"*50)
    print(message)
    print("═"*50 + "\n")

    # ── שליחה ───────────────────────────
    print("📱 שולח WhatsApp...")
    if os.environ.get("DRY_RUN", "false").lower() == "true":
        print("🔍 DRY_RUN=true – לא שולח ווטסאפ")
    else:
        send_whatsapp(message)

    # ── שמירת היסטוריה ──────────────────
    print("📚 מסכם ושומר היסטוריה...")
    summary = extract_summary_from_message(message, payload)
    save_history(history, today_key, summary)
    print(f"✅ נשמר: {summary}")
    print("✅ הכל הושלם!")


if __name__ == "__main__":
    main()
