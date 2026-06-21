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

# ברכות הפתיחה האפשריות – כל הודעה חייבת להתחיל באחת מהן
VALID_OPENINGS = [
    "בוקר טוב", "צהריים טובים", "ערב טוב", "לילה טוב",
    "שבוע טוב", "מוצאי שבת", "חודש טוב",
]

# ── משתני סביבה ──────────────────────────
ANTHROPIC_API_KEY      = os.environ["ANTHROPIC_API_KEY"]
GREEN_API_INSTANCE     = os.environ["GREEN_API_INSTANCE"]
GREEN_API_TOKEN        = os.environ["GREEN_API_TOKEN"]
WHATSAPP_GROUP_ID      = os.environ["WHATSAPP_GROUP_ID"]


# ══════════════════════════════════════════
# 1. לוח שנה יהודי, זמנים ושבת/חג
# ══════════════════════════════════════════

def get_jewish_date_info() -> dict:
    from pyluach import dates as pdates, hebrewcal

    now          = datetime.now(ISRAEL_TZ)
    today_il     = now.date()
    after_sunset = now.hour >= 17

    hdate = pdates.HebrewDate.from_pydate(today_il)
    print(f"📅 pyluach: {today_il} → {hdate.hebrew_day()} {hdate.month_name(hebrew=True)}")
    if after_sunset:
        hdate = hdate + 1

    hd = hdate.day
    hm = hdate.month_name(hebrew=True)
    hy = hebrewcal.Year(hdate.year).year_string()

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
    from pyluach import dates as pdates, hebrewcal as pheb

    now   = datetime.now(ISRAEL_TZ)
    today = now.date()

    hdate = pdates.HebrewDate.from_pydate(today) + 1

    events = []

    holiday = hdate.holiday(hebrew=True, israel=True)
    if holiday:
        events.append(f"✡️ {holiday}")

    fast = pheb.fast_day(hdate, hebrew=True)
    if fast:
        events.append(f"🕯️ {fast}")

    if hdate.day in (1, 30):
        if hdate.day == 30:
            next_month = pheb.Month(hdate.year, hdate.month) + 1
            rc_month = next_month.month_name(hebrew=True)
        else:
            rc_month = hdate.month_name(hebrew=True)
        events.append(f"🌑 ראש חודש {rc_month} – חודש טוב!")

    return events


# ══════════════════════════════════════════
# 2. עננות – Open-Meteo (חינמי)
# ══════════════════════════════════════════

def get_cloud_cover() -> int | None:
    """ממוצע עננות ב-20:00–23:00 בישראל. מחזיר None כשאין נתון זמין."""
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        f"&hourly=cloudcover"
        f"&timezone=Asia%2FJerusalem"
        f"&forecast_days=1"
    )
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data   = r.json()
        times  = data["hourly"]["time"]
        clouds = data["hourly"]["cloudcover"]

        evening = [c for t, c in zip(times, clouds)
                   if 20 <= int(t.split("T")[1][:2]) <= 23]
        return round(sum(evening) / len(evening)) if evening else None
    except Exception as e:
        print(f"⚠️ לא הצלחתי למשוך נתוני עננות: {e}")
        return None


def cloud_label(pct: int) -> tuple[str, str]:
    if pct < CLOUD_CLEAR:
        return "clear",         f"שמיים בהירים ({pct}%) – לילה מושלם לצפייה! 🌟"
    elif pct < CLOUD_HOPEFUL:
        return "partial",       f"עננות חלקית ({pct}%) – יש סיכוי טוב לחלונות פתוחים בשמיים 🤞"
    elif pct < CLOUD_POOR:
        return "mostly_cloudy", f"עננות גבוהה ({pct}%) – בתקווה שהענן ייפתח ויאפשר הצצה 🌥️"
    else:
        return "cloudy",        f"עננות כבדה ({pct}%) – לא מומלץ לצאת לצפייה הלילה ☁️"


# ══════════════════════════════════════════
# 3. ISS – מעברים (Skyfield + Celestrak TLE)
# ══════════════════════════════════════════

def _azimuth_to_hebrew(az: float) -> str:
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


