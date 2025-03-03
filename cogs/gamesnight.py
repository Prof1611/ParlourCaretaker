import discord
import logging
import yaml
from discord import app_commands
from discord.ext import commands
import asyncio


class GamesNightModal(discord.ui.Modal, title="Games Night Announcement"):
    message_input = discord.ui.TextInput(
        label="Announcement Message",
        style=discord.TextStyle.long,
        required=True,
        placeholder="Enter your announcement message here...",
    )

    def __init__(self, bot: commands.Bot, games_channel_id: int):
        super().__init__()
        self.bot = bot
        self.games_channel_id = games_channel_id

    async def on_submit(self, interaction: discord.Interaction):
        message_value = self.message_input.value

        # Send a processing embed to acknowledge the modal submission.
        processing_embed = discord.Embed(
            title="Processing Announcement",
            description="Please wait while your announcement is sent...",
            color=discord.Color.orange(),
        )
        await interaction.response.send_message(embed=processing_embed, ephemeral=True)
        original_response = await interaction.original_response()

        # Locate the target channel from the fixed games_channel_id.
        guild = interaction.guild
        target_channel = guild.get_channel(self.games_channel_id)
        if not target_channel:
            embed = discord.Embed(
                title="Error",
                description="Games channel not found!",
                color=discord.Color.red(),
            )
            await interaction.followup.edit_message(
                message_id=original_response.id, content="", embed=embed
            )
            return

        # Attempt to send the announcement with robust error handling.
        try:
            announcement_embed = discord.Embed(
                title="🎲🎮 Games Night Announcement 🎮🎲",
                description=message_value,
                color=discord.Color.blurple(),
            )
            await target_channel.send(embed=announcement_embed)
            logging.info(f"Announcement successfully sent in '#{target_channel.name}'.")
            success_embed = discord.Embed(
                title="Announcement Sent",
                description=f"Successfully sent games night announcement in {target_channel.mention}.",
                color=discord.Color.green(),
            )
            await interaction.followup.edit_message(
                message_id=original_response.id, content="", embed=success_embed
            )
        except discord.HTTPException as e:
            if e.status == 403:
                logging.error(f"No access to '#{target_channel.name}'. Error: {e}")
                embed = discord.Embed(
                    title="No Access",
                    description=f"I don't have access to {target_channel.mention}!",
                    color=discord.Color.red(),
                )
                await interaction.followup.edit_message(
                    message_id=original_response.id, content="", embed=embed
                )
            elif e.status == 404:
                logging.error(f"Channel not found. Error: {e}")
                embed = discord.Embed(
                    title="Error",
                    description="Channel not found!",
                    color=discord.Color.red(),
                )
                await interaction.followup.edit_message(
                    message_id=original_response.id, content="", embed=embed
                )
            elif e.status == 429:
                logging.error(f"RATE LIMIT. Error: {e}")
                embed = discord.Embed(
                    title="Error",
                    description="Too many requests! Please try later.",
                    color=discord.Color.red(),
                )
                await interaction.followup.edit_message(
                    message_id=original_response.id, content="", embed=embed
                )
            elif e.status in {500, 502, 503, 504}:
                logging.error(f"Discord API Error. Error: {e}")
                embed = discord.Embed(
                    title="Error",
                    description=f"Failed to send games night announcement in {target_channel.mention}. Please try later.",
                    color=discord.Color.red(),
                )
                await interaction.followup.edit_message(
                    message_id=original_response.id, content="", embed=embed
                )
            else:
                logging.error(
                    f"Error when attempting to send games night announcement in '#{target_channel.name}'. Error: {e}"
                )
                embed = discord.Embed(
                    title="Error",
                    description=f"Failed to send games night announcement in {target_channel.mention}. Please try again.",
                    color=discord.Color.red(),
                )
                await interaction.followup.edit_message(
                    message_id=original_response.id, content="", embed=embed
                )


class GamesNight(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Load the config file (with UTF-8 encoding for special characters).
        with open("config.yaml", "r", encoding="utf-8") as config_file:
            self.config = yaml.safe_load(config_file)
        self.games_channel_id = self.config["games_channel_id"]

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"\033[35mGamesNight\033[0m cog synced successfully.")

    @app_commands.command(
        name="gamesnight",
        description="Sends a games night announcement in #parlour-games",
    )
    async def gamesnight_command(self, interaction: discord.Interaction):
        modal = GamesNightModal(self.bot, self.games_channel_id)
        await interaction.response.send_modal(modal)


async def setup(bot: commands.Bot):
    await bot.add_cog(GamesNight(bot))
