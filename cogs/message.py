import discord
import logging
from discord import app_commands
from discord.ext import commands


class Message(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"\033[35mMessage\033[0m cog synced successfully.")

    @app_commands.command(
        name="message", description="Sends a custom message in a specified channel."
    )
    async def message(self, interaction: discord.Interaction, channel: discord.TextChannel, *, message: str,):
        # Defer the response to avoid timeout errors
        await interaction.response.defer()

        # Send the custom message in the specified channel
        try:
            await channel.send(message)
            logging.info(f"Custom message successfully sent in '#{channel}'.")
            embed = discord.Embed(
                title="Custom Message Sent",
                description=f"Successfully sent message in #{channel} ",
                color=discord.Color.green(),
            )
            await interaction.followup.send(embed=embed)

        except discord.HTTPException as e:
            if e.status == 403:  # No access to channel
                logging.error(f"No access to #{channel}. Error: {e}")
                embed = discord.Embed(
                    title="Error",
                    description=f"I don't have access to #{channel}!",
                    color=discord.Color.red(),
                )
                await interaction.followup.send(embed=embed)
            elif e.status == 404:  # Channel not found
                logging.error(f"Channel not found. Error: {e}")
                embed = discord.Embed(
                    title="Error",
                    description=f"Channel not found!",
                    color=discord.Color.red(),
                )
                await interaction.followup.send(embed=embed)
            elif e.status == 429:  # Rate limit hit
                logging.error(f"RATE LIMIT. Error: {e}")
                embed = discord.Embed(
                    title="Error",
                    description=f"Too many requests! Please try later.",
                    color=discord.Color.red(),
                )
                await interaction.followup.send(embed=embed)
            elif e.status in {500, 502, 503, 504}:  # Discord API error
                logging.error(f"Discord API Error. Error: {e}")
                embed = discord.Embed(
                    title="Error",
                    description=f"Failed to send custom message in #{channel}. Please try later.",
                    color=discord.Color.red(),
                )
                await interaction.followup.send(embed=embed)
            else:  # Other errors
                logging.error(
                    f"Error when attempting to send custom message in #{channel}. Error: {e}"
                )
                embed = discord.Embed(
                    title="Error",
                    description=f"Failed to send custom message in #{channel}.",
                    color=discord.Color.red(),
                )
                await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Message(bot))
