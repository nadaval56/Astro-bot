#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_negative_magnitude: "1.7-" → "‎-1.7", בלי לגעת בטווחים ובכינויים."""
from helpers import Results
from auto_fix import fix_negative_magnitude as f, LRM

r = Results("סימן מינוס בבהירות שלילית")
r.check("מינוס בסוף, בסוגריים", f("צדק הבהיר (1.7-) יעלה"), f"({LRM}-1.7)")
r.check("מינוס בסוף, לפני רווח", f("בבהירות 1.7- – הגוף"), f"בבהירות {LRM}-1.7 –")
r.check("מינוס תקין מקבל LRM", f("בבהירות -4.4 שוקעת"), f"{LRM}-4.4")
r.check("LRM קיים לא מוכפל", f(f"בבהירות {LRM}-4.4"), f"בבהירות {LRM}-4.4")
for t in ("בין 8-9 באוקטובר", "5–10 מטאורים", "STS-41-G", "MoM-z14",
          "בהירות 0.3)", "ב-21 באוקטובר"):
    r.check(f"ללא שינוי: {t}", repr(f(t)), repr(t))
r.done()
