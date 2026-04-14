#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_fix.py – תיקונים אוטומטיים דטרמיניסטיים
=============================================
רץ על הפלט של generate_message() לפני proofread_hebrew().
ללא AI, ללא API – Python טהור בלבד.

סוגי תיקונים:
  1. אותיות שירות לפני בולד (ו/ה/ב/כ/ל/מ/ש לפני *)
  2. תחליפי מילים קבועים
  3. המרת מיילים לקילומטרים (עם חישוב)
"""

import re


# ══════════════════════════════════════════
# 1. אותיות שירות לפני כוכבית פותחת
# ══════════════════════════════════════════

def fix_prefix_before_bold(text: str) -> str:
    """
    ממיר ו*מילה* → *ומילה*, ה*מילה* → *המילה*, וכו'.
    תומך בכל אותיות השירות: ו ה ב כ ל מ ש
    """
    # תבנית: אות שירות + * + תוכן + *
    # למשל: ו*נוגה* → *ונוגה*
    prefix_letters = "והבכלמש"
    pattern = rf'([{prefix_letters}])(\*[^*\n]+\*)'

    def replacer(m):
        letter  = m.group(1)
        bold    = m.group(2)          # *תוכן*
        # הכנס את האות לפנים: *ו + תוכן*
        inner = bold[1:-1]            # תוכן ללא כוכביות
        return f"*{letter}{inner}*"

    return pattern and re.sub(pattern, replacer, text) or text


# ══════════════════════════════════════════
# 2. תחליפי מילים קבועים
# ══════════════════════════════════════════

WORD_REPLACEMENTS = [
    # אסטרונומיה
    (r'מקלחת מטאורים', 'מטר מטאורים'),
    (r'דו-עינית',       'משקפת'),
    (r'בראייה ערומה',   'בעין בלתי מזוינת'),
    (r'בעין רגילה',     'בעין בלתי מזוינת'),
    (r'קרייטר',         'מכתש'),
    (r'קרטר',           'מכתש'),
    (r'קרטרים',         'מכתשים'),
    (r'קרייטרים',       'מכתשים'),
    (r'אסטרואיד',       'אסטרואיד'),   # שמור – נכון בעברית
    # שמות עצם בעברית
    (r'בלאק הול',       'חור שחור'),
    (r'ווייט דוורף',    'ננס לבן'),
    (r'רד דוורף',       'ננס אדום'),
    (r'סופרנובה',       'סופרנובה'),   # שמור – מקובל
]


def fix_word_replacements(text: str) -> str:
    for pattern, replacement in WORD_REPLACEMENTS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


# ══════════════════════════════════════════
# 3. המרת מיילים לקילומטרים
# ══════════════════════════════════════════

def fix_miles_to_km(text: str) -> str:
    """
    ממיר "253,000 מיילים" → "407,000 ק״מ"
    ו-"1,000 miles" → "1,609 ק״מ"
    """
    def convert(m):
        num_str = m.group(1).replace(",", "").replace(".", "")
        try:
            num_km = round(int(num_str) * 1.609)
            # פורמט עם פסיק אלפים
            formatted = f"{num_km:,}".replace(",", ",")
            return f"{formatted} ק״מ"
        except Exception:
            return m.group(0)  # לא הצלחנו – השאר כמו שהוא

    # מיילים בעברית
    text = re.sub(r'([\d,]+)\s*מיילים', convert, text)
    # miles באנגלית
    text = re.sub(r'([\d,]+)\s*miles', convert, text, flags=re.IGNORECASE)
    # mph → קמ"ש (מהירות)
    text = re.sub(r'([\d,]+)\s*mph', lambda m: f"{round(int(m.group(1).replace(',','')) * 1.609):,} קמ\"ש", text)

    return text


# ══════════════════════════════════════════
# ראשי – הרץ את כל התיקונים
# ══════════════════════════════════════════

def auto_fix(text: str) -> str:
    """מריץ את כל התיקונים האוטומטיים ברצף."""
    original = text

    text = fix_prefix_before_bold(text)
    text = fix_word_replacements(text)
    text = fix_miles_to_km(text)

    # דווח על שינויים
    if text != original:
        changes = []
        if fix_prefix_before_bold(original) != original:
            changes.append("כוכביות")
        if fix_word_replacements(original) != original:
            changes.append("מילים")
        if fix_miles_to_km(original) != original:
            changes.append("מיילים→ק״מ")
        print(f"🔧 auto_fix: {', '.join(changes) or 'שינויים'}")

    return text


if __name__ == "__main__":
    # בדיקה
    tests = [
        ('ו*נוגה* נמוכה', '*ונוגה* נמוכה'),
        ('ה*ירח* גדול', '*הירח* גדול'),
        ('קרייטר ענק', 'מכתש ענק'),
        ('253,000 מיילים', '407,077 ק״מ'),
        ('דו-עינית טובה', 'משקפת טובה'),
    ]
    all_pass = True
    for input_text, expected in tests:
        result = auto_fix(input_text)
        status = "✅" if result == expected else "❌"
        if result != expected:
            all_pass = False
        print(f"{status} '{input_text}' → '{result}' (expected: '{expected}')")
    print("\n✅ כל הבדיקות עברו!" if all_pass else "\n❌ יש כשלונות")
