#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""מריץ את כל קבצי הבדיקה בתיקייה. קוד יציאה 1 אם אחד מהם נכשל."""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

def main() -> int:
    failed = []
    for path in sorted(HERE.glob("test_*.py")):
        result = subprocess.run([sys.executable, str(path)], cwd=HERE)
        if result.returncode != 0:
            failed.append(path.name)

    print("\n" + "═" * 72)
    if failed:
        print(f"❌ נכשלו: {', '.join(failed)}")
        return 1
    print("🎉 כל קבצי הבדיקה עברו")
    return 0

if __name__ == "__main__":
    sys.exit(main())