def _get_satellite_passes(norad_id: int, name: str, ts, obs, eph=None) -> list[dict]:
    """מחשב מעברים של לוויין נתון מעל נקודת התצפית.

    אם מועבר ``eph`` (ephemeris פלנטרי), הפונקציה מסננת רק מעברים *נראים לעין*:
    השמש מתחת ל-6°- אצל הצופה (דמדומים אזרחיים או חשוך) **וגם** הלוויין מואר ע"י השמש
    (לא בצל כדור הארץ).
    """

    # ══════════════════════════════════════════
    # שליפת TLE – מספר מקורות + retry על 503
    # ══════════════════════════════════════════
    def _fetch_tle_from_url(url: str) -> tuple | None:
        """מנסה לשלוף TLE מ-URL. מחזיר (line1, line2) או None."""
        for attempt in range(3):
            try:
                r = requests.get(url, timeout=10)
                if r.status_code == 503:
                    wait = 5 * (attempt + 1)
                    print(f"  ⏳ {name} TLE: 503 מ-{url} – ממתין {wait}ש' ומנסה שוב")
                    time.sleep(wait)
                    continue
                if r.status_code != 200:
                    print(f"  ⚠️ {name} TLE: HTTP {r.status_code} מ-{url}")
                    return None
                lines = [l.strip() for l in r.text.strip().splitlines() if l.strip()]
                if len(lines) < 2:
                    print(f"  ⚠️ {name} TLE: תשובה קצרה מדי ({len(lines)} שורות)")
                    return None
                l1, l2 = lines[-2], lines[-1]
                if not (l1.startswith("1 ") and l2.startswith("2 ")):
                    print(f"  ⚠️ {name} TLE: תוכן לא תקין ('{l1[:20]}')")
                    return None
                return l1, l2
            except Exception as e:
                print(f"  ⚠️ {name} TLE שגיאה ({url}): {e}")
                return None
        return None

    def _fetch_tle_from_json(url: str) -> tuple | None:
        """שולף TLE מ-API שמחזיר JSON (tle.ivanstanojevic.me)."""
        try:
            r = requests.get(url, timeout=10)
            if r.status_code != 200:
                print(f"  ⚠️ {name} TLE (JSON): HTTP {r.status_code}")
                return None
            data = r.json()
            l1 = data.get("line1", "")
            l2 = data.get("line2", "")
            if not (l1.startswith("1 ") and l2.startswith("2 ")):
                print(f"  ⚠️ {name} TLE (JSON): תוכן לא תקין")
                return None
            return l1, l2
        except Exception as e:
            print(f"  ⚠️ {name} TLE (JSON) שגיאה: {e}")
            return None

    # סדר עדיפויות: Celestrak (gp.php) → Celestrak (legacy) → ivanstanojevic
    TLE_SOURCES = [
        ("txt",  f"https://celestrak.org/NORAD/elements/gp.php?CATNR={norad_id}&FORMAT=TLE"),
        ("txt",  f"https://celestrak.org/satcat/tle.php?CATNR={norad_id}"),
        ("json", f"https://tle.ivanstanojevic.me/api/tle/{norad_id}"),
    ]

    line1 = line2 = None
    for fmt, url in TLE_SOURCES:
        result = _fetch_tle_from_json(url) if fmt == "json" else _fetch_tle_from_url(url)
        if result:
            line1, line2 = result
            print(f"  ✅ {name} TLE נשלף (epoch: {line1[18:32].strip()})")
            break

    if not line1:
        print(f"  ❌ {name}: כל מקורות ה-TLE נכשלו – מדלג")
        return []

    # ══════════════════════════════════════════
    # חישוב מעברים
    # ══════════════════════════════════════════
    try:
        from skyfield.api import EarthSatellite
        sat = EarthSatellite(line1, line2, name, ts)

        now_il = datetime.now(ISRAEL_TZ)
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
        skipped_invisible = 0
        for p in passes:
            # ── סינון נראות לעין: שמש מתחת ל-6°- אצל הצופה והלוויין מואר ──
            if eph is not None:
                try:
                    peak_ti = p.get("peak_ti", p["rise_ti"])
                    sun_alt_at_obs = (
                        (eph["earth"] + obs).at(peak_ti)
                        .observe(eph["sun"]).apparent().altaz()[0].degrees
                    )
                    sat_sunlit = bool(sat.at(peak_ti).is_sunlit(eph))
                    if sun_alt_at_obs > -6.0 or not sat_sunlit:
                        skipped_invisible += 1
                        continue
                except Exception as vis_err:
                    print(f"  ⚠️ {name}: שגיאת בדיקת נראות – ממשיך בלי לסנן ({vis_err})")

            try:
                diff_rise = (sat - obs).at(p["rise_ti"])
                alt_r, az_r, _ = diff_rise.altaz()
                diff_set  = (sat - obs).at(p.get("peak_ti", p["rise_ti"]))
                alt_p, az_p, _ = diff_set.altaz()

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

        if skipped_invisible:
            print(f"  ⏭️ {name}: סוננו {skipped_invisible} מעברים לא-נראים (שמיים בהירים או לוויין בצל)")

        return result

    except Exception as e:
        print(f"⚠️ שגיאת {name}: {e}")
        return []


