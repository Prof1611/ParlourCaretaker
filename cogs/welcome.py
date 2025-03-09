import discord
import logging
import yaml
from discord.ext import commands
import datetime


def audit_log(message: str):
    """Append a timestamped message to the audit log file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("audit.log", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Load the config file (UTF-8 for special characters)
        with open("config.yaml", "r", encoding="utf-8") as config_file:
            self.config = yaml.safe_load(config_file)
        # Get the welcome channel ID and check if welcome messages are enabled.
        self.welcome_channel_id = self.config.get("welcome_channel_id")
        self.welcome_enabled = self.config.get("welcome_enabled", True)
        # Set the local welcome image path
        self.welcome_image_path = "welcome-image.jpg"

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"\033[96mWelcome\033[0m cog synced successfully.")
        audit_log("Welcome cog synced successfully.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # Check if welcome messages are enabled.
        if not self.welcome_enabled:
            logging.info("Welcome messages are disabled in config.")
            audit_log(
                f"Welcome messages disabled in guild '{member.guild.name}' (ID: {member.guild.id}). Skipping welcome for {member.name} (ID: {member.id})."
            )
            return

        guild = member.guild
        channel = guild.get_channel(self.welcome_channel_id)
        if not channel:
            logging.error(
                f"Welcome channel with ID '{self.welcome_channel_id}' not found in guild '{guild.name}'."
            )
            audit_log(
                f"Error: Welcome channel with ID '{self.welcome_channel_id}' not found in guild '{guild.name}' (ID: {guild.id})."
            )
            return

        embed = discord.Embed(
            title="Welcome to The Parlour",
            description=(
                f"Welcome {member.mention}! Retire with us to the parlour for after dinner games in celebrations of our hosts, The Last Dinner Party.\n\n"
                "Make sure to check out <#1346179590795559047> for our server info 🏹"
            ),
            color=discord.Color.dark_red(),
        )
        embed.set_image(url="attachment://welcome-image.jpg")

        try:
            await channel.send(
                embed=embed,
                file=discord.File(
                    self.welcome_image_path, filename="welcome-image.jpg"
                ),
            )
            logging.info(
                f"Welcome embed sent for '{member.name}' in channel #{channel.name}."
            )
            audit_log(
                f"Sent welcome message for {member.name} (ID: {member.id}) in channel #{channel.name} (ID: {channel.id}) in guild '{guild.name}' (ID: {guild.id})."
            )
        except discord.HTTPException as e:
            logging.error(
                f"Error sending welcome embed in channel #{channel.name} (ID: {channel.id}): {e}"
            )
            audit_log(
                f"Failed to send welcome message for {member.name} (ID: {member.id}) in channel #{channel.name} (ID: {channel.id}) in guild '{guild.name}' (ID: {guild.id}). Error: {e}"
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
