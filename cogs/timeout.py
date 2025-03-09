import discord
import logging
import re
import yaml
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone


def audit_log(message: str):
    """Append a timestamped message to the audit log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("audit.log", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


class Timeout(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Load config file for logging and other settings.
        with open("config.yaml", "r", encoding="utf-8") as config_file:
            self.config = yaml.safe_load(config_file)

    def parse_duration(self, duration_str: str) -> timedelta:
        """
        Parses a duration string (e.g. '10s', '5m', '2h', '1d') into a timedelta.
        """
        pattern = r"(\d+)([smhd])"
        match = re.fullmatch(pattern, duration_str)
        if not match:
            raise ValueError(
                "Please specify the duration in seconds(s), minutes(m), hours(h), or days(d) (e.g. '30s', '5m', '2h', '1d')."
            )
        amount = int(match.group(1))
        unit = match.group(2)
        unit_mapping = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        seconds = amount * unit_mapping[unit]
        return timedelta(seconds=seconds)

    @app_commands.command(
        name="timeout", description="Timeout a member for a specified duration."
    )
    @app_commands.describe(
        user="The member to be timed out",
        duration="The duration for the timeout (e.g. '30s', '5m', '2h', '1d')",
        reason="The reason for the timeout (optional; defaults to 'No reason provided.')",
    )
    async def timeout(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        duration: str,
        *,
        reason: str = "No reason provided.",
    ):
        moderator = interaction.user  # Actor performing the command.
        audit_log(
            f"{moderator.name} (ID: {moderator.id}) invoked /timeout for {user.name} (ID: {user.id}) with duration '{duration}' in guild '{interaction.guild.name}' (ID: {interaction.guild.id})."
        )

        if not interaction.user.guild_permissions.moderate_members:
            embed = discord.Embed(
                title="Permission Denied",
                description="You do not have permission to timeout members.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            audit_log(
                f"{moderator.name} (ID: {moderator.id}) attempted /timeout in guild '{interaction.guild.name}' (ID: {interaction.guild.id}) but lacked permission."
            )
            return

        try:
            delta = self.parse_duration(duration)
        except ValueError as e:
            embed = discord.Embed(
                title="Invalid Duration", description=str(e), color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            audit_log(
                f"{moderator.name} (ID: {moderator.id}) provided invalid duration '{duration}' for /timeout on {user.name} (ID: {user.id}). Error: {e}"
            )
            return

        timeout_until = datetime.now(timezone.utc) + delta

        try:
            await user.edit(timeout=timeout_until, reason=reason)
            embed = discord.Embed(
                title="Member Timed Out",
                description=f"{user.mention} has been timed out for **{duration}**.\n**Reason:** {reason}",
                color=discord.Color.green(),
            )
            await interaction.response.send_message(embed=embed)
            logging.info(
                f"Timed out {user} until {timeout_until.isoformat()} for reason: {reason}"
            )
            audit_log(
                f"{moderator.name} (ID: {moderator.id}) successfully timed out {user.name} (ID: {user.id}) until {timeout_until.isoformat()} in guild '{interaction.guild.name}' (ID: {interaction.guild.id}) for reason: {reason}."
            )
        except Exception as e:
            logging.error(f"Error timing out member: {e}")
            embed = discord.Embed(
                title="Error",
                description="An error occurred while attempting to timeout the member.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed)
            audit_log(
                f"{moderator.name} (ID: {moderator.id}) encountered error timing out {user.name} (ID: {user.id}) in guild '{interaction.guild.name}' (ID: {interaction.guild.id}): {e}"
            )
            return

        # Log the moderation action in the log channel.
        guild = interaction.guild
        logs_channel_id = self.config.get("logs_channel_id")
        if logs_channel_id is not None:
            logs_channel = guild.get_channel(logs_channel_id)
            log_link = f"https://discord.com/channels/{guild.id}/{logs_channel_id}"
            if logs_channel:
                try:
                    await logs_channel.send(
                        f"""**Username:** {user.mention}
**User ID:** {user.id}
**Category of Discipline:** Timeout
**Timespan of Discipline:** {duration}
**Reason of Discipline:** {reason}
**Link to Ticket Transcript:** N/A
**Date of Discipline:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Moderators Involved:** {moderator.mention}"""
                    )
                    logging.info(
                        f"Timeout logged in '#{logs_channel.name}' (ID: {logs_channel.id})."
                    )
                    audit_log(
                        f"{moderator.name} (ID: {moderator.id}) logged timeout for {user.name} (ID: {user.id}) in log channel #{logs_channel.name} (ID: {logs_channel.id})."
                    )
                    embed = discord.Embed(
                        title="Action Logged",
                        description=f"Timeout successfully logged in [logs channel]({log_link}).",
                        color=discord.Color.green(),
                    )
                    await interaction.followup.send(embed=embed, ephemeral=True)
                except discord.HTTPException as e:
                    logging.error(f"Error logging timeout: {e}")
                    audit_log(
                        f"{moderator.name} (ID: {moderator.id}) encountered error logging timeout for {user.name} (ID: {user.id}) in log channel (ID: {logs_channel_id}): {e}"
                    )
                    await interaction.followup.send(
                        embed=discord.Embed(
                            title="Error",
                            description=f"Failed to log the timeout action in [logs channel]({log_link}).",
                            color=discord.Color.red(),
                        ),
                        ephemeral=True,
                    )
            else:
                logging.warning("Log channel not found; please check your config.")
                audit_log(
                    f"{moderator.name} (ID: {moderator.id}) could not log timeout for {user.name} (ID: {user.id}) because log channel with ID {logs_channel_id} was not found in guild '{guild.name}' (ID: {guild.id})."
                )
        else:
            logging.warning("logs_channel_id not set in config.yaml.")
            audit_log(
                f"{moderator.name} (ID: {moderator.id}) attempted to log timeout for {user.name} (ID: {user.id}) but no logs_channel_id was set in config.yaml."
            )

    @app_commands.command(
        name="untimeout", description="Remove the timeout from a member."
    )
    @app_commands.describe(user="The member from whom to remove the timeout")
    async def untimeout(self, interaction: discord.Interaction, user: discord.Member):
        moderator = interaction.user
        if not moderator.guild_permissions.moderate_members:
            embed = discord.Embed(
                title="Permission Denied",
                description="You do not have permission to remove timeouts from members.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            audit_log(
                f"{moderator.name} (ID: {moderator.id}) attempted /untimeout in guild '{interaction.guild.name}' (ID: {interaction.guild.id}) but lacked permission."
            )
            return

        try:
            await user.edit(timeout=None, reason="Timeout removed by moderator.")
            embed = discord.Embed(
                title="Timeout Removed",
                description=f"Timeout has been removed from {user.mention}.",
                color=discord.Color.green(),
            )
            await interaction.response.send_message(embed=embed)
            logging.info(f"Removed timeout from {user}")
            audit_log(
                f"{moderator.name} (ID: {moderator.id}) removed timeout from {user.name} (ID: {user.id}) in guild '{interaction.guild.name}' (ID: {interaction.guild.id})."
            )
        except Exception as e:
            logging.error(f"Error removing timeout: {e}")
            embed = discord.Embed(
                title="Error",
                description="An error occurred while attempting to remove the timeout from the member.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed)
            audit_log(
                f"{moderator.name} (ID: {moderator.id}) encountered error removing timeout from {user.name} (ID: {user.id}) in guild '{interaction.guild.name}' (ID: {interaction.guild.id}): {e}"
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Timeout(bot))
