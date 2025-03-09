import discord
import logging
import yaml
import datetime
from discord import app_commands
from discord.ext import commands
import asyncio


class Kick(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Load the config file with UTF-8 encoding to handle special characters like emojis
        with open("config.yaml", "r", encoding="utf-8") as config_file:
            self.config = yaml.safe_load(config_file)

    def audit_log(self, message: str):
        """Append a timestamped message to the audit log file."""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open("audit.log", "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"\033[96mKick\033[0m cog synced successfully.")
        self.audit_log("Kick cog synced successfully.")

    @app_commands.command(
        name="kick", description="Kicks a member and sends them a notice via DM."
    )
    async def kick(
        self, interaction: discord.Interaction, user: discord.Member, *, reason: str
    ):
        # Defer the response to avoid timeout errors.
        await interaction.response.defer()
        moderator = interaction.user  # actor performing the action

        try:
            if user.id in self.config["owner_ids"]:
                logging.error("Owner entered as victim.")
                self.audit_log(
                    f"{moderator.name} (ID: {moderator.id}) attempted to kick owner {user.name} (ID: {user.id}). Action aborted."
                )
                embed = discord.Embed(
                    title="Error",
                    description="Nice try, fool.",
                    color=discord.Color.red(),
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            else:
                try:
                    dm_text = f"""**NOTICE: Kick from The Parlour Discord Server**

Dear {user.mention},

We are writing to inform you that you have been kicked from The Parlour Discord server. This action is a result of your violations of our community rules.

**Reason for Kick:** {reason}

We take upholding the standards of our community very seriously, and continued disruptive or disrespectful behaviour will not be tolerated.
You are welcome to rejoin the server provided you review our community rules to ensure you do not break them again.

Sincerely,
The Parlour Moderation Team
"""
                    await user.send(dm_text)
                    logging.info(
                        f"Successfully sent kick notice to {user.name} (ID: {user.id}) via DM."
                    )
                    self.audit_log(
                        f"{moderator.name} (ID: {moderator.id}) sent kick notice via DM to {user.name} (ID: {user.id})."
                    )
                except discord.HTTPException as e:
                    if e.status == 403:  # DMs Disabled
                        logging.error(
                            f"DMs disabled when attempting to send kick notice via DM. Error: {e}"
                        )
                        self.audit_log(
                            f"{moderator.name} (ID: {moderator.id}) failed to send DM notice to {user.name} (ID: {user.id}); DMs disabled."
                        )
                        embed = discord.Embed(
                            title="Error",
                            description=f"That user has their DMs disabled. Failed to send notice.",
                            color=discord.Color.red(),
                        )
                        await interaction.followup.send(embed=embed)
                    else:
                        logging.error(
                            f"Error when attempting to send kick notice via DM: {e}"
                        )
                        self.audit_log(
                            f"{moderator.name} (ID: {moderator.id}) encountered error sending DM notice to {user.name} (ID: {user.id}): {e}"
                        )
                        embed = discord.Embed(
                            title="Error",
                            description=f"Failed to send kick notice to {user.mention} via DM.",
                            color=discord.Color.red(),
                        )
                        await interaction.followup.send(embed=embed)
                try:
                    # Try kick the user from the server.
                    await user.kick(reason=reason)
                    guild = interaction.guild
                    logging.info(
                        f"Kicked {user.name} (ID: {user.id}) from '{guild.name}' (ID: {guild.id})."
                    )
                    self.audit_log(
                        f"{moderator.name} (ID: {moderator.id}) kicked {user.name} (ID: {user.id}) from guild '{guild.name}' (ID: {guild.id}) for reason: {reason}."
                    )
                    embed = discord.Embed(
                        title="Member Kicked",
                        description=f"Kicked {user.mention} from the server and sent them a notice via DM.",
                        color=discord.Color.green(),
                    )
                    await interaction.followup.send(embed=embed)
                except discord.HTTPException as e:
                    if e.status == 403:  # Bot has no permission to kick
                        logging.error(f"No permission to kick. Error: {e}")
                        self.audit_log(
                            f"{moderator.name} (ID: {moderator.id}) failed to kick {user.name} (ID: {user.id}) - insufficient permissions in guild '{guild.name}' (ID: {guild.id})."
                        )
                        embed = discord.Embed(
                            title="Error",
                            description=f"I don't have permission to kick members!",
                            color=discord.Color.red(),
                        )
                        await interaction.followup.send(embed=embed)
                    else:
                        logging.error(
                            f"Error when attempting to kick {user.name} from '{guild.name}'. Error: {e}"
                        )
                        self.audit_log(
                            f"{moderator.name} (ID: {moderator.id}) encountered error while kicking {user.name} (ID: {user.id}) from guild '{guild.name}' (ID: {guild.id}): {e}"
                        )
                        embed = discord.Embed(
                            title="Error",
                            description=f"Failed to kick {user.mention}.",
                            color=discord.Color.red(),
                        )
                        await interaction.followup.send(embed=embed)

                # Log the moderation action in the log channel.
                logs_channel_id = self.config["logs_channel_id"]
                guild = interaction.guild
                logs_channel = guild.get_channel(logs_channel_id)
                log_link = f"https://discord.com/channels/{guild.id}/{logs_channel_id}"
                if logs_channel:
                    try:
                        log_message = f"""**Username:** {user.mention}
**User ID:** {user.id}
**Category of Discipline:** Kick
**Timespan of Discipline:** N/A
**Reason of Discipline:** {reason}
**Link to Ticket Transcript:** N/A
**Date of Discipline:** {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Moderators Involved:** {moderator.mention}"""
                        await logs_channel.send(log_message)
                        logging.info(
                            f"Kick logged in '#{logs_channel.name}' (ID: {logs_channel.id})."
                        )
                        self.audit_log(
                            f"{moderator.name} (ID: {moderator.id}) logged kick for {user.name} (ID: {user.id}) in log channel #{logs_channel.name} (ID: {logs_channel.id})."
                        )
                        embed = discord.Embed(
                            title="Action Logged",
                            description=f"Kick successfully logged in {log_link}.",
                            color=discord.Color.green(),
                        )
                        await interaction.followup.send(embed=embed, ephemeral=True)
                    except discord.HTTPException as e:
                        if e.status == 403:
                            logging.error(
                                f"No access to '#{logs_channel.name}' (ID: {logs_channel.id}). Error: {e}"
                            )
                            self.audit_log(
                                f"{moderator.name} (ID: {moderator.id}) failed to log action in log channel #{logs_channel.name} (ID: {logs_channel.id}) for {user.name} (ID: {user.id}); no access."
                            )
                            embed = discord.Embed(
                                title="Error",
                                description=f"I don't have access to {log_link}!",
                                color=discord.Color.red(),
                            )
                            await interaction.followup.send(embed=embed)
                        elif e.status == 404:
                            logging.error(f"Channel not found. Error: {e}")
                            self.audit_log(
                                f"{moderator.name} (ID: {moderator.id}) failed to log action; log channel not found for {user.name} (ID: {user.id})."
                            )
                            embed = discord.Embed(
                                title="Error",
                                description=f"Channel not found!",
                                color=discord.Color.red(),
                            )
                            await interaction.followup.send(embed=embed)
                        elif e.status == 429:
                            logging.error(f"RATE LIMIT. Error: {e}")
                            self.audit_log(
                                f"{moderator.name} (ID: {moderator.id}) encountered rate limit when logging kick for {user.name} (ID: {user.id})."
                            )
                            embed = discord.Embed(
                                title="Error",
                                description=f"Too many requests! Please try later.",
                                color=discord.Color.red(),
                            )
                            await interaction.followup.send(embed=embed)
                        elif e.status in {500, 502, 503, 504}:
                            logging.error(f"Discord API Error. Error: {e}")
                            self.audit_log(
                                f"{moderator.name} (ID: {moderator.id}) encountered Discord API error when logging kick for {user.name} (ID: {user.id}): {e}"
                            )
                            embed = discord.Embed(
                                title="Error",
                                description=f"Failed to log action in {log_link}. Please try later.",
                                color=discord.Color.red(),
                            )
                            await interaction.followup.send(embed=embed)
                        else:
                            logging.error(
                                f"Failed to log kick in '#{logs_channel.name}' (ID: {logs_channel.id}). Error: {e}"
                            )
                            self.audit_log(
                                f"{moderator.name} (ID: {moderator.id}) unknown error when logging kick for {user.name} (ID: {user.id}) in log channel #{logs_channel.name} (ID: {logs_channel.id}): {e}"
                            )
                            embed = discord.Embed(
                                title="Error",
                                description=f"Failed to log action in {log_link}.",
                                color=discord.Color.red(),
                            )
                            await interaction.followup.send(embed=embed)
        except discord.HTTPException as e:
            logging.error(f"Error when attempting to kick: {e}")
            self.audit_log(
                f"{moderator.name} (ID: {moderator.id}) critical error: Failed to kick and send notice to {user.name} (ID: {user.id}): {e}"
            )
            embed = discord.Embed(
                title="Error",
                description=f"Failed to ban and send notice to {user.mention}. Error: {e}",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Kick(bot))
