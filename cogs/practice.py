"""
cogs/practice.py — Tag-based CF practice problem sets.

Commands
--------
/practice   Get 5 problems filtered by tag and optional rating range
/tags       List all available CF problem tags
"""

import random
from typing import Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands


# Common CF tags for the /tags command
COMMON_TAGS = [
    "dp", "graphs", "greedy", "math", "implementation",
    "binary search", "data structures", "brute force", "strings",
    "trees", "number theory", "geometry", "bitmasks", "two pointers",
    "sorting", "dfs and similar", "constructive algorithms",
    "divide and conquer", "shortest paths", "flows",
]


async def _fetch_by_tag(tag: str, min_r: int, max_r: int, count: int = 5) -> list:
    """Fetch random problems matching tag and rating range."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://codeforces.com/api/problemset.problems?tags={tag}",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()

        if data["status"] != "OK":
            return []

        problems = [
            p for p in data["result"]["problems"]
            if "rating" in p
            and min_r <= p["rating"] <= max_r
            and "contestId" in p
        ]
        return random.sample(problems, min(count, len(problems)))
    except Exception as e:
        print(f"[Practice] Error fetching tag {tag}: {e}")
        return []


class PracticeCog(commands.Cog, name="Practice"):
    """Tag-filtered CF practice problem sets."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── /practice ─────────────────────────────────────────────────────────────

    @app_commands.command(
        name="practice",
        description="Get 5 CF problems by tag (e.g. dp, graphs, greedy)",
    )
    @app_commands.describe(
        tag="Problem tag (e.g. dp, graphs, greedy, binary search)",
        min_rating="Minimum rating (default 800)",
        max_rating="Maximum rating (default 2000)",
        count="Number of problems (1-10, default 5)",
    )
    async def practice(
        self,
        interaction: discord.Interaction,
        tag: str,
        min_rating: int = 800,
        max_rating: int = 2000,
        count: int = 5,
    ) -> None:
        await interaction.response.defer()

        count = max(1, min(count, 10))
        tag   = tag.lower().strip()

        problems = await _fetch_by_tag(tag, min_rating, max_rating, count)

        if not problems:
            return await interaction.followup.send(
                f"❌ No problems found for tag `{tag}` in rating range `{min_rating}–{max_rating}`.\n"
                f"Try `/tags` to see valid tag names."
            )

        embed = discord.Embed(
            title=f"📚 Practice Set — {tag.title()}",
            description=f"Rating range: `{min_rating}–{max_rating}`",
            color=discord.Color.blurple(),
        )

        for i, p in enumerate(problems, 1):
            url = (
                f"https://codeforces.com/problemset/problem/"
                f"{p['contestId']}/{p['index']}"
            )
            tag_str = ", ".join(p.get("tags", [])[:4])
            embed.add_field(
                name=f"{i}. {p['name']} — `{p['rating']}`",
                value=f"[Solve]({url}) | Tags: `{tag_str}`",
                inline=False,
            )

        embed.set_footer(text=f"Showing {len(problems)} problems. Use /practice {tag} to get a new set.")
        await interaction.followup.send(embed=embed)

    # ── /tags ─────────────────────────────────────────────────────────────────

    @app_commands.command(
        name="tags",
        description="List commonly used CF problem tags for /practice",
    )
    async def tags(self, interaction: discord.Interaction) -> None:
        formatted = "\n".join(f"• `{t}`" for t in sorted(COMMON_TAGS))
        embed = discord.Embed(
            title="🏷️ Available Tags for /practice",
            description=formatted,
            color=discord.Color.teal(),
        )
        embed.set_footer(text="Usage: /practice dp 1200 1600")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PracticeCog(bot))
