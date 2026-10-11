#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""לילה מעונן אינו "מצוין לתצפית": האזהרה מגיעה לכותב ולבקרה הלוגית רק מעל הסף."""
from helpers import S, Results

r = Results("לילה מעונן – בלי 'מושלם לתצפית'")

captured = []
S.ask_claude = lambda content, **kw: captured.append(content) or "x" * 1000


def qc_prompt(cloud):
    captured.clear()
    S.quality_check("הודעה", {"astro": {"sunset": "18:00"}, "cloud_pct": cloud})
    return captured[0]


r.check("עננות 90% → בקרה לוגית מקבלת משימת עננות", qc_prompt(90), "העננות הלילה 90%")
r.check("עננות 55% (הסף) → משימת עננות", qc_prompt(S.CLOUD_HOPEFUL), "מחק את שבח התצפית")
r.check("עננות 30% → בלי משימת עננות", str("העננות הלילה" in qc_prompt(30)), "False")
r.check("בלי נתון עננות → בלי משימת עננות", str("העננות הלילה" in qc_prompt(None)), "False")
r.done()
