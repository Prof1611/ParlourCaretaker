import discord
import logging
from discord.ext import commands
import asyncio
import datetime


STICKER_ID = 1364364888171872256  # Sticker ID for "Godzilla" sticker


def audit_log(message: str):
    """Append a timestamped message to the audit log file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("audit.log", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


class GodzillaSticker(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore messages from bots or DMs
        if message.author.bot or message.guild is None:
            return

        # Check if the message contains "godzilla" (case-insensitive)
        if "godzilla" in message.content.lower():
            try:
                # Attempt to send the sticker in the same channel
                await message.channel.send(sticker=discord.Object(STICKER_ID))
                audit_log(
                    f"Sent Godzilla sticker in #{message.channel.name} (ID: {message.channel.id}) "
                    f"after message by {message.author} (ID: {message.author.id})."
                )
                logging.info(
                    f"Godzilla sticker sent in #{message.channel.name} (Guild: {message.guild.name})."
                )
            except discord.Forbidden as e:
                error_msg = f"Failed to send Godzilla sticker: Missing permissions in #{message.channel.name} (ID: {message.channel.id})."
                logging.error(error_msg + f" Error: {e}")
                audit_log(error_msg)
            except discord.HTTPException as e:
                if e.status == 429:
                    error_msg = f"Failed to send Godzilla sticker: Rate limited in #{message.channel.name} (ID: {message.channel.id})."
                    logging.error(error_msg + f" Error: {e}")
                    audit_log(error_msg)
                else:
                    error_msg = f"HTTPException sending Godzilla sticker in #{message.channel.name} (ID: {message.channel.id}): {e}"
                    logging.error(error_msg)
                    audit_log(error_msg)
            except Exception as e:
                error_msg = f"Unexpected error sending Godzilla sticker in #{message.channel.name} (ID: {message.channel.id}): {e}"
                logging.error(error_msg)
                audit_log(error_msg)

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info("\033[96mGodzillaSticker\033[0m cog synced successfully.")
        audit_log("GodzillaSticker cog synced successfully.")


async def setup(bot: commands.Bot):
    await bot.add_cog(GodzillaSticker(bot))
