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


class React(commands.Cog):
    """Automatically reacts to introduction messages."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Load config with UTF-8 encoding for emoji support
        with open("config.yaml", "r", encoding="utf-8") as config_file:
            self.config = yaml.safe_load(config_file)
        # Channel where the bot should react to introductions
        self.introductions_channel_id = self.config.get("introductions_channel_id")

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info("\033[96mReact\033[0m cog synced successfully.")
        audit_log("React cog synced successfully.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore messages sent by bots
        if message.author.bot:
            return

        # Ensure the channel matches the configured introductions channel
        if not self.introductions_channel_id:
            return
        if message.channel.id != self.introductions_channel_id:
            return

        # React when message contains the required phrase
        if "🏹Name:" in message.content:
            try:
                await message.add_reaction("👋")
                logging.info(
                    f"Reacted to message {message.id} in #{message.channel.name}"
                )
                audit_log(
                    f"Reacted with 👋 to message {message.id} in channel #{message.channel.name} (ID: {message.channel.id}) in guild '{message.guild.name}' (ID: {message.guild.id})."
                )
            except discord.HTTPException as e:
                logging.error(
                    f"Failed to react to message {message.id} in #{message.channel.name}: {e}"
                )
                audit_log(
                    f"Error reacting to message {message.id} in channel #{message.channel.name} (ID: {message.channel.id}): {e}"
                )


async def setup(bot: commands.Bot):
    await bot.add_cog(React(bot))
