import discord
import logging
import sqlite3
import asyncio
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
import yaml
import re


def audit_log(message: str):
    """Append a timestamped message to the audit log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("audit.log", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


class TempBan(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Load configuration from config.yaml for log channel etc.
        with open("config.yaml", "r", encoding="utf-8") as config_file:
            self.config = yaml.safe_load(config_file)
        # Connect to the database file "database.db" (check_same_thread set to False for multi-threaded use)
        self.db = sqlite3.connect("database.db", check_same_thread=False)
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS temp_bans (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                guild_id INTEGER,
                unban_time TEXT
            )
            """
        )
        self.db.commit()
        self.check_bans.start()

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info("\033[96mTempBan\033[0m cog synced successfully.")
        audit_log("TempBan cog synced successfully.")

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

    def add_ban(self, user_id: int, username: str, guild_id: int, unban_time: str):
        """Insert or replace a temporary ban record in the database."""
        self.db.execute(
            "INSERT OR REPLACE INTO temp_bans (user_id, username, guild_id, unban_time) VALUES (?, ?, ?, ?)",
            (user_id, username, guild_id, unban_time),
        )
        self.db.commit()

    def delete_ban(self, user_id: int):
        """Delete a temporary ban record from the database."""
        self.db.execute("DELETE FROM temp_bans WHERE user_id = ?", (user_id,))
        self.db.commit()

    def get_all_bans(self):
        """Retrieve all temporary ban records from the database."""
        cursor = self.db.execute("SELECT user_id, guild_id, unban_time FROM temp_bans")
        return cursor.fetchall()

    @app_commands.command(
        name="tempban",
        description="Temporarily bans a member and sends them a notice via DM.",
    )
    async def tempban(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        duration: str,
        *,
        reason: str,
    ):
        moderator = interaction.user  # actor performing the command

        # Log the invocation of the command.
        audit_log(
            f"{moderator.name} (ID: {moderator.id}) invoked /tempban for {user.name} (ID: {user.id}) with duration '{duration}' in guild '{interaction.guild.name}' (ID: {interaction.guild.id})."
        )

        if not interaction.user.guild_permissions.ban_members:
            embed = discord.Embed(
                title="Error",
                description="You don't have permission to ban members!",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            audit_log(
                f"{moderator.name} (ID: {moderator.id}) attempted /tempban but lacks permission in guild '{interaction.guild.name}' (ID: {interaction.guild.id})."
            )
            return

        try:
            duration_seconds = self.parse_duration(duration)
        except ValueError as e:
            embed = discord.Embed(
                title="Invalid duration", description=str(e), color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            audit_log(
                f"{moderator.name} (ID: {moderator.id}) provided invalid duration '{duration}' for /tempban on {user.name} (ID: {user.id})."
            )
            return

        unban_time = (
            datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
        ).isoformat()

        dm_message = f"""**NOTICE: Temporary Ban from The Parlour Discord Server**

Dear {user.display_name},

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
            await user.send(dm_message)
            logging.info(
                f"Successfully sent temporary ban notice to {user.name} (ID: {user.id}) via DM."
            )
            audit_log(
                f"{moderator.name} (ID: {moderator.id}) sent temporary ban DM notice to {user.name} (ID: {user.id})."
            )
        except discord.Forbidden:
            logging.warning(
                f"Failed to send a DM to {user.name} (ID: {user.id}). They might have DMs disabled."
            )
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="Warning",
                    description=f"Could not send a DM to {user.mention}. They may have DMs disabled.",
                    color=discord.Color.orange(),
                ),
                ephemeral=True,
            )
            audit_log(
                f"{moderator.name} (ID: {moderator.id}) failed to send DM notice to {user.name} (ID: {user.id}) due to DMs being disabled."
            )

        await interaction.guild.ban(user, reason=reason, delete_message_days=0)
        logging.info(
            f"Temporarily banned {user.name} (ID: {user.id}) from '{interaction.guild.name}' (ID: {interaction.guild.id}) for '{duration}'."
        )
        audit_log(
            f"{moderator.name} (ID: {moderator.id}) temporarily banned {user.name} (ID: {user.id}) from guild '{interaction.guild.name}' (ID: {interaction.guild.id}) for duration '{duration}' with reason: {reason}."
        )

        embed = discord.Embed(
            title="Member Banned",
            description=f"Temporarily banned {user.mention} for **{duration}**.\n\n**Reason:**\n{reason}",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)

        # Store the ban in the database.
        self.add_ban(user.id, user.name, interaction.guild.id, unban_time)

        # --- Log the moderation action in the log channel ---
        logs_channel_id = self.config.get("logs_channel_id")
        if logs_channel_id:
            logs_channel = interaction.guild.get_channel(logs_channel_id)
            log_link = (
                f"https://discord.com/channels/{interaction.guild.id}/{logs_channel_id}"
            )
            if logs_channel:
                try:
                    await logs_channel.send(
                        f"""**Username:** {user.mention}
**User ID:** {user.id}
**Category of Discipline:** Temporary Ban
**Timespan of Discipline:** {duration}
**Reason of Discipline:** {reason}
**Link to Ticket Transcript:** N/A
**Date of Discipline:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Moderators Involved:** {moderator.mention}"""
                    )
                    logging.info(
                        f"Temporary ban logged in '#{logs_channel.name}' (ID: {logs_channel.id})."
                    )
                    audit_log(
                        f"{moderator.name} (ID: {moderator.id}) logged temporary ban for {user.name} (ID: {user.id}) in log channel #{logs_channel.name} (ID: {logs_channel.id})."
                    )
                    embed = discord.Embed(
                        title="Action Logged",
                        description=f"Temporary ban successfully logged in [logs channel]({log_link}).",
                        color=discord.Color.green(),
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                except discord.HTTPException as e:
                    logging.error(f"Error logging temporary ban: {e}")
                    audit_log(
                        f"{moderator.name} (ID: {moderator.id}) encountered error when logging temporary ban for {user.name} (ID: {user.id}) in log channel (ID: {logs_channel_id}): {e}"
                    )
                    await interaction.followup.send(
                        embed=discord.Embed(
                            title="Error",
                            description=f"Failed to log the temporary ban action in [logs channel]({log_link}).",
                            color=discord.Color.red(),
                        ),
                        ephemeral=True,
                    )
            else:
                logging.warning("Log channel not found; please check your config.")
                audit_log(
                    f"{moderator.name} (ID: {moderator.id}) could not log temporary ban for {user.name} (ID: {user.id}) because log channel with ID {logs_channel_id} was not found in guild '{interaction.guild.name}' (ID: {interaction.guild.id})."
                )
        else:
            logging.warning("logs_channel_id not set in config.yaml.")
            audit_log(
                f"{moderator.name} (ID: {moderator.id}) attempted to log temporary ban for {user.name} (ID: {user.id}) but no logs_channel_id was set in config.yaml."
            )

    @tasks.loop(seconds=15)
    async def check_bans(self):
        now = datetime.now(timezone.utc)
        bans = self.get_all_bans()
        for user_id, guild_id, unban_time_str in bans:
            unban_time = datetime.fromisoformat(unban_time_str)
            if now >= unban_time:
                guild = self.bot.get_guild(guild_id)
                if guild:
                    member_obj = discord.Object(id=user_id)
                    try:
                        await guild.unban(member_obj)
                        logging.info(
                            f"Successfully unbanned user id: {user_id} from guild id: {guild_id}."
                        )
                        audit_log(
                            f"Unbanned user (ID: {user_id}) in guild (ID: {guild_id}) as ban duration expired."
                        )
                    except discord.NotFound:
                        logging.warning(
                            f"Failed to unban user id: {user_id}; user not found in guild id: {guild_id}."
                        )
                        audit_log(
                            f"Failed to unban user (ID: {user_id}) in guild (ID: {guild_id}) - user not found."
                        )
                self.delete_ban(user_id)

    @check_bans.before_loop
    async def before_check_bans(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(TempBan(bot))
