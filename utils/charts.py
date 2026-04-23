"""
utils/charts.py — Matplotlib / Seaborn chart generators.

Every function returns a BytesIO PNG buffer ready to attach to a
Discord message. No Discord-specific logic lives here — pure data → image.
"""

import datetime
from io import BytesIO
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from config.settings import RATING_BANDS


# ── CF rating history graph ───────────────────────────────────────────────────

def generate_cf_stats_graph(history: list, handle: str) -> BytesIO:
    """Render a rating-history graph with coloured rank bands.

    Args:
        history: List of CF rating-change dicts (from user.rating API).
        handle:  CF handle used as the graph title.

    Returns:
        PNG image as a BytesIO buffer.
    """
    dates   = [datetime.datetime.fromtimestamp(e["ratingUpdateTimeSeconds"]) for e in history]
    ratings = [e["newRating"] for e in history]

    max_rating = max(ratings)
    y_limit    = max(2000, max_rating + 200)

    plt.figure(figsize=(10, 5))
    plt.plot(dates, ratings, marker="o", linestyle="-", color="black", label="Rating")

    for low, high, color, _ in RATING_BANDS:
        if low < y_limit:
            plt.axhspan(low, min(high, y_limit), facecolor=color, alpha=0.2)

    # Annotate peak
    max_idx = ratings.index(max_rating)
    plt.annotate(
        f"Max: {max_rating}",
        xy=(dates[max_idx], max_rating),
        xytext=(dates[max_idx], max_rating + 50),
        arrowprops=dict(arrowstyle="->", color="red"),
    )

    plt.xlabel("Date")
    plt.ylabel("Rating")
    plt.title(f"{handle}'s Codeforces Rating History")
    plt.xticks(rotation=45)
    plt.grid(True)
    plt.ylim(0, y_limit)
    plt.tight_layout()

    return _save_and_close()


# ── Multi-user comparison graph ───────────────────────────────────────────────

def generate_comparison_graph(
    histories: List[Tuple[str, list]],
    title: str,
) -> BytesIO:
    """Overlay multiple users' rating histories on one graph.

    Args:
        histories: List of (handle, rating_history) tuples.
        title:     Plot title.

    Returns:
        PNG image as a BytesIO buffer.
    """
    colors = ["blue", "green", "red", "purple", "orange"]
    plt.figure(figsize=(12, 6))

    for i, (handle, history) in enumerate(histories):
        dates   = [datetime.datetime.fromtimestamp(e["ratingUpdateTimeSeconds"]) for e in history]
        ratings = [e["newRating"] for e in history]
        plt.plot(dates, ratings, marker="o", linestyle="-",
                 color=colors[i % len(colors)], label=handle)

    plt.title(title)
    plt.xlabel("Date")
    plt.ylabel("Rating")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    return _save_and_close()


# ── Duel history line graph ───────────────────────────────────────────────────

def generate_duel_history_graph(history: list, username: str) -> BytesIO | None:
    """Render a cumulative duel-points-over-time graph.

    Args:
        history:  List of duel history dicts (keys: timestamp, duel_points).
        username: CF handle for the title.

    Returns:
        PNG BytesIO buffer, or None if history is empty.
    """
    if not history:
        return None

    dates  = [datetime.datetime.fromtimestamp(e["timestamp"]) for e in history]
    points: list[int] = []
    total = 0
    for entry in history:
        total += entry["duel_points"]
        points.append(total)

    plt.style.use("dark_background")
    plt.figure(figsize=(8, 4))
    plt.plot(dates, points, marker="o", linestyle="-", color="lime", label="Duel Points")
    plt.axhline(0, color="red", linestyle="--", linewidth=1)

    plt.title(f"{username}'s Duel History")
    plt.xlabel("Date")
    plt.ylabel("Points")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.legend()

    buf = _save_and_close(dpi=150)
    plt.style.use("default")   # reset style for subsequent charts
    return buf


# ── Activity heatmap ──────────────────────────────────────────────────────────

def generate_cf_heatmap(
    solved_dates: Dict[datetime.date, int],
    handle: str,
) -> BytesIO:
    """Render a GitHub-style activity heatmap for the past 365 days.

    Args:
        solved_dates: {date: solve_count} mapping.
        handle:       CF handle for the title.

    Returns:
        PNG BytesIO buffer.
    """
    today      = datetime.date.today()
    start_date = today - datetime.timedelta(days=364)

    full_dates = pd.date_range(start=start_date, end=today)
    df = pd.DataFrame({"date": full_dates})
    df["count"] = df["date"].dt.date.map(solved_dates).fillna(0).astype(int)
    df["dow"]   = df["date"].dt.dayofweek
    df["week"]  = (
        (df["date"] - pd.to_datetime(start_date)).dt.days + start_date.weekday()
    ) // 7

    heatmap_data = df.pivot(index="dow", columns="week", values="count")
    heatmap_data.index = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    fig, ax = plt.subplots(figsize=(18, 3))
    sns.heatmap(
        heatmap_data,
        cmap=sns.light_palette("red", as_cmap=True),
        linewidths=0.5,
        linecolor="white",
        cbar_kws={"label": "Solved Count"},
        square=False,
        ax=ax,
    )
    ax.set_title(f"{handle}'s Heatmap ({start_date.year}–{today.year})", fontsize=14)
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.tick_params(left=True, bottom=False)
    plt.tight_layout()

    return _save_and_close()


# ── Internal helper ───────────────────────────────────────────────────────────

def _save_and_close(dpi: int = 100) -> BytesIO:
    """Save the current figure to a BytesIO buffer, close it, and return it."""
    buf = BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", dpi=dpi)
    buf.seek(0)
    plt.close()
    return buf
