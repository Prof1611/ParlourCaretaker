import discord
import logging
from discord import app_commands
from discord.ext import commands
import datetime


class Ban(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"\033[35m{__name__}\033[0m synced successfully.")

    @app_commands.command(name="ban", description="Bans a member and sends them a notice via DM.")
    async def ban(self, interaction: discord.Interaction, member: discord.Member, *, reason: str):
        # Defer the response to avoid timeout errors
        await interaction.response.defer()

        # Send the notice to the member via DM
        try:
            if member == 411589337369804801:
                logging.error("Owner (tygafire) entered as victim.")
                embed = discord.Embed(
                    title="Error", description="Nice try, fool.", color=discord.Color.red())
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            elif member == 398205938265358339:
                logging.error("Owner (harry0278) entered as victim.")
                embed = discord.Embed(
                    title="Error", description="Nice try, fool.", color=discord.Color.red())
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            else:
                await member.send(f"""**NOTICE: Permanent Ban from The Parlour Discord Server**

Dear {member.mention},

We are writing to inform you that you have been permanently banned from The Parlour Discord server. This action is a result of your repeated violations of our community rules, despite previous warnings and attempts to rectify the situation.

**Reason for Ban:** {reason}

We take upholding the standards of our community very seriously, and continued disruptive or disrespectful behaviour will not be tolerated. This ban ensures a positive and respectful environment for all members.

**Appeal Process:** If you believe this ban was issued in error, you may appeal it by filling out this form https://forms.gle/n9RirTLaQYfuHG5k8

Sincerely,
The Parlour Moderation Team
""")

                # Ban the user from the server
                await member.ban(reason=reason)
                logging.info(
                    f"Banned '{member.name}' and sent notice via DM.")

                embed = discord.Embed(
                    title="Member Banned", description=f"Sent permanent ban notice to {member.mention} via DM and banned them from the server.", color=discord.Color.green())
                await interaction.followup.send(embed=embed, ephemeral=True)
                # Get the target channel object using its ID
                logs_channel_id = 1237165394649682003
                guild = interaction.guild
                logs_channel = guild.get_channel(logs_channel_id)
                log_link = "https://discord.com/channels/" + \
                    str(interaction.guild.id) + "/" + str(logs_channel_id)

                if logs_channel:
                    try:
                        await logs_channel.send(f"""**Username:** {member.mention}
**User ID:** {member.id}
**Category of Discipline:** Permanent Ban
**Timespan of Discipline:** Permanent
**Reason of Discipline:** {reason}
**Link to Ticket Transcript:** N/A
**Date of Discipline:** {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Moderators Involved:** {interaction.user.mention}""")
                        logging.info(
                            f"Permanent ban logged in #{logs_channel.name}")
                        embed = discord.Embed(
                            title="Action Logged", description=f"Permanent ban successfully logged in {log_link}.", color=discord.Color.green())
                        await interaction.followup.send(embed=embed, ephemeral=True)
                    except Exception as e:
                        logging.error(
                            f"Failed to log ban: {e}")
                        embed = discord.Embed(
                            title="Error", description=f"Failed to log action in {log_link}.", color=discord.Color.red())
                        await interaction.followup.send(embed=embed, ephemeral=True)

        except discord.HTTPException as e:
            logging.error(
                f"Error when attempting to ban: {e}")
            # Handle cases where the message cannot be sent (e.g., DM disabled) or ban fails
            embed = discord.Embed(
                title="Error", description=f"Failed to send notice or ban {member.mention}. Error: {e}", color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Ban(bot))
