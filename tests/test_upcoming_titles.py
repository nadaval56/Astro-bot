#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
בדיקות להתאמת כותרות hebcal ב-build_upcoming_text.

הרקע: בחול המועד סוכות נשלח כל יום "השבוע: הערב סוכות", כי
"Sukkot II (CH''M)" ודומיו התאימו לקידומת "Sukkot I". אותה בעיה בפסח.
"""
from helpers import S, Results


def main() -> None:
    r = Results("🗓️ אירועים קרובים – התאמת כותרות")
    m = S._title_matches

    cases = [
        ("Sukkot I",                  "Sukkot I",       True),
        ("Sukkot II (CH''M)",         "Sukkot I",       False),
        ("Sukkot III (CH''M)",        "Sukkot I",       False),
        ("Sukkot IV (CH''M)",         "Sukkot I",       False),
        ("Pesach I",                  "Pesach I",       True),
        ("Pesach II (CH''M)",         "Pesach I",       False),
        ("Pesach III (CH''M)",        "Pesach I",       False),
        ("Pesach VII",                "Pesach VII",     True),
        ("Pesach VIII",               "Pesach VII",     False),
        ("Rosh Hashana 5787",         "Rosh Hashana",   True),
        ("Rosh Hashana II",           "Rosh Hashana",   False),
        ("Rosh Chodesh Cheshvan",     "Rosh Chodesh",   True),
        ("Chanukah: 1 Candle",        "Chanukah: 1 Candle", True),
        ("Chanukah: 2 Candles",       "Chanukah: 1 Candle", False),
        ("Erev Sukkot",               "Erev Sukkot",    True),
        ("Shmini Atzeret",            "Shmini Atzeret", True),
    ]
    for title, pattern, want in cases:
        got = m(title, pattern)
        r.check(f"{title!r} ~ {pattern!r}", str(got), str(want))

    r.done()


if __name__ == "__main__":
    main()
