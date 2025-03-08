import discord
import logging
import yaml
import datetime
from discord import app_commands
from discord.ext import commands


class Ban(commands.Cog):
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
        logging.info(f"\033[96mBan\033[0m cog synced successfully.")
        self.audit_log("Ban cog synced successfully.")

    @app_commands.command(
        name="ban", description="Bans a member and sends them a notice via DM."
    )
    async def ban(
        self, interaction: discord.Interaction, member: discord.Member, *, reason: str
    ):
        # Defer the response to avoid timeout errors
        await interaction.response.defer()

        moderator = interaction.user  # actor performing the action

        try:
            if member.id in self.config["owner_ids"]:
                logging.error("Owner entered as victim.")
                self.audit_log(
                    f"Attempted ban on owner {member.name} (ID: {member.id}) by {moderator.name} (ID: {moderator.id}). Action aborted."
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
                    dm_text = f"""**NOTICE: Permanent Ban from The Parlour Discord Server**

Dear {member.mention},

We are writing to inform you that you have been permanently banned from The Parlour Discord server. This action is a result of your repeated violations of our community rules, despite previous warnings and attempts to rectify the situation.

**Reason for Ban:** {reason}

We take upholding the standards of our community very seriously, and continued disruptive or disrespectful behaviour will not be tolerated. This ban ensures a positive and respectful environment for all members.

**Appeal Process:** If you wish to appeal this ban, you may do so by filling out the following form: https://forms.gle/Sn73Tvn7VJP2eiTD6

Sincerely,
The Parlour Moderation Team
*Please do not reply to this message as the staff team will not see it.*"""
                    await member.send(dm_text)
                    logging.info(
                        f"Successfully sent permanent ban notice to {member.name} (ID: {member.id}) via DM."
                    )
                    self.audit_log(
                        f"{moderator.name} (ID: {moderator.id}) sent permanent ban notice via DM to {member.name} (ID: {member.id})."
                    )
                except discord.HTTPException as e:
                    if e.status == 403:  # DMs Disabled
                        logging.error(
                            f"DMs disabled when attempting to send ban notice via DM. Error: {e}"
                        )
                        self.audit_log(
                            f"{moderator.name} (ID: {moderator.id}) failed to send DM notice to {member.name} (ID: {member.id}); DMs disabled."
                        )
                        embed = discord.Embed(
                            title="Error",
                            description=f"That user has their DMs disabled. Failed to send notice.",
                            color=discord.Color.red(),
                        )
                        await interaction.followup.send(embed=embed)
                    else:
                        logging.error(
                            f"Error when attempting to send ban notice via DM: {e}"
                        )
                        self.audit_log(
                            f"{moderator.name} (ID: {moderator.id}) error sending DM notice to {member.name} (ID: {member.id}): {e}"
                        )
                        embed = discord.Embed(
                            title="Error",
                            description=f"Failed to send notice to {member.mention} via DM.",
                            color=discord.Color.red(),
                        )
                        await interaction.followup.send(embed=embed)
                try:
                    # Try ban the user from the server
                    await member.ban(reason=reason, delete_message_days=0)
                    guild = interaction.guild
                    logging.info(
                        f"Permanently banned {member.name} (ID: {member.id}) from '{guild.name}' (ID: {guild.id})."
                    )
                    self.audit_log(
                        f"{moderator.name} (ID: {moderator.id}) permanently banned {member.name} (ID: {member.id}) from guild '{guild.name}' (ID: {guild.id}) for reason: {reason}."
                    )
                    embed = discord.Embed(
                        title="Member Banned",
                        description=f"Permanently banned {member.mention} from the server and sent them a notice via DM.",
                        color=discord.Color.green(),
                    )
                    await interaction.followup.send(embed=embed)
                except discord.HTTPException as e:
                    if e.status == 403:  # Bot has no permission to ban
                        logging.error(f"No permission to ban. Error: {e}")
                        self.audit_log(
                            f"{moderator.name} (ID: {moderator.id}) failed to ban {member.name} (ID: {member.id}) - insufficient permissions in guild '{guild.name}' (ID: {guild.id})."
                        )
                        embed = discord.Embed(
                            title="No Permission",
                            description=f"I don't have permission to ban members!",
                            color=discord.Color.red(),
                        )
                        await interaction.followup.send(embed=embed)
                    else:
                        logging.error(
                            f"Error when attempting to ban {member.name}. Error: {e}"
                        )
                        self.audit_log(
                            f"{moderator.name} (ID: {moderator.id}) error banning {member.name} (ID: {member.id}) in guild '{guild.name}' (ID: {guild.id}): {e}"
                        )
                        embed = discord.Embed(
                            title="Error",
                            description=f"Failed to ban {member.mention}.",
                            color=discord.Color.red(),
                        )
                        await interaction.followup.send(embed=embed)

                # Log the moderation action in the log channel
                logs_channel_id = self.config["logs_channel_id"]
                guild = interaction.guild
                logs_channel = guild.get_channel(logs_channel_id)
                log_link = f"https://discord.com/channels/{guild.id}/{logs_channel_id}"
                if logs_channel:
                    try:
                        log_message = f"""**Username:** {member.mention}
**User ID:** {member.id}
**Category of Discipline:** Permanent Ban
**Timespan of Discipline:** Permanent
**Reason of Discipline:** {reason}
**Link to Ticket Transcript:** N/A
**Date of Discipline:** {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Moderators Involved:** {moderator.mention}"""
                        await logs_channel.send(log_message)
                        logging.info(
                            f"Permanent ban logged in '#{logs_channel.name}' (ID: {logs_channel.id})."
                        )
                        self.audit_log(
                            f"{moderator.name} (ID: {moderator.id}) logged permanent ban for {member.name} (ID: {member.id}) in log channel #{logs_channel.name} (ID: {logs_channel.id})."
                        )
                        embed = discord.Embed(
                            title="Action Logged",
                            description=f"Permanent ban successfully logged in {log_link}.",
                            color=discord.Color.green(),
                        )
                        await interaction.followup.send(embed=embed, ephemeral=True)
                    except discord.HTTPException as e:
                        if e.status == 403:
                            logging.error(
                                f"No access to '#{logs_channel.name}' (ID: {logs_channel.id}). Error: {e}"
                            )
                            self.audit_log(
                                f"{moderator.name} (ID: {moderator.id}) failed to log action in log channel #{logs_channel.name} (ID: {logs_channel.id}) for {member.name} (ID: {member.id}); no access."
                            )
                            embed = discord.Embed(
                                title="No Access",
                                description=f"I don't have access to {log_link}!",
                                color=discord.Color.red(),
                            )
                            await interaction.followup.send(embed=embed)
                        elif e.status == 404:
                            logging.error(f"Channel not found. Error: {e}")
                            self.audit_log(
                                f"{moderator.name} (ID: {moderator.id}) failed to log action; log channel not found for {member.name} (ID: {member.id})."
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
                                f"{moderator.name} (ID: {moderator.id}) encountered rate limit when logging ban for {member.name} (ID: {member.id})."
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
                                f"{moderator.name} (ID: {moderator.id}) encountered Discord API error when logging ban for {member.name} (ID: {member.id}): {e}"
                            )
                            embed = discord.Embed(
                                title="Error",
                                description=f"Failed to log action in {log_link}. Please try later.",
                                color=discord.Color.red(),
                            )
                            await interaction.followup.send(embed=embed)
                        else:
                            logging.error(
                                f"Failed to log ban in '#{logs_channel.name}' (ID: {logs_channel.id}). Error: {e}"
                            )
                            self.audit_log(
                                f"{moderator.name} (ID: {moderator.id}) unknown error when logging ban for {member.name} (ID: {member.id}) in log channel #{logs_channel.name} (ID: {logs_channel.id}): {e}"
                            )
                            embed = discord.Embed(
                                title="Error",
                                description=f"Failed to log action in {log_link}.",
                                color=discord.Color.red(),
                            )
                            await interaction.followup.send(embed=embed)
        except discord.HTTPException as e:
            logging.error(f"Error when attempting to ban: {e}")
            self.audit_log(
                f"{moderator.name} (ID: {moderator.id}) critical error: Failed to ban and send notice to {member.name} (ID: {member.id}): {e}"
            )
            embed = discord.Embed(
                title="Error",
                description=f"Failed to ban and send notice to {member.mention}. Error: {e}",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Ban(bot))
