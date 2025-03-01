import discord
import logging
import yaml
from discord import app_commands
from discord.ext import commands


class GamesNight(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Load the config file with UTF-8 encoding to handle special characters like emojis
        with open("config.yaml", 'r', encoding='utf-8') as config_file:
            self.config = yaml.safe_load(config_file)

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"\033[35mGamesnight\033[0m cog synced successfully.")

    @app_commands.command(name="gamesnight", description="Sends a games night announcement in #parlour-games")
    async def message(self, interaction: discord.Interaction, *, message: str):
        # Defer the response to avoid timeout errors
        await interaction.response.defer()

        # Pull the games night channel from the config
        guild = interaction.guild
        games_channel_id = self.config["games_channel_id"]
        games_channel = guild.get_channel(games_channel_id)

        # Try send the announcement
        try:
            embed = discord.Embed(
                title="🎲🎮 Games Night Announcement 🎮🎲", description=f"{message}", color=discord.Color.blurple())
            await games_channel.send(embed=embed)
            logging.info(
                f"Announcement successfully sent in '#{games_channel.name}'.")
            embed = discord.Embed(
                title="Announcement Sent", description=f"Successfully sent games night announcement in #{games_channel.name}", color=discord.Color.green())
            await interaction.followup.send(embed=embed)

        except discord.HTTPException as e:
            if e.status == 403:  # No access to games_channel
                logging.error(
                    f"No access to '#{games_channel.name}'. Error: {e}")
                embed = discord.Embed(
                    title="No Access", description=f"I don't have access to #{games_channel.name}!", color=discord.Color.red())
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
                    title="Error", description=f"Failed to send games night announcement in '#{games_channel.name}'. Please try later.", color=discord.Color.red())
                await interaction.followup.send(embed=embed)
            else:  # Other errors
                logging.error(
                    f"Error when attempting to send games night announcement in '#{games_channel.name}'. Error: {e}")
                embed = discord.Embed(
                    title="Error", description=f"Failed to send games night announcement in #{games_channel.name}. Please try again.", color=discord.Color.red())
                await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(GamesNight(bot))
