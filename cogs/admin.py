"""
cogs/admin.py — Guild setup & configuration commands (admin-only).
"""

import discord
from discord import app_commands
from discord.ext import commands

from config.database import guilds_collection


class AdminCog(commands.Cog, name="Admin"):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="setcommandchannel",
        description="Restrict bot commands to the current channel's category (admin only)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_command_channel(self, interaction: discord.Interaction) -> None:
        category = interaction.channel.category
        if not category:
            return await interaction.response.send_message(
                "❌ Run this command in a channel **inside a category**.", ephemeral=True
            )
        guilds_collection.update_one(
            {"guild_id": interaction.guild_id},
            {"$set": {"command_category_id": category.id}},
            upsert=True,
        )
        await interaction.response.send_message(
            f"✅ Bot commands restricted to **{category.name}** category.", ephemeral=True
        )

    @app_commands.command(
        name="setcfcelebrationchannel",
        description="Set this channel for CF rank-up celebration announcements",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_celebration_channel(self, interaction: discord.Interaction) -> None:
        guilds_collection.update_one(
            {"guild_id": interaction.guild_id},
            {"$set": {"cf_celebration_channel": interaction.channel_id}},
            upsert=True,
        )
        await interaction.response.send_message("🎉 Celebration channel set!", ephemeral=True)

    @app_commands.command(
        name="setduelchannel",
        description="Admin only: Set the category where duels are allowed",
    )
    @app_commands.describe(channel="Any channel inside the duel category")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_duel_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        category = channel.category
        if not category:
            return await interaction.response.send_message(
                "❌ Choose a channel that is inside a category.", ephemeral=True
            )
        guilds_collection.update_one(
            {"guild_id": interaction.guild_id},
            {"$set": {"duel_category_id": category.id}},
            upsert=True,
        )
        await interaction.response.send_message(
            f"✅ Duel category set to **{category.name}**.", ephemeral=True
        )

    @app_commands.command(
        name="setreminderchannel",
        description="Admin only: Set contest reminder channel and mention role",
    )
    @app_commands.describe(
        channel="Channel where reminders will be sent",
        role="Role to mention in reminders",
        enable_cf="Enable Codeforces reminders?",
        enable_cc="Enable CodeChef reminders?",
        enable_lc="Enable LeetCode reminders?",
        custom_message="Customize message. Use {name}, {url}, {platform}, {role}",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_reminder_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        role: discord.Role,
        enable_cf: bool = True,
        enable_cc: bool = True,
        enable_lc: bool = True,
        custom_message: str = "CONTEST TODAY: {name}\nREGISTER HERE: {url}\n{role}",
    ) -> None:
        guilds_collection.update_one(
            {"guild_id": interaction.guild.id},
            {"$set": {
                "reminder_channel":   channel.id,
                "reminder_role":      role.id,
                "reminder_message":   custom_message,
                "reminder_enable_cf": enable_cf,
                "reminder_enable_cc": enable_cc,
                "reminder_enable_lc": enable_lc,
            }},
            upsert=True,
        )
        await interaction.response.send_message("✅ Reminder settings updated!", ephemeral=True)

    @app_commands.command(
        name="setmodchannel",
        description="Set the mod feedback / suggestions channel (admin only)",
    )
    @app_commands.describe(channel="Channel where suggestions should go")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_mod_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        guilds_collection.update_one(
            {"guild_id": interaction.guild_id},
            {"$set": {"mod_channel": channel.id}},
            upsert=True,
        )
        await interaction.response.send_message(
            f"✅ Mod channel set to {channel.mention}", ephemeral=True
        )

    @app_commands.command(
        name="enablereminder",
        description="Admin only: Enable contest reminders for a platform",
    )
    @app_commands.describe(platform="Platform to enable: cf / cc / lc")
    @app_commands.checks.has_permissions(administrator=True)
    async def enable_reminder(self, interaction: discord.Interaction, platform: str) -> None:
        platform = platform.lower()
        if platform not in ("cf", "cc", "lc"):
            return await interaction.response.send_message(
                "❌ Valid platforms: `cf`, `cc`, `lc`", ephemeral=True
            )
        field_map = {"cf": "reminder_enable_cf", "cc": "reminder_enable_cc", "lc": "reminder_enable_lc"}
        guilds_collection.update_one(
            {"guild_id": interaction.guild.id},
            {"$set": {field_map[platform]: True}},
            upsert=True,
        )
        await interaction.response.send_message(
            f"🔔 Reminders for **{platform.upper()}** enabled.", ephemeral=True
        )

    @app_commands.command(
        name="disablereminder",
        description="Admin only: Disable contest reminders for a platform",
    )
    @app_commands.describe(platform="Platform to disable: cf / cc / lc")
    @app_commands.checks.has_permissions(administrator=True)
    async def disable_reminder(self, interaction: discord.Interaction, platform: str) -> None:
        platform = platform.lower()
        if platform not in ("cf", "cc", "lc"):
            return await interaction.response.send_message(
                "❌ Valid platforms: `cf`, `cc`, `lc`", ephemeral=True
            )
        field_map = {"cf": "reminder_enable_cf", "cc": "reminder_enable_cc", "lc": "reminder_enable_lc"}
        guilds_collection.update_one(
            {"guild_id": interaction.guild.id},
            {"$set": {field_map[platform]: False}},
            upsert=True,
        )
        await interaction.response.send_message(
            f"🔕 Reminders for **{platform.upper()}** disabled.", ephemeral=True
        )

    # BUG FIX: on_app_command_error must be registered on bot.tree, not as a Cog listener.
    # Moved it to main.py's on_ready via bot.tree.error instead.


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))