def get_station_passes() -> list[str]:
    try:
        from skyfield.api import load, wgs84
        ts  = load.timescale()
        obs = wgs84.latlon(LAT, LON, elevation_m=ALT)

        # ephemeris פלנטרי לבדיקת נראות לעין (~17MB, נשמר במטמון מקומי).
        # אם הטעינה נכשלת ממשיכים בלי סינון נראות.
        try:
            eph = load("de421.bsp")
        except Exception as e:
            print(f"  ⚠️ טעינת de421.bsp נכשלה ({e}) – ממשיך בלי סינון נראות")
            eph = None

        iss_passes  = _get_satellite_passes(25544, "ISS",      ts, obs, eph=eph)
        css_passes  = _get_satellite_passes(48274, "טיאנגונג", ts, obs, eph=eph)

        # סינון מעברים שכבר התרחשו: שומרים מעברים עתידיים
        # ומעברים שעדיין בעיצומם (עד 5 דק' אחרי הזריחה).
        now = datetime.now(ISRAEL_TZ)
        cutoff = now - timedelta(minutes=5)
        before_iss = len(iss_passes)
        before_css = len(css_passes)
        iss_passes = [p for p in iss_passes if p["rise_dt"] > cutoff]
        css_passes = [p for p in css_passes if p["rise_dt"] > cutoff]
        skipped = (before_iss - len(iss_passes)) + (before_css - len(css_passes))
        if skipped:
            print(f"  ⏭️ סוננו {skipped} מעברים שכבר התרחשו")

        result = []

        double_pass = False
        if iss_passes and css_passes:
            for ip in iss_passes:
                for cp in css_passes:
                    diff = abs((ip["rise_dt"] - cp["rise_dt"]).total_seconds())
                    if diff < 600:
                        double_pass = True
                        result.append(
                            f"🌟 *מעבר כפול הלילה!* תחנת החלל הבינלאומית והסינית בשמיים יחד\n"
                            f"   🛸 *תחנת החלל הבינלאומית* (ISS): {ip['rise_str']} מ{ip['dir_rise']} "
                            f"לכיוון {ip['dir_set']} (שיא {ip['alt_peak']}°, {ip['brightness']})\n"
                            f"   🛸 *תחנת החלל הסינית* (טיאנגונג): {cp['rise_str']} מ{cp['dir_rise']} "
                            f"לכיוון {cp['dir_set']} (שיא {cp['alt_peak']}°, {cp['brightness']})"
                        )

        if not double_pass:
            for p in iss_passes[:1]:
                result.append(
                    f"🛸 *תחנת החלל הבינלאומית* (ISS) עוברת ב-{p['rise_str']} – "
                    f"מ{p['dir_rise']} לכיוון {p['dir_set']} "
                    f"(שיא {p['alt_peak']}°, {p['brightness']})"
                )
            for p in css_passes[:1]:
                result.append(
                    f"🛸 *תחנת החלל הסינית* (טיאנגונג) עוברת ב-{p['rise_str']} – "
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
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_history(history: dict, today_key: str, summary: dict):
    history[today_key] = summary

    cutoff = (datetime.now(ISRAEL_TZ) - timedelta(days=HISTORY_DAYS)).strftime("%Y-%m-%d")
    old_keys = [k for k in history if k < cutoff]
    for k in old_keys:
        del history[k]

    HISTORY_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def format_history_for_prompt(history: dict) -> str:
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
    try:
        import ephem

        obs       = ephem.Observer()
        obs.lat   = str(LAT)
        obs.lon   = str(LON)
        obs.elev  = ALT

        # שלב 1: חישוב שקיעה/זריחה מצהריים
        noon_il  = datetime.now(ISRAEL_TZ).replace(hour=12, minute=0, second=0, microsecond=0)
        noon_utc = noon_il.astimezone(pytz.utc)
        obs.date = noon_utc

        sun = ephem.Sun(obs)
        try:
            sunset_utc  = obs.next_setting(sun).datetime()
            sunset_dt   = sunset_utc.replace(tzinfo=pytz.utc).astimezone(ISRAEL_TZ)
            sunset      = sunset_dt.strftime("%H:%M")
            sunrise_utc = obs.next_rising(sun).datetime()
            sunrise     = sunrise_utc.replace(tzinfo=pytz.utc).astimezone(ISRAEL_TZ).strftime("%H:%M")
        except Exception:
            sunset_dt  = None
            sunset = sunrise = "N/A"

        # שלב 2: מעבר לזמן ערב (19:30) לכל שאר החישובים
        evening_il  = datetime.now(ISRAEL_TZ).replace(hour=19, minute=30, second=0, microsecond=0)
        evening_utc = evening_il.astimezone(pytz.utc)
        obs.date    = evening_utc

        # ── ירח ──
        moon = ephem.Moon(obs)
        pct  = round(moon.moon_phase * 100)

        prev_new = ephem.previous_new_moon(obs.date)
        age = float(obs.date - prev_new)

        if   age <  1.5: phase_name = "🌑 ירח חדש"
        elif age <  7.0: phase_name = "🌒 סהר גדל"
        elif age <  8.5: phase_name = "🌓 רבע ראשון"
        elif age < 14.0: phase_name = "🌔 ירח גדל"
        elif age < 15.5: phase_name = "🌕 ירח מלא"
        elif age < 21.0: phase_name = "🌖 ירח פוחת"
        elif age < 22.5: phase_name = "🌗 רבע אחרון"
        else:            phase_name = "🌘 סהר פוחת"

        # ── ירח – זריחה/שקיעה ביחס לשקיעת השמש ──
        obs_evening = ephem.Observer()
        obs_evening.lat  = obs.lat
        obs_evening.lon  = obs.lon
        obs_evening.elev = obs.elev
        if sunset_dt:
            obs_evening.date = ephem.Date(sunset_utc.strftime("%Y/%m/%d %H:%M:%S"))
        else:
            obs_evening.date = obs.date

        moon_evening = ephem.Moon(obs_evening)

        # *** חשב גובה לפני קריאות next_rising/next_setting ***
        moon_alt_evening = math.degrees(float(moon_evening.alt))
        moon_visible_evening = moon_alt_evening > 0

        moon_rise = None
        moon_set  = None
        moon_rise_passed = False
        moon_minutes_since_rise = None
        now_il = datetime.now(ISRAEL_TZ)
        try:
            # אם הירח כבר מעל האופק בשקיעה (טיפוסי לירח מלא) –
            # אנו רוצים את זמן הזריחה של היום (לפני השקיעה), לא של מחר.
            if moon_visible_evening:
                rise_utc = obs_evening.previous_rising(moon_evening).datetime()
            else:
                rise_utc = obs_evening.next_rising(moon_evening).datetime()
            rise_dt  = rise_utc.replace(tzinfo=pytz.utc).astimezone(ISRAEL_TZ)
            today_d    = evening_il.date()
            tomorrow_d = today_d + timedelta(days=1)
            relevant = (
                (rise_dt.date() == today_d    and rise_dt.hour >= 14) or
                (rise_dt.date() == tomorrow_d and rise_dt.hour <  12)
            )
            if relevant:
                moon_rise = rise_dt.strftime("%H:%M")
                moon_rise_passed = rise_dt < now_il
                if moon_rise_passed:
                    moon_minutes_since_rise = int(
                        (now_il - rise_dt).total_seconds() / 60
                    )
        except Exception:
            pass
        try:
            set_utc = obs_evening.next_setting(moon_evening).datetime()
            set_dt  = set_utc.replace(tzinfo=pytz.utc).astimezone(ISRAEL_TZ)
            if 19 <= set_dt.hour or set_dt.hour < 12:
                moon_set = set_dt.strftime("%H:%M")
        except Exception:
            pass

        # זיהוי תקופת ירח מלא (כולל לילה לפני/אחרי) –
        # להמלצה על תצפית בזריחת הירח הכתומה והגדולה
        is_full_moon_period = (13.0 <= age <= 16.5) or pct >= 95

        # ── כוכבי לכת – מחושבים ב-19:30 ──
        planet_defs = [
            ("נוגה ♀",   ephem.Venus),
            ("מאדים ♂",  ephem.Mars),
            ("צדק ♃",    ephem.Jupiter),
            ("שבתאי ♄",  ephem.Saturn),
            ("אורנוס ⛢", ephem.Uranus),
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

        # ── היפוך/שוויון אסטרונומי (רק אם בתוך ±2 ימים) ──
        # שונה מ"תקופות שמואל" (לוח עברי, ≈7 ביולי) – זה האירוע האסטרונומי
        # האמיתי: היום הארוך/הקצר בשנה או יום-ולילה-שווים.
        seasonal_event = None
        try:
            ref = ephem.Date(evening_utc)
            candidates = [
                ("solstice", ephem.next_solstice(ref)),
                ("solstice", ephem.previous_solstice(ref)),
                ("equinox",  ephem.next_equinox(ref)),
                ("equinox",  ephem.previous_equinox(ref)),
            ]
            kind, edate = min(candidates, key=lambda c: abs(c[1] - ref))
            ev_dt = edate.datetime().replace(tzinfo=pytz.utc).astimezone(ISRAEL_TZ)
            days_away = (ev_dt.date() - now_il.date()).days
            if abs(days_away) <= 2:
                m = ev_dt.month
                if kind == "solstice":
                    label = ("היפוך הקיץ – היום הארוך בשנה" if m == 6
                             else "היפוך החורף – היום הקצר בשנה")
                else:
                    label = ("שוויון האביב – יום ולילה שווים" if m == 3
                             else "שוויון הסתיו – יום ולילה שווים")
                when = ("היום"  if days_away ==  0 else
                        "מחר"   if days_away ==  1 else
                        "אתמול" if days_away == -1 else
                        f"בעוד {days_away} ימים" if days_away > 0 else
                        f"לפני {abs(days_away)} ימים")
                seasonal_event = f"{label} ({when}, {ev_dt.strftime('%d/%m %H:%M')})"
        except Exception:
            pass

        return {
            "moon_pct":             pct,
            "moon_phase":           phase_name,
            "moon_age":             round(age, 1),
            "moon_rise":            moon_rise,
            "moon_rise_passed":     moon_rise_passed,
            "moon_minutes_since_rise": moon_minutes_since_rise,
            "moon_set":             moon_set,
            "moon_visible_evening": moon_visible_evening,
            "is_full_moon_period":  is_full_moon_period,
            "seasonal_event":       seasonal_event,
            "planets_visible":      planets_visible,
            "sunset":               sunset,
            "sunrise":              sunrise,
        }

    except ImportError:
        print("⚠️ ephem לא מותקן – מחזיר נתונים חלקיים")
        return {
            "moon_pct": 50, "moon_phase": "🌔 ירח גדל",
            "moon_rise": None, "moon_rise_passed": False,
            "moon_minutes_since_rise": None,
            "moon_set": None,
            "is_full_moon_period": False,
            "seasonal_event": None,
            "planets_visible": [], "sunset": "N/A", "sunrise": "N/A",
        }


# ══════════════════════════════════════════
# 4.5  קבוצות כוכבים נראות לפי עונה (מרכז ישראל)
# ══════════════════════════════════════════

# מבוסס על נראות ערב מוקדם (~21:00) ממרכז ישראל (~31° צפון).
# כל ערך הוא רשימת תיאורים קצרים לפי כיוון.
_CONSTELLATIONS_BY_MONTH: dict[int, list[str]] = {
    1:  ["במזרח: *אוריון* עם חגורתו המפורסמת",
         "במרכז: *השור* עם *הכימה* ו*אַלְדֵבָּרָן* האדום",
         "צפון-מזרח: *תאומים*, ובמערב *הציידים* עם *סיריוס*"],
    2:  ["דרום: *אוריון* גבוה במרכז השמיים",
         "מערב: *השור* יורד",
         "מזרח: *אריה* עולה עם *רגולוס*"],
    3:  ["מערב: *אוריון* יורד לאופק",
         "מעל הראש: *תאומים*",
         "מזרח: *אריה* גבוה",
         "צפון: *הדובה הגדולה*"],
    4:  ["מעל הראש: *אריה* עם *רגולוס*",
         "מזרח: *בתולה* עם *ספיקה* הכחולה",
         "צפון: *הדובה הגדולה* גבוהה"],
    5:  ["מזרח: *רועה דובים* עם *ארקטורוס* הכתום",
         "דרום: *בתולה*",
         "מערב: *אריה* יורד",
         "צפון: *הדובה הגדולה*"],
    6:  ["דרום-מזרח: *עקרב* עולה עם *אנטארס* האדום",
         "מזרח: *הרקולס*",
         "מעל הראש: *רועה דובים* עם *ארקטורוס*"],
    7:  ["דרום: *עקרב* גבוה עם *אנטארס*",
         "מזרח: *משולש הקיץ* (וגה, אלטיר, דנב) עולה",
         "מעל: *הרקולס*"],
    8:  ["מעל הראש: *משולש הקיץ* – וגה ב*נֶבֶל*, אלטיר ב*נֶשֶׁר*, דנב ב*בַּרְבּוּר*",
         "דרום: *עקרב* יורד, *קשת* עם מרכז שביל החלב",
         "מזרח: *פגסוס* מתחיל לעלות"],
    9:  ["מעל הראש: *משולש הקיץ* עדיין שולט",
         "מזרח: *פגסוס* ו*אנדרומדה* עם הגלקסיה M31",
         "צפון: *קסיופאה* בצורת W"],
    10: ["מעל הראש: *פגסוס* – הריבוע הגדול",
         "מזרח: *אנדרומדה* עם הגלקסיה הקרובה ביותר",
         "צפון: *קסיופאה*",
         "מערב: *משולש הקיץ* יורד"],
    11: ["מזרח: *השור* עם *הכימה* (אשכול הפלאיאדות), *אוריון* מתחיל לעלות מאוחר",
         "מעל הראש: *אנדרומדה* ו*פגסוס*",
         "צפון: *קסיופאה*"],
    12: ["מזרח: *אוריון* עולה עם חגורתו, אחריו *השור*",
         "מעל הראש: *השור* עם *הכימה*",
         "צפון: *קסיופאה* גבוהה"],
}


def get_visible_constellations(now: datetime | None = None) -> list[str]:
    if now is None:
        now = datetime.now(ISRAEL_TZ)
    return _CONSTELLATIONS_BY_MONTH.get(now.month, [])


# ══════════════════════════════════════════
# 5. יצירת ההודעה עם Claude Opus
# ══════════════════════════════════════════

from auto_fix import auto_fix


def strip_preamble(message: str) -> str:
    """חותך כל טקסט (ניתוח/הסבר של המודל) שלפני ברכת הפתיחה של ההודעה."""
    earliest = -1
    for opening in VALID_OPENINGS:
        idx = message.find(opening)
        if idx != -1 and (earliest == -1 or idx < earliest):
            earliest = idx
    if earliest > 0:
        return message[earliest:].strip()
    return message


def fix_opening(message: str, payload: dict) -> str:
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

    lines = message.split("\n", 1)
    first_line = lines[0]
    rest       = lines[1] if len(lines) > 1 else ""

    needs_fix = not any(first_line.startswith(o) for o in VALID_OPENINGS)
    wrong_opening = any(
        first_line.startswith(o) for o in VALID_OPENINGS
        if o != correct and not (correct == "ערב טוב" and o == "לילה טוב")
    )

    if needs_fix or wrong_opening:
        import re
        emoji_match = re.search(r'[\U00010000-\U0010ffff\u2600-\u26FF\u2700-\u27BF]', first_line)
        emoji = " " + emoji_match.group(0) if emoji_match else " 🌙"
        new_first = f"{correct}{emoji}"
        print(f"🔧 fix_opening: '{first_line.strip()}' → '{new_first}'")
        return new_first + "\n" + rest

    return message


def fix_date_line(message: str, payload: dict) -> str:
    import re

    jdate = payload["jdate"]
    now   = datetime.now(ISRAEL_TZ)
    correct_date = f"{now.day}.{now.month}.{now.year} | {jdate['hebrew_display']}"

    lines = message.split("\n")
    if len(lines) < 1:
        return message

    date_pattern = re.compile(r'^\d{1,2}\.\d{1,2}\.\d{4}\s*\|')
    filtered = [l for l in lines if not date_pattern.match(l.strip())]

    if len(filtered) >= 1:
        filtered.insert(1, correct_date)

    result = "\n".join(filtered)
    if result != message:
        print(f"🔧 fix_date_line: → '{correct_date}'")
    return result


def quality_check(message: str, payload: dict) -> str:
    sunset       = payload.get("astro", {}).get("sunset", "N/A")
    history_text = payload.get("history_text", "")

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
                f"אם לא מצאת בעיה – החזר את ההודעה כפי שהיא, מילה במילה.\n"
                f"החזר אך ורק את ההודעה הסופית – בלי ניתוח, בלי הסבר, בלי טקסט לפני או אחרי.\n\n"
                f"ההודעה:\n{message}"
            )
        }]
    }
    try:
        r = requests.post(CLAUDE_API, headers=headers, json=body, timeout=30)
        r.raise_for_status()
        result = strip_preamble(r.json()["content"][0]["text"].strip())
        if result and len(result) >= len(message) * 0.85:
            print("✅ quality_check: הושלם")
            return result
        print("⚠️ quality_check: תוצאה קצרה מדי – שומר מקורי")
        return message
    except Exception as e:
        print(f"⚠️ quality_check נכשל: {e} – ממשיך בלי")
        return message


