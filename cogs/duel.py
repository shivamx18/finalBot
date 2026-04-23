"""
cogs/duel.py — Codeforces 1v1 duel system.
"""

import asyncio
import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config.database import users_collection, guilds_collection
from config.settings import (
    DUEL_WIN_POINTS,
    DUEL_LOSE_POINTS,
    DUEL_TIMEOUT_MINUTES,
    DUEL_POLL_INTERVAL_SECONDS,
)
from utils.cf_api import get_unsolved_problem
from utils.charts import generate_duel_history_graph


def record_duel_result(winner_cfid: str, loser_cfid: str, guild_id: int) -> None:
    timestamp = int(datetime.datetime.now(datetime.UTC).timestamp())
    for cfid, delta in [(winner_cfid, DUEL_WIN_POINTS), (loser_cfid, DUEL_LOSE_POINTS)]:
        users_collection.update_one(
            {"cfid": cfid, "guild_id": guild_id},
            {
                "$inc": {"duel_points": delta},
                "$push": {"duel_history": {"timestamp": timestamp, "duel_points": delta}},
            },
            upsert=True,
        )


async def wait_for_ac(
    handle1: str,
    handle2: str,
    problem: dict,
    timeout_minutes: int = DUEL_TIMEOUT_MINUTES,
) -> Optional[str]:
    import aiohttp
    end_time   = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=timeout_minutes)
    contest_id = problem["contestId"]
    index      = problem["index"]

    while datetime.datetime.now(datetime.UTC) < end_time:
        for handle in (handle1, handle2):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        f"https://codeforces.com/api/user.status?handle={handle}"
                    ) as resp:
                        data = await resp.json()
                for sub in data.get("result", []):
                    if (
                        sub.get("verdict") == "OK"
                        and sub["problem"]["contestId"] == contest_id
                        and sub["problem"]["index"] == index
                    ):
                        return handle
            except Exception:
                pass
        await asyncio.sleep(DUEL_POLL_INTERVAL_SECONDS)
    return None


