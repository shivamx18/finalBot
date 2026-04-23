"""
cogs/verify.py — Codeforces handle verification and user management.
"""

import asyncio
import random
from random import choice
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config.database import guilds_collection, users_collection
from config.settings import ROLE_COLORS
from utils.cf_api import get_user_info, is_rank_up
from utils.discord_helpers import assign_cf_rank_role

RANK_UP_QUOTES = [
    "Hard work beats talent when talent doesn't work hard.",
    "You just ranked up — but you're only getting started. 🚀",
    "Your growth is showing. Keep pushing those limits! 💪",
    "Small steps each day lead to big achievements!",
    "Be proud, be humble, and aim higher!",
]


async def _send_rank_up_celebration(
    interaction: discord.Interaction,
    old_rank: str,
    new_rank: str,
    guild_data: Optional[dict],
) -> None:
    if not guild_data:
        return
    channel_id = guild_data.get("cf_celebration_channel")
    if not channel_id:
        return
    channel = interaction.guild.get_channel(channel_id)
    if not channel:
        return

    embed = discord.Embed(
        title="🎉 Rank Up Alert!",
        description=f"{interaction.user.mention} just levelled up on Codeforces!",
        color=discord.Color.gold(),
    )
    embed.add_field(name="📉 Previous Rank", value=old_rank.title(), inline=True)
    embed.add_field(name="📈 New Rank",      value=new_rank.title(), inline=True)
    embed.add_field(name="💬 Motivation",    value=f"*{choice(RANK_UP_QUOTES)}*", inline=False)
    embed.set_footer(
        text="👏 Congratulations!",
        icon_url=interaction.user.display_avatar.url,
    )
    await channel.send(embed=embed)


