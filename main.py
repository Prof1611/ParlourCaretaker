import discord
from discord.ext import commands, tasks
import random
import discord.utils
import os
import yaml
import asyncio
import logging


# Define ANSI escape sequences for colours
class CustomFormatter(logging.Formatter):

    LEVEL_COLOURS = {
        logging.DEBUG: "\033[0;36m",  # Cyan
        logging.INFO: "\033[0;32m",  # Green
        logging.WARNING: "\033[0;33m",  # Yellow
        logging.ERROR: "\033[0;31m",  # Red
        logging.CRITICAL: "\033[1;41m",  # Red background w/ bold text
    }
    RESET_COLOUR = "\033[0m"

    def format(self, record):
        level_name = (
            self.LEVEL_COLOURS.get(record.levelno, self.RESET_COLOUR)
            + record.levelname
            + self.RESET_COLOUR
        )
        record.levelname = level_name
        return super().format(record)


# Configure logging
formatter = CustomFormatter(
    "%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
)
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logging.basicConfig(level=logging.INFO, handlers=[handler])

# Load the config file (UTF-8 for emojis, etc.)
with open("config.yaml", "r", encoding="utf-8") as config_file:
    config = yaml.safe_load(config_file)

BOT_TOKEN = os.environ.get("TOKEN", None)
if BOT_TOKEN is None:
    logging.error("Bot token not found in environment variable 'TOKEN'. Please set it!")
    exit(1)

intents = discord.Intents.all()
intents.messages = True
intents.dm_messages = True
intents.guilds = True
intents.members = True

# Initialize the bot
bot = commands.Bot(command_prefix=">", intents=intents)

# Load statuses from the config file
bot_statuses = random.choice(config["statuses"])

dm_forward_channel_id = config["dm_forward_channel_id"]


@tasks.loop(seconds=120)
async def change_bot_status():
    """Changes the bot's 'listening' status every 120 seconds."""
    next_status = random.choice(config["statuses"])
    activity = discord.Activity(type=discord.ActivityType.listening, name=next_status)
    await bot.change_presence(status=discord.Status.online, activity=activity)


@bot.event
async def on_ready():
    logging.info(f"Successfully logged in as \033[35m{bot.user}\033[0m")

    # Start the status rotation if not already running
    if not change_bot_status.is_running():
        change_bot_status.start()

    # Sync slash commands
    try:
        synced_commands = await bot.tree.sync()
        logging.info(f"Successfully synced {len(synced_commands)} commands.")
    except Exception as e:
        logging.error(f"Error syncing application commands: {e}")


@bot.event
async def on_message(message):
    """
    Forwards direct messages to the specified channel in your config.
    Ignores messages from the bot itself.
    """
    if message.author == bot.user:
        return

    # Check if this is a DM
    if isinstance(message.channel, discord.DMChannel):
        # Directly use the stored dm_forward_channel_id
        target_channel = bot.get_channel(
            dm_forward_channel_id
        )  # Use bot.get_channel instead of accessing a guild

        if target_channel:
            try:
                embed = discord.Embed(
                    title=f"Direct Message from '{message.author}'",
                    description=message.content,
                    color=discord.Color.green(),
                )
                await target_channel.send(embed=embed)
                logging.info(
                    f"DM from \033[35m{message.author}\033[0m forwarded to \033[35m#{target_channel.name}\033[0m"
                )
            except discord.HTTPException as e:
                logging.error(f"Error forwarding DM: {e}")
        else:
            logging.error("Target channel not found for DM forwarding.")


# Load all cogs
async def load_cogs():
    """Loads all .py files in the 'cogs' folder as extensions."""
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            await bot.load_extension(f"cogs.{filename[:-3]}")


async def main():
    async with bot:
        await load_cogs()
        await bot.start(BOT_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
