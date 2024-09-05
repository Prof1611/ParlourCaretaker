import discord
import logging
import yaml
import datetime
from discord import app_commands
from discord.ext import commands


class Kick(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Load the configuration file when the instance is created
        with open('config.yaml', 'r') as config_file:
            self.config = yaml.safe_load(config_file)

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"\033[35m{__name__}\033[0m synced successfully.")

    @app_commands.command(name="kick", description="Kicks a member and sends them a notice via DM.")
    async def kick(self, interaction: discord.Interaction, member: discord.Member, *, reason: str):
        # Defer the response to avoid timeout errors
        await interaction.response.defer()

        # Send the notice to the member via DM
        try:
            if member.id in self.config["owner_ids"]:
                logging.error("Owner entered as victim.")
                embed = discord.Embed(
                    title="Error", description="Nice try, fool.", color=discord.Color.red())
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            else:
                try:
                    await member.send(f"""**NOTICE: Kick from The Parlour Discord Server**

Dear {member.mention},

We are writing to inform you that you have been kicked from The Parlour Discord server. This action is a result of your violations of our community rules.

**Reason for Kick:** {reason}

We take upholding the standards of our community very seriously, and continued disruptive or disrespectful behaviour will not be tolerated.
You are welcome to rejoin the server provided you review our community rules to ensure you do not break them again.

Sincerely,
The Parlour Moderation Team
""")
                    logging.info(
                        f"Successfully sent kick notice to '{member.name}' via DM.")
                except discord.HTTPException as e:
                    if e.status == 403:  # DMs Disabled
                        logging.error(
                            f"DMs disabled when attempting to send kick notice via DM. Error: {e}")
                        embed = discord.Embed(
                            title="Error", description=f"That user has their DMs disabled. Failed to send notice.", color=discord.Color.red())
                        await interaction.followup.send(embed=embed)
                    else:
                        logging.error(
                            f"Error when attempting to send kick notice via DM: {e}")
                        embed = discord.Embed(
                            title="Error", description=f"Failed to send kick notice to {member.mention} via DM.", color=discord.Color.red())
                        await interaction.followup.send(embed=embed)
                try:
                    # Try kick the user from the server
                    await member.kick(reason=reason)
                    guild = interaction.guild
                    logging.info(
                        f"Kicked '{member.name}'from {guild.name}.")

                    embed = discord.Embed(
                        title="Member Kicked", description=f"Kicked {member.mention} from the server and sent them a notice to via DM.", color=discord.Color.green())
                    await interaction.followup.send(embed=embed)
                except discord.HTTPException as e:
                    if e.status == 403:  # Bot has no permission to kick
                        logging.error(
                            f"No permission to kick. Error: {e}")
                        embed = discord.Embed(
                            title="Error", description=f"I don't have permission to kick members!", color=discord.Color.red())
                        await interaction.followup.send(embed=embed)
                    else:
                        logging.error(
                            f"Error when attempting to kick {member.name} from {guild.name}. Error: {e}")
                        embed = discord.Embed(
                            title="Error", description=f"Failed to kick {member.mention}.", color=discord.Color.red())
                        await interaction.followup.send(embed=embed)

                # Get the target channel object using its ID
                logs_channel_id = self.config["logs_channel_id"]
                logs_channel = guild.get_channel(logs_channel_id)
                log_link = "https://discord.com/channels/" + \
                    str(interaction.guild.id) + "/" + str(logs_channel_id)

                if logs_channel:
                    try:
                        await logs_channel.send(f"""**Username:** {member.mention}
**User ID:** {member.id}
**Category of Discipline:** Kick
**Timespan of Discipline:** N/A
**Reason of Discipline:** {reason}
**Link to Ticket Transcript:** N/A
**Date of Discipline:** {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Moderators Involved:** {interaction.user.mention}""")
                        logging.info(
                            f"Kick logged in #{logs_channel.name}.")
                        embed = discord.Embed(
                            title="Action Logged", description=f"Kick successfully logged in {log_link}.", color=discord.Color.green())
                        await interaction.followup.send(embed=embed, ephemeral=True)
                    except discord.HTTPException as e:
                        if e.status == 403:  # No access to channel
                            logging.error(
                                f"No access to #{logs_channel.name}. Error: {e}")
                            embed = discord.Embed(
                                title="Error", description=f"I don't have access to {log_link}!", color=discord.Color.red())
                            await interaction.followup.send(embed=embed)
                        elif e.status == 404:  # Channel not found
                            logging.error(
                                f"Channel not found. Error: {e}")
                            embed = discord.Embed(
                                title="Error", description=f"Channel not found!", color=discord.Color.red())
                            await interaction.followup.send(embed=embed)
                        elif e.status == 429:  # Rate limit hit
                            logging.error(
                                f"RATE LIMIT. Error: {e}")
                            embed = discord.Embed(
                                title="Error", description=f"Too many requests! Please try later.", color=discord.Color.red())
                            await interaction.followup.send(embed=embed)
                        elif e.status == 500 or 502 or 503 or 504:  # Discord API error
                            logging.error(
                                f"Discord API Error. Error: {e}")
                            embed = discord.Embed(
                                title="Error", description=f"Failed to log action in {log_link}. Please try later.", color=discord.Color.red())
                            await interaction.followup.send(embed=embed)
                        else:  # Other errors
                            logging.error(
                                f"Failed to log kick in {log_link}. Error: {e}")
                            embed = discord.Embed(
                                title="Error", description=f"Failed to log action in {log_link}.", color=discord.Color.red())
                            await interaction.followup.send(embed=embed)
        except discord.HTTPException as e:
            logging.error(
                f"Error when attempting to kick: {e}")
            embed = discord.Embed(
                title="Error", description=f"Failed to send notice or kick {member.mention}.", color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Kick(bot))
