"""
utils/cf_api.py — Async helpers for the Codeforces public REST API.

All network calls go through aiohttp and are surfaced as clean async
functions so cogs never have to handle raw HTTP logic.
"""

import random
import datetime
import aiohttp
from collections import defaultdict
from typing import Dict, List, Optional

from config.settings import RANK_ORDER


# ── User info ─────────────────────────────────────────────────────────────────

async def get_user_info(handle: str) -> dict:
    """Return the raw CF user.info result dict for *handle*.
    Raises ValueError on API error or unknown handle.
    """
    url = f"https://codeforces.com/api/user.info?handles={handle}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
    if data["status"] != "OK":
        raise ValueError(f"CF API error for handle '{handle}': {data.get('comment', 'unknown')}")
    return data["result"][0]


async def get_user_rating_and_rank(handle: str) -> tuple[str, int]:
    """Return (rank, rating) for *handle*."""
    user = await get_user_info(handle)
    rank   = user.get("rank", "newbie").lower()
    rating = user.get("rating", 800)
    return rank, rating


# ── Rating history ────────────────────────────────────────────────────────────

async def fetch_cf_rating_history(handle: str) -> list:
    """Return the full contest rating history list for *handle*."""
    url = f"https://codeforces.com/api/user.rating?handle={handle}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
    return data.get("result", [])


# ── Accepted submissions / heatmap data ───────────────────────────────────────

async def fetch_ac_submissions(handle: str) -> Optional[Dict[datetime.date, int]]:
    """Return a mapping of {date: solve_count} for all AC submissions.
    Returns None if the API call fails.
    """
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://codeforces.com/api/user.status?handle={handle}"
        ) as resp:
            data = await resp.json()

    if data["status"] != "OK":
        return None

    solved_dates: Dict[datetime.date, int] = defaultdict(int)
    for sub in data["result"]:
        if sub.get("verdict") == "OK":
            dt = datetime.datetime.fromtimestamp(
                sub["creationTimeSeconds"], datetime.UTC
            ).date()
            solved_dates[dt] += 1

    return dict(solved_dates)


# ── Problems ──────────────────────────────────────────────────────────────────

async def fetch_problems_from_cf(
    tag_filter: Optional[List[str]] = None,
    min_rating: int = 800,
    max_rating: int = 1600,
    count: int = 5,
) -> List[dict]:
    """Return up to *count* random problems within the rating range.
    Optionally filters by *tag_filter* (any match).
    """
    async with aiohttp.ClientSession() as session:
        async with session.get("https://codeforces.com/api/problemset.problems") as resp:
            data = await resp.json()

    all_problems = data["result"]["problems"]
    filtered = [
        p for p in all_problems
        if "rating" in p
        and min_rating <= p["rating"] <= max_rating
        and (not tag_filter or any(tag in p.get("tags", []) for tag in tag_filter))
        and "contestId" in p
        and "index" in p
    ]
    return random.sample(filtered, min(count, len(filtered)))


async def get_random_problem(session: aiohttp.ClientSession, rating: int) -> Optional[dict]:
    """Return a single random CF problem at the exact *rating*."""
    async with session.get("https://codeforces.com/api/problemset.problems") as resp:
        data = await resp.json()
    if data["status"] != "OK":
        return None
    problems = [
        p for p in data["result"]["problems"]
        if p.get("rating") == rating and "contestId" in p and "index" in p
    ]
    return random.choice(problems) if problems else None


async def get_unsolved_problem(
    min_rating: int,
    max_rating: int,
    handle1: str,
    handle2: str,
) -> Optional[dict]:
    """Return a random unsolved (by both players) problem in the rating band."""
    async with aiohttp.ClientSession() as session:
        async with session.get("https://codeforces.com/api/problemset.problems") as resp:
            data = await resp.json()
        if data["status"] != "OK":
            raise RuntimeError("Failed to fetch CF problem set")

        problems = data["result"]["problems"]

        async def _solved_set(handle: str) -> set:
            async with session.get(
                f"https://codeforces.com/api/user.status?handle={handle}"
            ) as r:
                subs = await r.json()
            return {
                f"{s['problem']['contestId']}-{s['problem']['index']}"
                for s in subs.get("result", [])
                if s.get("verdict") == "OK"
            }

        combined_solved = (await _solved_set(handle1)) | (await _solved_set(handle2))

    unsolved = [
        p for p in problems
        if "rating" in p
        and "contestId" in p
        and "index" in p
        and min_rating <= p["rating"] <= max_rating
        and f"{p['contestId']}-{p['index']}" not in combined_solved
    ]
    return random.choice(unsolved) if unsolved else None


# ── Rank helpers ──────────────────────────────────────────────────────────────

def is_rank_up(new_rank: str, old_rank: str) -> bool:
    """Return True if *new_rank* is higher than *old_rank* in CF hierarchy."""
    try:
        return RANK_ORDER.index(new_rank.lower()) > RANK_ORDER.index(old_rank.lower())
    except ValueError:
        return False


def get_rank_emoji(rank: str) -> str:
    return {
        "newbie":                  "⚪",
        "pupil":                   "🟢",
        "specialist":              "🔵",
        "expert":                  "🟣",
        "candidate master":        "🟠",
        "master":                  "🔴",
        "international master":    "🔴",
        "grandmaster":             "🏅",
        "international grandmaster": "🥇",
        "legendary grandmaster":   "🔥",
    }.get(rank.lower(), "🎖️")
