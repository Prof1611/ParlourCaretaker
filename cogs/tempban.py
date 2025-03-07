import discord
import logging
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
import re
from datetime import datetime, timedelta, timezone


class TempBan(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ban_file = "bans.json"
        self.load_bans()
        self.check_bans.start()

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"\033[96mTempBan\033[0m cog synced successfully.")

    def load_bans(self):
        if os.path.exists(self.ban_file):
            with open(self.ban_file, "r") as f:
                self.ban_data = json.load(f)
        else:
            self.ban_data = {}

    def save_bans(self):
        with open(self.ban_file, "w") as f:
            json.dump(self.ban_data, f)

    def parse_duration(self, duration_str: str) -> int:
        pattern = r"(\d+)([smhd])"
        match = re.match(pattern, duration_str)

        if not match:
            raise ValueError(
                """Please specify the duration in either seconds(s), minutes(m), hours(h), or days(d)!

                **Examples:**
                    '100s', '5m', '3h', '2d'."""
            )

        try:
            amount = int(match.group(1))
            unit = match.group(2)

            if amount <= 0:
                raise ValueError("The duration can't be a negative number!")

            unit_mapping = {"s": 1, "m": 60, "h": 3600, "d": 86400}
            return amount * unit_mapping[unit]
        except (ValueError, OverflowError) as e:
            raise ValueError(f"Error parsing duration '{duration_str}': {str(e)}")

    @app_commands.command(name="tempban", description="Temporarily bans a member and sends them a notice via DM.")
    async def tempban(self, interaction: discord.Interaction, member: discord.Member, duration: str, *, reason: str):
        """Temporarily bans a user and sends a properly formatted DM with multi-paragraph support."""

        if not interaction.user.guild_permissions.ban_members:
            embed = discord.Embed(
                title="Error",
                description="You don't have permission to ban members!",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        try:
            duration_seconds = self.parse_duration(duration)
        except ValueError as e:
            embed = discord.Embed(title="Invalid duration", description=str(e), color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        unban_time = (datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)).isoformat()

        dm_message = f"""**NOTICE: Temporary Ban from The Parlour Discord Server**

Dear {member.display_name},

We are writing to inform you that you have been temporarily banned from The Parlour Discord server for **{duration}**.

**Reason for Temporary Ban:**
{reason}

We take upholding the standards of our community very seriously, and continued disruptive or disrespectful behaviour will not be tolerated.

Upon the expiration of your ban, you are welcome to re-join the server. We encourage you to take this time to reflect on your behaviour and consider how you can contribute positively to our community moving forward.

**Appeal Process:**  
If you wish to appeal this ban, you may do so by filling out the following form:  
🔗 [Appeal Form](https://forms.gle/Sn73Tvn7VJP2eiTD6)

Sincerely,  
The Parlour Moderation Team  
*Please do not reply to this message as the staff team will not see it.*"""

        try:
            await member.send(dm_message)
            logging.info(f"Successfully sent temporary ban notice to '{member.name}' via DM.")
        except discord.Forbidden:
            logging.warning(f"Failed to send a DM to {member.name}. They might have DMs disabled.")
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="Warning",
                    description=f"Could not send a DM to {member.mention}. They may have DMs disabled.",
                    color=discord.Color.orange(),
                ),
                ephemeral=True,
            )

        await interaction.guild.ban(member, reason=reason, delete_message_days=0)
        logging.info(f"Temporarily banned '{member.name}' from '{interaction.guild.name}' for '{duration}'.")

        embed = discord.Embed(
            title="Member Banned",
            description=f"Temporarily banned {member.mention} for **{duration}**.\n\n**Reason:**\n{reason}",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)

        self.ban_data[str(member.id)] = {
            "username": member.name,
            "guild_id": interaction.guild.id,
            "unban_time": unban_time,
        }
        self.save_bans()

    @tasks.loop(seconds=15)
    async def check_bans(self):
        now = datetime.now(timezone.utc)
        to_unban = []

        for user_id, ban_info in self.ban_data.items():
            unban_time = datetime.fromisoformat(ban_info["unban_time"])
            if now >= unban_time:
                to_unban.append((user_id, ban_info["guild_id"]))

        for user_id, guild_id in to_unban:
            guild = self.bot.get_guild(guild_id)
            if guild:
                member = discord.Object(id=user_id)
                try:
                    await guild.unban(member)
                    logging.info(f"Successfully unbanned user id: {user_id} from guild id: {guild_id}.")
                except discord.NotFound:
                    logging.warning(f"Failed to unban user id: {user_id}, user not found in guild id: {guild_id}.")
            del self.ban_data[user_id]

        self.save_bans()

    @check_bans.before_loop
    async def before_check_bans(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(TempBan(bot))
