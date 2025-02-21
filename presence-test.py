import discord
from discord.ext import commands, tasks
from itertools import cycle
import discord.utils
import os
import yaml
import asyncio
import logging
from pypresence import Presence
import time


# Define ANSI escape sequences for colours
class CustomFormatter(logging.Formatter):
    LEVEL_COLOURS = {  # Define colours for different log levels
        logging.DEBUG: "\033[0;36m",   # Cyan
        logging.INFO: "\033[0;32m",    # Green
        logging.WARNING: "\033[0;33m",  # Yellow
        logging.ERROR: "\033[0;31m",    # Red
        logging.CRITICAL: "\033[1;41m",  # Red background with bold text
    }
    RESET_COLOUR = "\033[0m"  # Reset to default colour

    def format(self, record):
        level_name = self.LEVEL_COLOURS.get(
            record.levelno, self.RESET_COLOUR) + record.levelname + self.RESET_COLOUR
        record.levelname = level_name
        return super().format(record)


# Configure logging
formatter = CustomFormatter('%(asctime)s - %(levelname)s - %(message)s')
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logging.basicConfig(level=logging.INFO, handlers=[handler])

# Load the config file with UTF-8 encoding
with open("config.yaml", 'r', encoding='utf-8') as config_file:
    config = yaml.safe_load(config_file)

BOT_TOKEN = os.environ.get("TOKEN", None)

if BOT_TOKEN is None:
    logging.error(
        "Bot token environment variable not found when searching with name 'TOKEN'. Please set it!")
    exit(1)

client_id = "1226910011847086162"
intents = discord.Intents.all()
# Use the same event loop as the bot for pypresence
RPC = Presence(client_id, loop=asyncio.get_event_loop())
RPC.connect()

# Initialize the bot with a custom prefix
bot = commands.Bot(command_prefix=">", intents=intents)

# Load statuses from the config file
bot_statuses = cycle(config['statuses'])
dm_forward_channel_id = config["dm_forward_channel_id"]
guild_id = config["guild_id"]


@tasks.loop(seconds=20)
async def change_bot_status():
    next_status = next(bot_statuses)  # Get the next status in the cycle
    start = int(time.time())

    try:
        RPC.update(
            large_image="pte-cover",
            large_text="Listening to",
            details=f"{next_status}",
            state="test state",
            start=start,
            buttons=[
                {"label": "TLDP", "url": "https://www.thelastdinnerparty.co.uk/"}]
        )

        logging.info(f"Updated Rich Presence to: {next_status}")
    except Exception as e:
        logging.error(f"Error updating Rich Presence: {e}")


@ bot.event
async def on_ready():
    logging.info(f"Successfully logged in as \033[35m{bot.user}\033[0m")
    await asyncio.sleep(1)  # Wait a bit before starting status updates
    change_bot_status.start()
    try:
        synced_commands = await bot.tree.sync()  # Sync all bot commands
        logging.info(f"Successfully synced {len(synced_commands)} commands.")
    except Exception as e:
        logging.error(
            f"An error with syncing application commands has occurred: {e}")


async def load():  # Load command cogs from 'cogs' folder
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            await bot.load_extension(f"cogs.{filename[:-3]}")


@ bot.event
async def on_message(message):
    if message.author == bot.user:  # Ignore messages from the bot itself
        return

    if isinstance(message.channel, discord.DMChannel):
        guild = bot.get_guild(guild_id)
        if guild:
            target_channel = guild.get_channel(dm_forward_channel_id)
            if target_channel:
                try:
                    embedded_msg = discord.Embed(
                        title=f"Direct Message from '{message.author}'",
                        description=f"{message.content}",
                        color=discord.Color.green()
                    )
                    await target_channel.send(embed=embedded_msg)
                    logging.info(
                        f"Direct Message from \033[35m{message.author}\033[0m successfully forwarded to \033[35m#{target_channel.name}\033[0m")
                except discord.HTTPException as e:
                    logging.error(f"Error forwarding direct Message: {e}")
            else:
                logging.error(
                    "Target channel not found in the specified guild when attempting to forward Direct Message.")
        else:
            logging.error(
                "Guild not found when attempting to forward Direct Message.")


async def main():  # Start bot
    async with bot:
        await load()
        await bot.start(BOT_TOKEN)

asyncio.run(main())
