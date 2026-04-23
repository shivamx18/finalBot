"""
cogs/teamduel.py — 2v2 team Codeforces duels.

Two teams of 2 compete to solve the same problem first.
The first team where ANY member solves it wins.

Commands
--------
/teamduel   Start a 2v2 duel: /teamduel @u1 @u2 vs @u3 @u4 800 1200
"""

import asyncio
import datetime
from typing import Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from config.database import users_collection, guilds_collection
from config.settings import DUEL_WIN_POINTS, DUEL_LOSE_POINTS, DUEL_TIMEOUT_MINUTES
from utils.cf_api import get_unsolved_problem


async def _wait_for_team_ac(
    team1: list[str],
    team2: list[str],
    problem: dict,
    timeout_minutes: int = DUEL_TIMEOUT_MINUTES,
) -> Optional[int]:
    """
    Poll CF API until someone from team1 or team2 solves the problem.
    Returns 1 if team1 wins, 2 if team2 wins, None on timeout.
    """
    end_time   = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=timeout_minutes)
    contest_id = problem["contestId"]
    index      = problem["index"]

    while datetime.datetime.now(datetime.UTC) < end_time:
        for team_num, handles in [(1, team1), (2, team2)]:
            for handle in handles:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            f"https://codeforces.com/api/user.status?handle={handle}",
                            timeout=aiohttp.ClientTimeout(total=10),
                        ) as resp:
                            data = await resp.json()
                    for sub in data.get("result", []):
                        if (
                            sub.get("verdict") == "OK"
                            and sub["problem"]["contestId"] == contest_id
                            and sub["problem"]["index"] == index
                        ):
                            return team_num
                except Exception:
                    pass
        await asyncio.sleep(10)

    return None


