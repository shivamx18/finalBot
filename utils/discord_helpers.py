"""
utils/discord_helpers.py — Reusable Discord utility functions.

These are thin wrappers that combine Discord.py calls and DB lookups
so cogs stay clean and avoid duplicating boilerplate.
"""

import discord
from config.database import guilds_collection, users_collection
from config.settings import ROLE_COLORS


# ── Channel / category permission checks ─────────────────────────────────────

async def check_and_warn(interaction: discord.Interaction) -> bool:
    """Return True if the command is used inside the configured bot category.

    Sends an ephemeral error message and returns False if the wrong category
    is being used. Returns True (silently) if no category has been configured.
    """
    guild_config = guilds_collection.find_one({"guild_id": interaction.guild_id})
    if not guild_config or "command_category_id" not in guild_config:
        return True

    allowed_category_id = guild_config["command_category_id"]
    if interaction.channel.category_id == allowed_category_id:
        return True

    allowed_cat = discord.utils.get(
        interaction.guild.categories, id=allowed_category_id
    )
    msg = (
        f"❌ Please use bot commands in channels under the **{allowed_cat.name}** category."
        if allowed_cat
        else "❌ This command is not allowed here."
    )
    await interaction.response.send_message(msg, ephemeral=True)
    return False


# ── User ↔ handle lookups ─────────────────────────────────────────────────────

def get_user_handle(discord_id: int) -> str | None:
    """Return the CF handle linked to *discord_id*, or None."""
    user = users_collection.find_one({"discord_id": str(discord_id)})
    return user.get("cfid") if user else None


# ── Role management ───────────────────────────────────────────────────────────

async def assign_cf_rank_role(
    member: discord.Member,
    guild: discord.Guild,
    new_rank: str,
) -> discord.Role:
    """Remove all existing CF rank roles from *member* and assign *new_rank*.

    Creates the role in the guild if it does not exist yet.
    Returns the assigned role.
    """
    # Remove stale CF roles
    for rank_name in ROLE_COLORS:
        role_obj = discord.utils.get(guild.roles, name=rank_name.title())
        if role_obj and role_obj in member.roles:
            await member.remove_roles(role_obj)

    # Find or create target role
    role_name  = new_rank.title()
    role_color = ROLE_COLORS.get(new_rank.lower(), 0xCCCCCC)
    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        role = await guild.create_role(
            name=role_name,
            colour=discord.Colour(role_color),
            reason="CF rank role auto-created on verification",
        )

    await member.add_roles(role)
    return role