class DuelCog(commands.Cog, name="Duel"):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="duel", description="Challenge someone to a Codeforces duel")
    @app_commands.describe(
        user="Your opponent",
        min_rating="Minimum problem rating",
        max_rating="Maximum problem rating",
    )
    async def duel(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        min_rating: int,
        max_rating: int,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        if interaction.user.id == user.id:
            return await interaction.followup.send("❌ You cannot duel yourself.", ephemeral=True)

        guild_config = guilds_collection.find_one({"guild_id": interaction.guild_id})
        duel_cat_id  = guild_config.get("duel_category_id") if guild_config else None

        if not duel_cat_id:
            return await interaction.followup.send(
                "❌ Duel category not configured. Ask an admin to run `/setduelchannel`.",
                ephemeral=True,
            )

        if interaction.channel.category_id != duel_cat_id:
            duel_cat = discord.utils.get(interaction.guild.categories, id=duel_cat_id)
            cat_name = duel_cat.name if duel_cat else "the configured duel category"
            return await interaction.followup.send(
                f"❌ Please use this command in a channel under **{cat_name}**.",
                ephemeral=True,
            )

        id1, id2 = str(interaction.user.id), str(user.id)
        user1_doc = users_collection.find_one({"discord_id": id1})
        user2_doc = users_collection.find_one({"discord_id": id2})

        if not user1_doc or not user2_doc:
            return await interaction.followup.send(
                "❌ Both users must be verified to start a duel.", ephemeral=True
            )

        h1, h2 = user1_doc["cfid"], user2_doc["cfid"]

        # Create private duel channel inside the category
        category = discord.utils.get(interaction.guild.categories, id=duel_cat_id)
        try:
            duel_channel = await category.create_text_channel(
                name=f"duel-{interaction.user.name[:10]}-vs-{user.name[:10]}",
                overwrites={
                    interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    interaction.user:               discord.PermissionOverwrite(read_messages=True, send_messages=True),
                    user:                           discord.PermissionOverwrite(read_messages=True, send_messages=True),
                    interaction.guild.me:           discord.PermissionOverwrite(read_messages=True, send_messages=True),
                },
            )
        except discord.HTTPException as e:
            return await interaction.followup.send(
                f"❌ Could not create duel channel: {e}", ephemeral=True
            )

        challenger   = interaction.user
        min_r, max_r = min_rating, max_rating

        class DuelConfirmView(discord.ui.View):
            def __init__(view_self):
                super().__init__(timeout=120)  # 2 min to accept

            @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success)
            async def accept(
                view_self,
                interaction2: discord.Interaction,
                button: discord.ui.Button,
            ) -> None:
                if interaction2.user.id != user.id:
                    return await interaction2.response.send_message(
                        "❌ Only the challenged user can accept.", ephemeral=True
                    )

                # BUG FIX: defer the button interaction immediately
                await interaction2.response.defer()

                for item in view_self.children:
                    item.disabled = True
                try:
                    await interaction2.message.edit(view=view_self)
                except Exception:
                    pass

                try:
                    problem = await get_unsolved_problem(min_r, max_r, h1, h2)
                except Exception as e:
                    await duel_channel.send(f"❌ Error fetching problem: {e}")
                    await asyncio.sleep(10)
                    try:
                        await duel_channel.delete()
                    except Exception:
                        pass
                    return

                if not problem:
                    await duel_channel.send("❌ No unsolved problem found in that rating range.")
                    await asyncio.sleep(10)
                    try:
                        await duel_channel.delete()
                    except Exception:
                        pass
                    return

                prob_url = (
                    f"https://codeforces.com/problemset/problem/"
                    f"{problem['contestId']}/{problem['index']}"
                )
                await duel_channel.send(
                    f"🎯 **Problem**: [{problem['name']}]({prob_url})\n"
                    f"⚔️ **Duel**: {challenger.name} vs {user.name}\n"
                    f"📊 **Rating Range**: `{min_r} – {max_r}`\n"
                    f"👇 Press **Done** once you've submitted your solution!"
                )

                class DoneView(discord.ui.View):
                    def __init__(view_self2):
                        super().__init__(timeout=None)

                    @discord.ui.button(label="✅ Done", style=discord.ButtonStyle.primary)
                    async def check_done(
                        view_self2,
                        done_interaction: discord.Interaction,
                        _: discord.ui.Button,
                    ) -> None:
                        # BUG FIX: defer immediately so Discord doesn't show interaction failed
                        await done_interaction.response.defer(ephemeral=True)

                        winner_handle = await wait_for_ac(h1, h2, problem)
                        if not winner_handle:
                            return await done_interaction.followup.send(
                                "⏳ No one has solved it yet. Keep trying!", ephemeral=True
                            )

                        loser_handle = h2 if winner_handle == h1 else h1
                        record_duel_result(winner_handle, loser_handle, interaction.guild_id)

                        winner_user = challenger if winner_handle == h1 else user
                        loser_user  = user if winner_handle == h1 else challenger

                        await duel_channel.send(
                            f"🏁 **Duel Complete!**\n"
                            f"🏆 Winner: {winner_user.mention}\n"
                            f"❌ Loser: {loser_user.mention}"
                        )
                        try:
                            await interaction.channel.send(
                                f"📣 Duel Result: **{challenger.name}** vs **{user.name}** "
                                f"→ Winner: **{winner_user.name}** 🏆"
                            )
                        except Exception:
                            pass

                        await asyncio.sleep(20)
                        try:
                            await duel_channel.delete()
                        except Exception:
                            pass

                await duel_channel.send(
                    "🔘 Press below once you believe the problem has been solved:",
                    view=DoneView(),
                )

            @discord.ui.button(label="❌ Reject", style=discord.ButtonStyle.danger)
            async def reject(
                view_self,
                interaction2: discord.Interaction,
                button: discord.ui.Button,
            ) -> None:
                if interaction2.user.id != user.id:
                    return await interaction2.response.send_message(
                        "❌ Only the challenged user can reject.", ephemeral=True
                    )
                # BUG FIX: defer first
                await interaction2.response.defer()
                for item in view_self.children:
                    item.disabled = True
                try:
                    await interaction2.message.edit(view=view_self)
                except Exception:
                    pass
                await duel_channel.send("❌ Duel rejected.")
                await asyncio.sleep(3)
                try:
                    await duel_channel.delete()
                except Exception:
                    pass

        await duel_channel.send(
            f"🎮 **Duel Challenge!**\n"
            f"{user.mention}, you are challenged by {challenger.mention}!\n"
            f"📊 Rating Range: `{min_rating} – {max_rating}`\n"
            f"Do you accept?",
            view=DuelConfirmView(),
        )
        await interaction.followup.send(
            f"📨 Duel request sent! Check <#{duel_channel.id}>", ephemeral=True
        )

    @app_commands.command(name="duelleaderboard", description="📈 Top 10 duelists in this server")
    async def duel_leaderboard(self, interaction: discord.Interaction) -> None:
        users = (
            users_collection
            .find({"guild_id": interaction.guild_id, "duel_points": {"$exists": True}})
            .sort("duel_points", -1)
            .limit(10)
        )
        embed = discord.Embed(
            title="🏆 Top Duelists",
            description="Only showing users from **this server**",
            color=discord.Color.blurple(),
        )
        entries = list(users)
        if not entries:
            embed.description = "No duel data yet. Start a `/duel`!"
        for i, u in enumerate(entries, 1):
            embed.add_field(
                name=f"#{i}  –  {u.get('cfid', 'Unknown')}",
                value=f"🏅 Points: **{u.get('duel_points', 0)}**",
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="myduelpoints", description="📊 Check your current duel points")
    async def my_duel_points(self, interaction: discord.Interaction) -> None:
        user = users_collection.find_one(
            {"discord_id": str(interaction.user.id), "guild_id": interaction.guild_id}
        )
        if not user or "cfid" not in user:
            return await interaction.response.send_message(
                "❌ You must be verified first.", ephemeral=True
            )
        await interaction.response.send_message(
            f"📈 `{user['cfid']}` has **{user.get('duel_points', 0)}** duel points."
        )

    @app_commands.command(name="myduelhistory", description="📉 View your duel point graph")
    async def my_duel_history(self, interaction: discord.Interaction) -> None:
        user = users_collection.find_one(
            {"discord_id": str(interaction.user.id), "guild_id": interaction.guild_id}
        )
        if not user or "cfid" not in user:
            return await interaction.response.send_message(
                "❌ You must be verified first.", ephemeral=True
            )
        history = user.get("duel_history", [])
        if not history:
            return await interaction.response.send_message(
                "📉 No duel history found yet.", ephemeral=True
            )
        graph_buf = generate_duel_history_graph(history, user["cfid"])
        if not graph_buf:
            return await interaction.response.send_message("⚠️ Could not generate graph.")

        file  = discord.File(graph_buf, filename="duel_history.png")
        embed = discord.Embed(
            title=f"{user['cfid']}'s Duel History",
            description="📈 Your duel performance over time",
            color=discord.Color.green(),
        )
        embed.set_image(url="attachment://duel_history.png")
        await interaction.response.send_message(embed=embed, file=file)

    @app_commands.command(name="resetduel", description="Admin only: Reset a user's duel stats")
    @app_commands.describe(user="The user to reset")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_duel(self, interaction: discord.Interaction, user: discord.User) -> None:
        result = users_collection.update_one(
            {"discord_id": str(user.id), "guild_id": interaction.guild_id},
            {"$set": {"duel_points": 0}, "$unset": {"duel_history": ""}},
        )
        if result.modified_count == 0:
            return await interaction.response.send_message(
                "⚠️ User not found in this server.", ephemeral=True
            )
        await interaction.response.send_message(
            f"✅ Reset duel stats for `{user.name}`.", ephemeral=True
        )

    @app_commands.command(name="resetduelall", description="Admin only: Reset ALL duel points")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_duel_all(self, interaction: discord.Interaction) -> None:
        result = users_collection.update_many(
            {"guild_id": interaction.guild_id},
            {"$set": {"duel_points": 0}, "$unset": {"duel_history": ""}},
        )
        await interaction.response.send_message(
            f"✅ Reset duel points for `{result.modified_count}` users.", ephemeral=True
        )

    @app_commands.command(name="clearduelleaderboard", description="Admin only: Wipe entire duel leaderboard")
    @app_commands.checks.has_permissions(administrator=True)
    async def clear_duel_leaderboard(self, interaction: discord.Interaction) -> None:
        result = users_collection.update_many(
            {}, {"$unset": {"duel_points": "", "duel_history": ""}}
        )
        await interaction.response.send_message(
            f"✅ Cleared leaderboard for `{result.modified_count}` users.", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DuelCog(bot))