class VerifyCog(commands.Cog, name="Verify"):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="verify", description="Link and verify your Codeforces handle")
    @app_commands.describe(cfid="Your Codeforces handle")
    async def verify(self, interaction: discord.Interaction, cfid: str) -> None:
        await interaction.response.defer(ephemeral=True)

        user_id           = str(interaction.user.id)
        verification_code = str(random.randint(1000, 9999))

        # BUG FIX 1: private_thread only works in text channels with Community enabled.
        # Use a public thread instead — it's visible only inside the channel and auto-deletes.
        try:
            thread = await interaction.channel.create_thread(
                name=f"verify-{interaction.user.name[:20]}",
                type=discord.ChannelType.public_thread,
                auto_archive_duration=60,
            )
        except discord.HTTPException as e:
            return await interaction.followup.send(
                f"❌ Could not create verification thread: {e}\n"
                "Make sure the bot has **Create Public Threads** permission in this channel.",
                ephemeral=True,
            )

        class ConfirmView(discord.ui.View):
            def __init__(view_self):
                super().__init__(timeout=300)  # 5 min timeout

            @discord.ui.button(label="✅ Verify", style=discord.ButtonStyle.success)
            async def confirm(
                view_self,
                button_interaction: discord.Interaction,
                _: discord.ui.Button,
            ) -> None:
                if button_interaction.user.id != interaction.user.id:
                    return await button_interaction.response.send_message(
                        "❌ Only the user who started verification can confirm.",
                        ephemeral=True,
                    )

                # BUG FIX 2: ALWAYS acknowledge the button interaction first.
                # Not doing this causes "interaction failed" in Discord.
                await button_interaction.response.defer(ephemeral=True)

                # Disable buttons so user can't click twice
                for item in view_self.children:
                    item.disabled = True
                try:
                    await button_interaction.message.edit(view=view_self)
                except Exception:
                    pass

                # Validate CF profile
                try:
                    info = await get_user_info(cfid)
                    if info.get("firstName", "") != verification_code:
                        raise ValueError("Code mismatch")
                    new_rank   = info.get("rank", "unrated").lower()
                    new_rating = info.get("rating", 0)
                except Exception:
                    await thread.send(
                        "❌ Verification failed. Make sure your Codeforces **first name** "
                        "matches the code exactly, then try `/verify` again."
                    )
                    # BUG FIX 3: respond to the button_interaction after deferring
                    await button_interaction.followup.send(
                        "❌ Verification failed.", ephemeral=True
                    )
                    await asyncio.sleep(15)
                    try:
                        await thread.delete()
                    except Exception:
                        pass
                    return

                # Assign rank role
                await assign_cf_rank_role(interaction.user, interaction.guild, new_rank)

                # Rank-up check (read BEFORE updating DB)
                prev_user = users_collection.find_one({"discord_id": user_id})
                old_rank  = prev_user.get("rank") if prev_user else None

                # Save to DB
                users_collection.update_one(
                    {"discord_id": user_id},
                    {
                        "$set": {
                            "cfid":            cfid,
                            "rating":          new_rating,
                            "rank":            new_rank,
                            "guild_id":        interaction.guild_id,
                            "handle_verified": True,
                        }
                    },
                    upsert=True,
                )

                # Rank-up celebration
                if old_rank and is_rank_up(new_rank, old_rank):
                    guild_data = guilds_collection.find_one({"guild_id": interaction.guild_id})
                    await _send_rank_up_celebration(interaction, old_rank, new_rank, guild_data)

                role_name = new_rank.title()
                await thread.send(f"✅ Verified as `{cfid}` with role **{role_name}**! 🎉")
                await button_interaction.followup.send(
                    f"✅ Successfully verified as `{cfid}`!", ephemeral=True
                )
                await asyncio.sleep(15)
                try:
                    await thread.delete()
                except Exception:
                    pass

        await thread.send(
            f"{interaction.user.mention}, to verify:\n"
            f"1. Go to [Codeforces Settings](https://codeforces.com/settings/general)\n"
            f"2. Set your **First name** to exactly:\n```{verification_code}```\n"
            f"3. Save changes on Codeforces, then click ✅ below.",
            view=ConfirmView(),
        )
        await interaction.followup.send(
            f"🔐 Verification thread created! Check <#{thread.id}>", ephemeral=True
        )

    @app_commands.command(name="unverify", description="Admin only: Unverify a user")
    @app_commands.describe(user="User to unverify")
    @app_commands.checks.has_permissions(administrator=True)
    async def unverify(self, interaction: discord.Interaction, user: discord.User) -> None:
        users_collection.delete_one({"discord_id": str(user.id)})
        member = interaction.guild.get_member(user.id)
        if member:
            for role in member.roles:
                if role.name.lower() in ROLE_COLORS:
                    await member.remove_roles(role)
        await interaction.response.send_message("✅ User unverified and roles removed.", ephemeral=True)

    @app_commands.command(name="verified", description="List all verified users in this server")
    async def verified(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        users = users_collection.find({"guild_id": interaction.guild_id})
        lines = []
        for user in users:
            try:
                member = await self.bot.fetch_user(int(user["discord_id"]))
                lines.append(f"- {member.mention} → `{user['cfid']}`")
            except Exception:
                lines.append(f"- `{user['discord_id']}` → `{user['cfid']}`")

        text = "**Verified Users:**\n" + "\n".join(lines) if lines else "No verified users yet."
        await interaction.followup.send(text)

    @app_commands.command(name="cfid", description="Get a Discord user's linked CF handle")
    @app_commands.describe(user="Discord user")
    async def cfid(self, interaction: discord.Interaction, user: discord.User) -> None:
        record = users_collection.find_one({"discord_id": str(user.id)})
        if record:
            await interaction.response.send_message(
                f"✅ `{user.display_name}` is linked to `{record['cfid']}`."
            )
        else:
            await interaction.response.send_message("❌ That user is not verified.")

    @app_commands.command(name="discordid", description="Get Discord user linked to a CF handle")
    @app_commands.describe(cfid="Codeforces handle")
    async def discordid(self, interaction: discord.Interaction, cfid: str) -> None:
        record = users_collection.find_one({"cfid": cfid})
        if record:
            user = await self.bot.fetch_user(int(record["discord_id"]))
            await interaction.response.send_message(
                f"✅ `{cfid}` is linked to {user.mention}."
            )
        else:
            await interaction.response.send_message("❌ CF handle not found.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VerifyCog(bot))
