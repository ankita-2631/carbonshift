"""Path-independent launcher for the CarbonShift web dashboard.

Run from anywhere:
    python C:\\Hack\\carbonshift\\run_web.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from carbonshift.web import main

if __name__ == "__main__":
    main()
