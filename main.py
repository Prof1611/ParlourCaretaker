import discord
from discord.ext import commands, tasks
from itertools import cycle
import discord.utils
import os
import yaml
import asyncio
import logging


# Define ANSI escape sequences for colours
class CustomFormatter(logging.Formatter):

    LEVEL_COLOURS = {  # Define colours for different log levels
        logging.DEBUG: "\033[0;36m",   # Cyan
        logging.INFO: "\033[0;32m",    # Green
        logging.WARNING: "\033[0;33m",  # Yellow
        logging.ERROR: "\033[0;31m",   # Red
        logging.CRITICAL: "\033[1;41m",  # Red background with bold text
    }
    RESET_COLOUR = "\033[0m"  # Reset to default colour

    def format(self, record):
        # Apply the colour based on the log level
        level_name = self.LEVEL_COLOURS.get(
            record.levelno, self.RESET_COLOUR) + record.levelname + self.RESET_COLOUR
        record.levelname = level_name
        return super().format(record)


# Configure logging
formatter = CustomFormatter(
    '%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logging.basicConfig(level=logging.INFO, handlers=[handler])


# Load the config file with UTF-8 encoding to handle special characters like emojis
with open("config.yaml", 'r', encoding='utf-8') as config_file:
    config = yaml.safe_load(config_file)


BOT_TOKEN = os.environ.get("TOKEN", None)  # Set a default value if not found

if BOT_TOKEN is None:  # Check if bot token is set correctly from environment variable
    logging.error(
        "Bot token environment variable not found when searching with name 'TOKEN'. Please set it!")
    exit(1)

intents = discord.Intents.all()  # Set bot intents
intents.messages = True
intents.dm_messages = True
intents.guilds = True
intents.members = True

# Initialize the bot with a custom prefix
bot = commands.Bot(command_prefix=">", intents=intents)

# Load statuses from the config file
bot_statuses = cycle(config['statuses'])

dm_forward_channel_id = config["dm_forward_channel_id"]
guild_id = config["guild_id"]


@tasks.loop(seconds=120)
async def change_bot_status():
    next_status = next(bot_statuses)  # Get the next status in the cycle
    activity = discord.Activity(
        type=discord.ActivityType.listening,  # Set activity type to listening
        name=next_status  # Set the name to the next status
    )
    # Change the bot's presence
    await bot.change_presence(status=discord.Status.online, activity=activity)


@ bot.event
async def on_ready():
    logging.info(f"Sucessfully logged in as \033[35m{bot.user}\033[0m")
    # readyActivity = discord.CustomActivity(name="Ready!")  # Set as CustomActivity
    # await bot.change_presence(status=discord.Status.idle, activity=readyActivity)
    # await asyncio.sleep(5)
    change_bot_status.start()
    try:
        synced_commands = await bot.tree.sync()  # Sync all bot commands
        logging.info(f"Successfully synced {len (synced_commands)} commands.")
    except Exception as e:
        logging.error(
            f"An error with syncing application commands has occured: {e}")


async def load():  # Load command cogs from 'cogs' folder
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            await bot.load_extension(f"cogs.{filename[:-3]}")


@ bot.event
# Forwards direct messages to The Parlour
async def on_message(message):
    if message.author == bot.user:  # Ignore messages from the bot itself to prevent loops
        return

    if isinstance(message.channel, discord.DMChannel):
        guild = bot.get_guild(guild_id)
        if guild:
            target_channel = guild.get_channel(
                dm_forward_channel_id)  # Get specified channel from ID
            if target_channel:
                try:
                    embedded_msg = discord.Embed(
                        title=f"Direct Message from '{message.author}'", description=f"{message.content}", color=discord.Color.green())  # Set embed content
                    # Forward the DM to the specified channel
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
