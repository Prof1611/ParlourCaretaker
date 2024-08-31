import discord
from discord.ext import commands
import discord.utils
import os
from os import environ
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


BOT_TOKEN = os.environ.get("TOKEN", None)  # Set a default value if not found

if BOT_TOKEN is None:
    print("\033[32m[BOT]\033[0m \033[91m[ERROR]\033[0m Discord bot 'TOKEN' environment variable not found. Please set it!")
    exit(1)

intents = discord.Intents.all()
intents.dm_messages = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix=">", intents=intents)

dm_forward_channel_id = 1237165394649682003
guild_id = 1161423690517463161


@bot.event
async def on_ready():
    logging.info(f"Sucessfully logged in as \033[35m{bot.user}\033[0m")
    try:
        synced_commands = await bot.tree.sync()
        logging.info(f"Successfully synced {len (synced_commands)} commands.")
    except Exception as e:
        logging.error(
            f"An error with syncing application commands has occured: {e}")


async def load():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            await bot.load_extension(f"cogs.{filename[:-3]}")


@bot.event
# Forwards direct messages to The Parlour
async def on_message(message):
    if message.author == bot.user:
        return

    if isinstance(message.channel, discord.DMChannel):
        guild = bot.get_guild(guild_id)
        if guild:
            target_channel = guild.get_channel(dm_forward_channel_id)
            if target_channel:
                try:
                    # Get the user's avatar as an Asset object
                    user_avatar = message.author.avatar
                    if user_avatar:
                        # Construct the avatar URL dynamically using the user ID and hash
                        avatar_url = f"https://cdn.discordapp.com/avatars/{message.author.id}/{user_avatar.url}"
                        embedded_msg = discord.Embed(
                            title=f"Direct Message from '{message.author}'", description=f"{message.content}", color=discord.Color.green())
                        embedded_msg.set_thumbnail(url=avatar_url)
                        await target_channel.send(embed=embedded_msg)
                    else:
                        embedded_msg = discord.Embed(
                            title=f"Direct Message from '{message.author}'", description=f"{message.content}", color=discord.Color.green())
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


async def main():
    async with bot:
        await load()
        await bot.start(BOT_TOKEN)

asyncio.run(main())
