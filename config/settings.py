"""
config/settings.py — Centralised environment & bot-wide constants.
"""

import os
from typing import Dict, List, Tuple
import pytz
from dotenv import load_dotenv

load_dotenv()

TOKEN: str    = os.getenv("TOKEN", "")
MONGO_URI: str = os.getenv("MONGO_URI", "")

TZ_IST = pytz.timezone("Asia/Kolkata")

# BUG FIX: Use Dict/List/Tuple from typing instead of dict[]/list[] (works on Python 3.8+)
ROLE_COLORS: Dict[str, int] = {
    "newbie":                    0xCCCCCC,
    "pupil":                     0x77FF77,
    "specialist":                0x77DDBB,
    "expert":                    0xAAAAFF,
    "candidate master":          0xFF88FF,
    "master":                    0xFFCC88,
    "international master":      0xFFBB55,
    "grandmaster":               0xFF7777,
    "international grandmaster": 0xFF3333,
    "legendary grandmaster":     0xAA0000,
}

RANK_ORDER: List[str] = [
    "newbie", "pupil", "specialist", "expert",
    "candidate master", "master", "international master",
    "grandmaster", "international grandmaster", "legendary grandmaster",
]

RATING_BANDS: List[Tuple] = [
    (0,    1199, "#CCCCCC", "Newbie"),
    (1200, 1399, "#77FF77", "Pupil"),
    (1400, 1599, "#77DDBB", "Specialist"),
    (1600, 1899, "#AAAAFF", "Expert"),
    (1900, 2099, "#FF88FF", "CM"),
    (2100, 2299, "#FFCC88", "Master"),
    (2300, 2399, "#FFBB55", "IM"),
    (2400, 2599, "#FF7777", "GM"),
    (2600, 2899, "#FF3333", "IGM"),
    (2900, 4000, "#AA0000", "LGM"),
]

DUEL_WIN_POINTS: int          = 2
DUEL_LOSE_POINTS: int         = -1
DUEL_TIMEOUT_MINUTES: int     = 15
DUEL_POLL_INTERVAL_SECONDS: int = 10
