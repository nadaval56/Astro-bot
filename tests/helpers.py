# -*- coding: utf-8 -*-
"""עזרי בדיקה משותפים: טעינת המודול בלי סודות, וזיוף השעון."""
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# shamay_halayla קורא משתני סביבה חובה בזמן ה-import.
for _k in ("ANTHROPIC_API_KEY", "GREEN_API_INSTANCE",
           "GREEN_API_TOKEN", "WHATSAPP_GROUP_ID"):
    os.environ.setdefault(_k, "test")

import shamay_halayla as S   # noqa: E402

TZ = S.ISRAEL_TZ


class FrozenDatetime(datetime):
    """datetime עם now() קפוא – מוזרק אל תוך המודול הנבדק."""
    _now = None

    @classmethod
    def now(cls, tz=None):
        return cls._now


def freeze(ts: str) -> None:
    """מקפיא את שעון המודול על "YYYY-MM-DD HH:MM" בשעון ישראל."""
    S.datetime = FrozenDatetime
    FrozenDatetime._now = TZ.localize(
        datetime.strptime(ts, "%Y-%m-%d %H:%M")
    )


def at(ts: str):
    return TZ.localize(datetime.strptime(ts, "%Y-%m-%d %H:%M"))


class Results:
    """אוסף תוצאות ומדפיס סיכום; קוד יציאה 1 אם משהו נכשל."""

    def __init__(self, title: str):
        self.title = title
        self.failures = []
        self.passed = 0
        print(f"\n{'═' * 72}\n{title}\n{'═' * 72}")

    def check(self, desc: str, got: str, want: str) -> None:
        """`want` נחשב עובר אם הוא תת-מחרוזת של `got`."""
        ok = want in got
        if ok:
            self.passed += 1
        else:
            self.failures.append((desc, got, want))
        print(f"  {'✅' if ok else '❌'} {desc}")
        if not ok:
            print(f"       ציפיתי להכיל: {want}")
            print(f"       התקבל:         {got}")

    def done(self) -> None:
        if self.failures:
            print(f"\n❌ {len(self.failures)} מתוך "
                  f"{len(self.failures) + self.passed} נכשלו")
            sys.exit(1)
        print(f"\n🎉 כל {self.passed} הבדיקות עברו")
