import discord
import logging
import yaml
from discord.ext import commands


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
        self.welcome_image_path = "welcome_image.jpeg"

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"\033[96mWelcome\033[0m cog synced successfully.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # Check if welcome messages are enabled.
        if not self.welcome_enabled:
            logging.info("Welcome messages are disabled in config.")
            return

        guild = member.guild
        channel = guild.get_channel(self.welcome_channel_id)
        if not channel:
            logging.error(
                f"Welcome channel with ID '{self.welcome_channel_id}' not found in guild '{guild.name}'."
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
        embed.set_image(url="attachment://welcome_image.jpeg")

        try:
            await channel.send(
                embed=embed,
                file=discord.File(
                    self.welcome_image_path, filename="welcome_image.jpeg"
                ),
            )
            logging.info(
                f"Welcome embed sent for '@{member.name}' in '#{channel.name}'."
            )
        except discord.HTTPException as e:
            logging.error(f"Error sending welcome embed in '#{channel.name}': {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