class TeamDuelCog(commands.Cog, name="TeamDuel"):
    """2v2 Codeforces team duels."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="teamduel",
        description="2v2 CF duel: /teamduel @p1 @p2 @p3 @p4 min_rating max_rating",
    )
    @app_commands.describe(
        player1="Team 1 — Player 1",
        player2="Team 1 — Player 2",
        player3="Team 2 — Player 1",
        player4="Team 2 — Player 2",
        min_rating="Minimum problem rating",
        max_rating="Maximum problem rating",
    )
    async def team_duel(
        self,
        interaction: discord.Interaction,
        player1: discord.User,
        player2: discord.User,
        player3: discord.User,
        player4: discord.User,
        min_rating: int = 1000,
        max_rating: int = 1600,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        # Check duel category
        guild_config = guilds_collection.find_one({"guild_id": interaction.guild_id})
        duel_cat_id  = guild_config.get("duel_category_id") if guild_config else None
        if not duel_cat_id:
            return await interaction.followup.send(
                "❌ Duel category not configured. Admin must run `/setduelchannel`.",
                ephemeral=True,
            )
        if interaction.channel.category_id != duel_cat_id:
            cat = discord.utils.get(interaction.guild.categories, id=duel_cat_id)
            return await interaction.followup.send(
                f"❌ Use this in the **{cat.name if cat else 'duel'}** category.",
                ephemeral=True,
            )

        # Verify all players
        all_players = [player1, player2, player3, player4]
        if len(set(p.id for p in all_players)) < 4:
            return await interaction.followup.send(
                "❌ All 4 players must be different users.", ephemeral=True
            )

        handles = {}
        for p in all_players:
            doc = users_collection.find_one({"discord_id": str(p.id)})
            if not doc:
                return await interaction.followup.send(
                    f"❌ {p.mention} is not verified. All players must use `/verify` first.",
                    ephemeral=True,
                )
            handles[p.id] = doc["cfid"]

        team1_handles = [handles[player1.id], handles[player2.id]]
        team2_handles = [handles[player3.id], handles[player4.id]]
        all_handles   = team1_handles + team2_handles

        # Create duel channel
        category = discord.utils.get(interaction.guild.categories, id=duel_cat_id)
        try:
            duel_channel = await category.create_text_channel(
                name=f"team-duel-{player1.name[:8]}-vs-{player3.name[:8]}",
                overwrites={
                    interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    **{p: discord.PermissionOverwrite(read_messages=True, send_messages=True)
                       for p in all_players},
                    interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                },
            )
        except discord.HTTPException as e:
            return await interaction.followup.send(f"❌ Could not create channel: {e}", ephemeral=True)

        t1_mentions = f"{player1.mention} & {player2.mention}"
        t2_mentions = f"{player3.mention} & {player4.mention}"

        class TeamDuelView(discord.ui.View):
            def __init__(view_self):
                super().__init__(timeout=120)

            @discord.ui.button(label="✅ All Ready", style=discord.ButtonStyle.success)
            async def start(view_self, i2: discord.Interaction, _):
                if i2.user.id not in [p.id for p in all_players]:
                    return await i2.response.send_message("❌ Only duel participants can click this.", ephemeral=True)

                await i2.response.defer()
                for item in view_self.children:
                    item.disabled = True
                try:
                    await i2.message.edit(view=view_self)
                except Exception:
                    pass

                # Get a problem nobody has solved
                try:
                    problem = await get_unsolved_problem(
                        min_rating, max_rating, all_handles[0], all_handles[1]
                    )
                except Exception as e:
                    await duel_channel.send(f"❌ Error fetching problem: {e}")
                    return await asyncio.sleep(10) or await duel_channel.delete()

                if not problem:
                    await duel_channel.send("❌ No unsolved problem found in that range.")
                    return await asyncio.sleep(10) or await duel_channel.delete()

                url = f"https://codeforces.com/problemset/problem/{problem['contestId']}/{problem['index']}"
                await duel_channel.send(
                    f"⚔️ **Team Duel Started!**\n"
                    f"🔵 Team 1: {t1_mentions}\n"
                    f"🔴 Team 2: {t2_mentions}\n\n"
                    f"🎯 **Problem**: [{problem['name']}]({url})\n"
                    f"⭐ Rating: `{problem['rating']}`\n\n"
                    f"First team to solve it wins! Press **Done** when solved."
                )

                class DoneView(discord.ui.View):
                    def __init__(v2):
                        super().__init__(timeout=None)

                    @discord.ui.button(label="✅ Done", style=discord.ButtonStyle.primary)
                    async def done(v2, i3: discord.Interaction, _):
                        await i3.response.defer(ephemeral=True)
                        winner_team = await _wait_for_team_ac(
                            team1_handles, team2_handles, problem
                        )

                        if not winner_team:
                            return await i3.followup.send("⏳ No solve detected yet!", ephemeral=True)

                        if winner_team == 1:
                            w_str, l_str = t1_mentions, t2_mentions
                            w_handles, l_handles = team1_handles, team2_handles
                        else:
                            w_str, l_str = t2_mentions, t1_mentions
                            w_handles, l_handles = team2_handles, team1_handles

                        # Record points
                        for h in w_handles:
                            users_collection.update_one(
                                {"cfid": h, "guild_id": interaction.guild_id},
                                {"$inc": {"duel_points": DUEL_WIN_POINTS}},
                                upsert=True,
                            )
                        for h in l_handles:
                            users_collection.update_one(
                                {"cfid": h, "guild_id": interaction.guild_id},
                                {"$inc": {"duel_points": DUEL_LOSE_POINTS}},
                                upsert=True,
                            )

                        await duel_channel.send(
                            f"🏁 **Team Duel Over!**\n"
                            f"🏆 Winners: {w_str} (+{DUEL_WIN_POINTS} pts each)\n"
                            f"❌ Losers: {l_str} ({DUEL_LOSE_POINTS} pts each)"
                        )
                        await asyncio.sleep(20)
                        try:
                            await duel_channel.delete()
                        except Exception:
                            pass

                await duel_channel.send("👇 Click when your team has solved it:", view=DoneView())

            @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.danger)
            async def cancel(view_self, i2: discord.Interaction, _):
                await i2.response.defer()
                await duel_channel.send("❌ Team duel cancelled.")
                await asyncio.sleep(3)
                try:
                    await duel_channel.delete()
                except Exception:
                    pass

        await duel_channel.send(
            f"⚔️ **Team Duel Challenge!**\n"
            f"🔵 **Team 1**: {t1_mentions}\n"
            f"🔴 **Team 2**: {t2_mentions}\n"
            f"📊 Rating Range: `{min_rating}–{max_rating}`\n\n"
            f"All 4 players click **All Ready** when set!",
            view=TeamDuelView(),
        )
        await interaction.followup.send(
            f"⚔️ Team duel channel created! Check <#{duel_channel.id}>", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TeamDuelCog(bot))