def proofread_hebrew(message: str) -> str:
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
                "• 'בראייה ערומה' / 'בעין רגילה' → 'בעין בלתי מזוינת'\n"
                "• מיילים → המר לקילומטרים (1 מייל = 1.609 ק\"מ)\n"
                "• 'קרייטר' / 'קרטר' → 'מכתש'\n"
                "• ו/ה/ב/כ/ל/מ/ש לפני *בולד* – כנס לפנים: *ונוגה* לא ו*נוגה*\n\n"
                "החזר את ההודעה המתוקנת בלבד, ללא הסברים.\n\n"
                f"ההודעה:\n{message}"
            )
        }]
    }
    try:
        r = requests.post(CLAUDE_API, headers=headers, json=body, timeout=30)
        r.raise_for_status()
        return strip_preamble(r.json()["content"][0]["text"].strip())
    except Exception as e:
        print(f"⚠️ הגהה נכשלה: {e} – שולח הודעה מקורית")
        return message


def gather_space_news(date_str: str, jewish_context: str = "", recent_news: list = None) -> str:
    headers = {
        "x-api-key":         ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type":      "application/json",
    }

    jewish_section = f"""
אירועים יהודיים-אסטרונומיים ידועים הלילה (כבר מחושבים, אין צורך לחפש):
{jewish_context}
""" if jewish_context else ""

    recent_section = ""
    if recent_news:
        items = "\n".join(f"• {n}" for n in recent_news if n)
        recent_section = f"""
נושאים שכוסו לאחרונה בהודעות קודמות – אל תחזור עליהם, חפש משהו אחר:
{items}
"""

    # פרסור התאריך לחיפוש "ביום זה בהיסטוריה"
    try:
        _dt_for_hist = datetime.strptime(date_str, "%d/%m/%Y")
        day_month_en = _dt_for_hist.strftime("%B %-d")  # למשל "May 9"
    except Exception:
        day_month_en = date_str

    body = {
        "model":      CLAUDE_MODEL,
        "max_tokens": 1000,
        "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        "messages": [{"role": "user", "content": f"""אתה עיתונאי חלל. המשימה שלך היא לחפש ולסנן בלבד – לא לכתוב הודעה.
{jewish_section}{recent_section}
חפש באינטרנט לתאריך {date_str}:
1. חדשות חלל בולטות השבוע – תגליות ג'יימס וב/האבל, שיגורים מיוחדים, גילויים חדשים
2. אירועים אסטרונומיים – שביטים נראים, ליקויים, מטר מטאורים פעיל, Starlink מישראל
3. כל דבר שחובב אסטרונומיה ישראלי לא יידע בלעדיך

⛔ אל תכלול: "תמונת היום של נאס"א" (APOD), פוסטים בסגנון תיאור-תמונה,
   ציוצים/פוסטים ב-X/טוויטר/אינסטגרם, "snapshot of the day" – אלה לא חדשות.
   רק אירועים, תגליות, שיגורים ופרסומים מדעיים.

🔴 חובה (אל תדלג!): "ביום זה בהיסטוריית החלל" –
חפש: "{day_month_en} space history" / "this day in space history {day_month_en}".
הבא **לפחות אירוע אחד** היסטורי מעניין שקרה בתאריך {day_month_en} בשנה כלשהי.
עדיפות: נחיתות (אפולו, מאדים), שיגורים ראשונים, תגליות מדעיות, אסונות, צעדי חלל ראשונים, מבצעי וויאג'ר/קסיני/האבל.
אם לא מצאת אירוע חזק לתאריך המדויק – בחר אירוע מהשבוע הנוכחי ({date_str} ± 3 ימים).
ציין שנה מפורשת ושם הדמות/החללית/המשימה.

החזר את התשובה במבנה הזה (חובה לכלול את כל הסעיפים):

== חדשות שוטפות ==
• שם האירוע/תגלית – עובדה אחת-שתיים – נראה מישראל: כן/לא/חלקית – פורסם: תאריך
(2-4 פריטים)

== ביום זה בהיסטוריה ==
• [שנה] – שם האירוע/המשימה – עובדה אחת על מה קרה בדיוק
(לפחות פריט אחד, רצוי 1-2)

ללא עיצוב, ללא סגנון, ללא המלצות. רק עובדות."""}]
    }

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
    cloud_pct    = payload["cloud_pct"]
    cloud_desc   = payload["cloud_desc"]
    if cloud_pct is None:
        cloud_block = "🌤 עננות: אין נתון זמין – אל תתייחס לעננות או למצב השמיים בהודעה."
    else:
        cloud_block = f"🌤 עננות: {cloud_pct}%\n   הערכה: {cloud_desc}"
    astro        = payload["astro"]
    iss          = payload["iss"]
    j_events     = payload["jewish_events"]
    jdate        = payload["jdate"]
    date_str     = payload["date_str"]

    history_text = payload.get("history_text", "אין היסטוריה.")
    is_motzei    = payload.get("is_motzei", False)

    rules_file = Path(__file__).parent / "rules.md"
    if rules_file.exists():
        STATIC_RULES = rules_file.read_text(encoding="utf-8")
        print("📋 כללים נטענו מ-rules.md")
    else:
        STATIC_RULES = """אתה חובב אסטרונומיה שמנהל קבוצת WhatsApp. כתוב בעברית תקנית, חמה, מדויקת.
מקסימום 150 מילה."""
        print("⚠️ rules.md לא נמצא – משתמש בכללים מינימליים")

    now_il       = datetime.now(ISRAEL_TZ)
    current_time = now_il.strftime("%H:%M")
    is_daytime   = now_il.hour < 17

    _mr        = astro.get('moon_rise')
    _ms        = astro.get('moon_set')
    _mv        = astro.get('moon_visible_evening', False)
    _is_full   = astro.get('is_full_moon_period', False)
    _mr_passed = astro.get('moon_rise_passed', False)
    _mr_mins   = astro.get('moon_minutes_since_rise')

    # סטטוס בסיסי – משפט אחד קצר וברור (ללא משפטים מורכבים).
    if _mv and _ms:
        moon_status = f"🌙 גלוי כבר בתחילת הלילה, ישקע ב-{_ms}"
    elif _mv:
        moon_status = "🌙 גלוי כבר בתחילת הלילה ויישאר גלוי כל הלילה"
    elif _mr and not _mr_passed:
        moon_status = f"🌙 יזרח ב-{_mr} – עד אז השמיים חשוכים"
    elif _mr and _mr_passed:
        moon_status = f"🌙 זרח כבר ב-{_mr}"
    else:
        moon_status = "🌙 לא יהיה גלוי כל הלילה"

    # רמז נפרד לירח מלא – נוסח שונה לכל תרחיש כדי למנוע מתח שגוי
    full_moon_hint = ""
    if _is_full:
        if _mr and not _mr_passed:
            full_moon_hint = (
                f"   💡 *תקופת ירח מלא*. הזריחה ב-{_mr} תהיה תצפית מרשימה: "
                f"ירח כתום וגדול על האופק המזרחי. המלץ לכוון את השעון לזמן הזריחה."
            )
        elif _mr and _mr_passed and _mr_mins is not None and _mr_mins <= 90:
            full_moon_hint = (
                f"   💡 *תקופת ירח מלא*. הירח זרח לפני {_mr_mins} דקות (ב-{_mr}) "
                f"ועדיין נמוך באופק המזרחי – הצצה עכשיו עדיין תופסת אותו כתום וגדול."
            )
        elif _mv:
            # ירח מלא, גלוי, זרח לפני יותר משעה וחצי – אור חזק ותצפית מוגבלת
            full_moon_hint = (
                f"   💡 *תקופת ירח מלא*. אור הירח חזק הלילה ויקשה על תצפית כוכבים חלשים – "
                f"שווה לציין זאת לקוראים."
            )
        # אם תקופת ירח מלא אבל הירח לא גלוי כרגע (שקע / לפני זריחה לא רלוונטית) – אין רמז
        # מיוחד; הסטטוס הבסיסי כבר אומר את הצורך.

    constellations = get_visible_constellations(now_il)
    constellations_block = (
        chr(10).join(f"   {c}" for c in constellations)
        if constellations else "   אין מידע עונתי"
    )

    DYNAMIC_DATA = f"""═══════════════════════════════
נתוני הערב — {date_str} | שעה: {current_time}
{'⚠️ מוצאי שבת/חג – פתח ב"שבוע טוב"!' if is_motzei else ''}
{'⚠️ שעת אחר הצהריים – פתח ב"צהריים טובים" ולא ב"ערב טוב"!' if is_daytime else ''}
═══════════════════════════════

📅 תאריך עברי עכשיו: {jdate['hebrew_display']}
⚠️ הלילה הקרוב (אחרי שקיעה ב-{astro.get('sunset','N/A')}) יהיה כבר היום העברי הבא – אל תכתוב על אירועי היום כאילו הם "הלילה"!

{cloud_block}

🌙 הירח: {astro['moon_phase']} ({astro['moon_pct']}% מואר, גיל {astro['moon_age']} ימים)
   {moon_status}
{full_moon_hint}

🌅 שקיעת שמש: {astro.get('sunset','N/A')}
🌄 זריחת שמש מחר: {astro.get('sunrise','N/A')}
{f"🌞 אירוע עונתי: {astro['seasonal_event']} – חובה לשלב משפט אחד קצר על כך (היום הארוך/הקצר בשנה / יום ולילה שווים)." if astro.get('seasonal_event') else ''}

🪐 כוכבי לכת נראים הלילה (מחושב ל-19:30 ישראל):
{chr(10).join(astro['planets_visible']) or "אין כוכבי לכת בולטים בגובה מספיק"}

🌌 קבוצות כוכבים בולטות בערב (לפי עונה):
{constellations_block}
   ⓘ אם הלילה חשוך (עננות נמוכה + אין ירח מציק) – שלב משפט קצר על קבוצות הכוכבים: ציין כיוון אחד-שניים בולטים. אל תפרט יותר מדי, רק מסגרת לתצפית.

🛸 מעברי תחנות חלל (פתחים תמיד עם הטקסט העברי, לא עם "ISS" באנגלית):
{chr(10).join(iss) if iss else "אין מעברים הלילה"}
   ⓘ הזמנים לעיל כבר מסוננים ושייכים לעתיד או למעבר שעדיין בעיצומו. *לעולם אל תכתוב "ISS" בתחילת שורה* – פתח תמיד ב"תחנת החלל הבינלאומית" / "תחנת החלל הסינית". אם השורה מתחילה באנגלית, ב-WhatsApp הכיוון מתחרבש.

✡️ אירועים יהודיים היום:
{chr(10).join(j_events) if j_events else "אין אירוע מיוחד הלילה"}

🗂 היסטוריית הודעות אחרונות:
{history_text}

📡 חדשות חלל ואסטרונומיה (נאספו בנפרד):
{payload.get('space_news', 'אין חדשות זמינות')}
   ⓘ חובה: אם בנתונים יש סעיף "ביום זה בהיסטוריה" – שלב **משפט אחד** (לא יותר) על האירוע ההיסטורי בתוך פסקת החדשות. זו פינה קבועה של הבוט – אל תדלג עליה.

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
        "model":      CLAUDE_MODEL_WRITER,
        "max_tokens": 1200,
        "messages":   [initial_message],
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
    raw = strip_preamble(raw)
    return raw or "⚠️ לא הצלחתי לייצר הודעה"


# ══════════════════════════════════════════
# 6. שליחת WhatsApp (Green API)
# ══════════════════════════════════════════

def send_whatsapp(message: str):
    url = (
        f"https://api.green-api.com/waInstance{GREEN_API_INSTANCE}"
        f"/sendMessage/{GREEN_API_TOKEN}"
    )
    # linkPreview=False מבטל את כרטיס התצוגה-המקדימה ש-WhatsApp מייצר
    # לקישור (למשל קישור ההצטרפות לקבוצה), שאחרת "משתלט" על ראש ההודעה.
    payload = {
        "chatId": WHATSAPP_GROUP_ID,
        "message": message,
        "linkPreview": False,
    }
    r = requests.post(url, json=payload, timeout=15)
    r.raise_for_status()
    print(f"✅ נשלח | idMessage: {r.json().get('idMessage','?')}")


def _was_mentioned_recently(title: str, history: dict, today: date, days_back: int) -> bool:
    """האם הכותרת הוזכרה ב-X הימים האחרונים בשדה ``jewish`` של ההיסטוריה."""
    if not history or not title:
        return False
    for offset in range(1, days_back + 1):
        key = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        day_data = history.get(key)
        if not day_data:
            continue
        if title in day_data.get("jewish", ""):
            return True
    return False


def build_upcoming_text(now: datetime, is_motzei: bool = False,
                       history: dict | None = None) -> str:
    today = now.date()

    # גבול "השבוע" – שבת הקרובה (Sun-Sat). במוצאי שבת/חג השבוע
    # החדש כבר התחיל, אז "השבוע" כולל את 7 הימים הבאים עד שבת הבאה.
    days_to_saturday = (5 - today.weekday()) % 7
    if is_motzei and days_to_saturday == 0:
        days_to_saturday = 7
    end_of_this_week = today + timedelta(days=days_to_saturday)

    DAY_NAMES = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]

    WANTED_EVENTS = {
        "Yom HaShoah":          ("יום השואה",        True),
        "Yom HaZikaron":        ("יום הזיכרון",      True),
        "Yom HaAtzma'ut":       ("יום העצמאות",      True),
        "Erev Pesach":          ("ערב פסח",          True),
        "Pesach I":             ("פסח",              True),
        "Pesach VII":           ("שביעי של פסח",     True),
        "Erev Shavuot":         ("ערב שבועות",       True),
        "Shavuot":              ("שבועות",            True),
        "Erev Rosh Hashana":    ("ערב ראש השנה",     True),
        "Rosh Hashana":         ("ראש השנה",         True),
        "Erev Yom Kippur":      ("ערב יום כיפור",    True),
        "Yom Kippur":           ("יום כיפור",        True),
        "Erev Sukkot":          ("ערב סוכות",        True),
        "Sukkot I":             ("סוכות",             True),
        "Shmini Atzeret":       ("שמיני עצרת",       True),
        "Chanukah: 1 Candle":   ("חנוכה",            True),
        "Purim":                ("פורים",             True),
        "Rosh Chodesh":         (None,               True),
    }

    events = []
    end_date = today + timedelta(days=7)

    months_to_check = {(today.year, today.month)}
    if end_date.month != today.month:
        months_to_check.add((end_date.year, end_date.month))

    for year, month in months_to_check:
        url = (
            f"https://www.hebcal.com/hebcal?v=1&cfg=json"
            f"&maj=on&mod=on&nx=on&mf=on"
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
                if cat not in {"holiday", "roshchodesh"}:
                    continue

                eng_title = item.get("title", "")
                heb_title = item.get("hebrew", eng_title)

                matched = None
                for pattern, (display, evening) in WANTED_EVENTS.items():
                    if eng_title.startswith(pattern):
                        matched = (display or heb_title, evening)
                        break

                if matched:
                    events.append({
                        "date":          item_date,
                        "days_away":     days_away,
                        "title":         matched[0],
                        "evening_start": matched[1],
                    })
        except Exception:
            pass

    events.sort(key=lambda x: x["days_away"])

    if not events:
        return ""

    seen = set()
    unique = []
    for ev in events:
        if ev["title"] not in seen:
            seen.add(ev["title"])
            unique.append(ev)
    events = unique[:4]

    # סינון לקצב סביר של הופעות:
    # d==1 (הערב) – תמיד מציגים, זו תזכורת אחרונה.
    # d>=2 – מציגים רק אם האירוע לא הוזכר ב-5 הימים האחרונים.
    HISTORY_WINDOW_DAYS = 5
    suppressed = []
    visible_events = []
    for ev in events:
        if ev["days_away"] == 1:
            visible_events.append(ev)
        elif _was_mentioned_recently(ev["title"], history, today, HISTORY_WINDOW_DAYS):
            suppressed.append(ev["title"])
        else:
            visible_events.append(ev)
    if suppressed:
        print(f"  ⏭️ אירועים שדוכאו (הוזכרו ב-{HISTORY_WINDOW_DAYS} ימים אחרונים): {', '.join(suppressed)}")
    events = visible_events

    this_week, next_week = [], []
    for ev in events:
        d = ev["days_away"]
        ev_day = DAY_NAMES[ev["date"].weekday()]
        text = f"הערב *{ev['title']}*" if d == 1 else f"*{ev['title']}* ביום {ev_day}"
        if ev["date"] <= end_of_this_week:
            this_week.append(text)
        else:
            next_week.append(text)

    sections = []
    if this_week:
        sections.append("השבוע: "    + ", ".join(this_week) + ".")
    if next_week:
        sections.append("שבוע הבא: " + ", ".join(next_week) + ".")
    return " ".join(sections)


def build_footer(payload: dict) -> str:
    now = payload["run_time"]
    is_motzei = payload.get("is_motzei", False)
    history   = payload.get("history") or {}
    lines = []

    upcoming = build_upcoming_text(now, is_motzei=is_motzei, history=history)
    if upcoming:
        lines.append(upcoming)

    kl = get_kiddush_levana_text()
    if kl:
        lines.append("")
        lines.append(kl)

    lines.append("")
    lines.append("שאו מרום עיניכם וראו מי ברא אלה 🌌")

    # ── קישור הצטרפות לקבוצה (תוספת קשיחה, תמיד בסוף ההודעה) ──
    lines.append("")
    lines.append("להצטרפות לקבוצת הווטסאפ שלנו - אסטרו-בוט (בטא):")
    lines.append("https://chat.whatsapp.com/JPkp1hyk4J938apVTFu6J1?s=cl&p=a&ilr=0")

    return "\n".join(lines)


def strip_closing_line(message: str) -> str:
    lines = message.rstrip().split("\n")
    while lines and ("שאו מרום" in lines[-1] or lines[-1].strip() == ""):
        lines.pop()
    return "\n".join(lines)


# ══════════════════════════════════════════
# 7. נקודת כניסה ראשית
# ══════════════════════════════════════════

def is_shabbat_or_yomtov_now(daytime_run: bool) -> bool:
    if not daytime_run:
        return False

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
                        return True
                except Exception:
                    pass
    except Exception:
        pass

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
                    return True
    except Exception:
        pass

    return False


def was_sent_today(history: dict) -> bool:
    today_key = datetime.now(ISRAEL_TZ).strftime("%Y-%m-%d")
    return today_key in history


def detect_motzei(now: datetime) -> bool:
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

    hour = now.hour
    history = load_history()

    if hour < 17:
        if is_shabbat_or_yomtov_now(daytime_run=True):
            print("✡️ עכשיו שבת/חג – לא שולח")
            sys.exit(0)
    else:
        if was_sent_today(history) and os.environ.get("FORCE_SEND", "false").lower() != "true":
            print("✅ כבר נשלחה הודעה היום – לא שולח שוב (הוסף force_send=true להרצה ידנית)")
            sys.exit(0)

        if is_shabbat_or_yomtov_now(daytime_run=False):
            print("✡️ עכשיו שבת/חג – לא שולח")
            sys.exit(0)

        print("🌙 ריצת לילה – שולח הודעה")

    is_motzei = (hour >= 17) and detect_motzei(now)
    if is_motzei:
        print("✡️ מוצאי שבת/חג – שולח בשבוע טוב")

    print("📚 טוען היסטוריית הודעות...")
    today_key    = now.strftime("%Y-%m-%d")
    history_text = format_history_for_prompt(history)

    print("📡 מושך נתוני עננות...")
    cloud_pct            = get_cloud_cover()
    if cloud_pct is None:
        cloud_status, cloud_desc = "unknown", None
    else:
        cloud_status, cloud_desc = cloud_label(cloud_pct)

    print("🔭 מחשב נתוני ירח וכוכבים (ל-19:30 ישראל)...")
    astro = get_astronomical_data()

    print("🛸 מחשב מעברי ISS...")
    iss = get_station_passes()

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

    date_str = now.strftime("%d/%m/%Y")

    recent_news = [
        v.get("space_news", "")
        for v in sorted(history.values(), key=lambda x: x.get("_message_length", 0))[-5:]
        if v.get("space_news")
    ]

    print("📡 מחפש חדשות חלל ואסטרונומיה...")
    jewish_context = "\n".join(j_events) if j_events else ""
    space_news = gather_space_news(date_str, jewish_context, recent_news)
    print("\n" + "─"*40)
    print("📡 חדשות שנאספו:")
    print(space_news)
    print("─"*40 + "\n")

    time.sleep(5)

    print("🤖 Claude מייצר הודעה בעברית...")
    payload = {
        "run_time":      now,
        "date_str":      date_str,
        "cloud_pct":     cloud_pct,
        "cloud_status":  cloud_status,
        "cloud_desc":    cloud_desc,
        "astro":         astro,
        "iss":           iss,
        "jewish_events": j_events,
        "jdate":         jdate,
        "history":       history,
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

    print("📱 שולח WhatsApp...")
    is_dry = os.environ.get("DRY_RUN", "false").lower() == "true"
    if is_dry:
        print("🔍 DRY_RUN=true – לא שולח ווטסאפ")
    else:
        send_whatsapp(message)

    summary = extract_summary_from_message(message, payload)
    if is_dry:
        # הרצה יבשה לא משנה מצב: לא שולח ולא כותב היסטוריה,
        # כדי שלא תסמן את היום כ"נשלח" ותחסום ריצה אמיתית.
        print(f"🔍 DRY_RUN – לא שומר היסטוריה (הסיכום שהיה נשמר: {summary})")
    else:
        print("📚 מסכם ושומר היסטוריה...")
        save_history(history, today_key, summary)
        print(f"✅ נשמר: {summary}")
    print("✅ הכל הושלם!")


if __name__ == "__main__":
    main()
