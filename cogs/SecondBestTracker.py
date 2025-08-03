import discord
import logging
from discord.ext import commands
from discord import app_commands
import datetime
import sqlite3
import unicodedata

DATABASE_PATH = "database.db"


def audit_log(message: str):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("audit.log", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


UNICODE_REPLACE = {
    "àáâãäåāąă": "a",
    "çćčĉċ": "c",
    "ďđð": "d",
    "èéêëēęěĕė": "e",
    "ƒ": "f",
    "ğĝġģ": "g",
    "ĥħ": "h",
    "ìíîïīĩĭįı": "i",
    "ĳ": "ij",
    "ĵ": "j",
    "ķĸ": "k",
    "łľĺļŀ": "l",
    "ñńňņŉŋ": "n",
    "òóôõöøōőŏ": "o",
    "œ": "oe",
    "ŕřŗ": "r",
    "śšşŝș": "s",
    "ťţŧț": "t",
    "ùúûüūůűŭũų": "u",
    "ŵ": "w",
    "ýÿŷ": "y",
    "žżź": "z",
    "ß": "ss",
    "æ": "ae",
    "ø": "o",
    "ğ": "g",
    "ł": "l",
    "ı": "i",
    "ś": "s",
    "ż": "z",
    "ð": "d",
    "þ": "th",
    "ç": "c",
    "ş": "s",
    "ğ": "g",
    "å": "a",
    "Ö": "O",
    "Ü": "U",
    "Ä": "A",
    "ẞ": "SS",
    "ａ": "a",
    "ｂ": "b",
    "ｃ": "c",
    "ｄ": "d",
    "ｅ": "e",
    "ｆ": "f",
    "ｇ": "g",
    "ｈ": "h",
    "ｉ": "i",
    "ｊ": "j",
    "ｋ": "k",
    "ｌ": "l",
    "ｍ": "m",
    "ｎ": "n",
    "ｏ": "o",
    "ｐ": "p",
    "ｑ": "q",
    "ｒ": "r",
    "ｓ": "s",
    "ｔ": "t",
    "ｕ": "u",
    "ｖ": "v",
    "ｗ": "w",
    "ｘ": "x",
    "ｙ": "y",
    "ｚ": "z",
    "Ａ": "a",
    "Ｂ": "b",
    "Ｃ": "c",
    "Ｄ": "d",
    "Ｅ": "e",
    "Ｆ": "f",
    "Ｇ": "g",
    "Ｈ": "h",
    "Ｉ": "i",
    "Ｊ": "j",
    "Ｋ": "k",
    "Ｌ": "l",
    "Ｍ": "m",
    "Ｎ": "n",
    "Ｏ": "o",
    "Ｐ": "p",
    "Ｑ": "q",
    "Ｒ": "r",
    "Ｓ": "s",
    "Ｔ": "t",
    "Ｕ": "u",
    "Ｖ": "v",
    "Ｗ": "w",
    "Ｘ": "x",
    "Ｙ": "y",
    "Ｚ": "z",
    "ɢ": "g",
    "ᴏ": "o",
    "ᴅ": "d",
    "ᴢ": "z",
    "ɪ": "i",
    "ʟ": "l",
    "ʏ": "y",
    "ᴬ": "a",
    "ᴮ": "b",
    "ᴰ": "d",
    "ᴱ": "e",
    "ᴳ": "g",
    "ᴴ": "h",
    "ᴵ": "i",
    "ᴶ": "j",
    "ᴷ": "k",
    "ᴸ": "l",
    "ᴹ": "m",
    "ᴺ": "n",
    "ᴼ": "o",
    "ᴾ": "p",
    "ᴿ": "r",
    "ᵀ": "t",
    "ᵁ": "u",
    "ⱽ": "v",
    "ᵂ": "w",
}


def normalise_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    table = {}
    for srcs, tgt in UNICODE_REPLACE.items():
        for c in srcs:
            table[ord(c)] = tgt
    return text.translate(table).lower()


def contains_second_best(text: str) -> bool:
    norm = normalise_text(text)
    import re

    return re.search(r"\b[sz]econd be[sz]t\b", norm) is not None


def ensure_sb_db_tables():
    with sqlite3.connect(DATABASE_PATH) as conn:
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS second_best_user_count (
                user_id INTEGER PRIMARY KEY,
                count INTEGER NOT NULL
            )
        """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS second_best_channel_count (
                channel_id INTEGER PRIMARY KEY,
                count INTEGER NOT NULL
            )
        """
        )
        conn.commit()


def increment_sb_stat(table: str, id_value: int):
    key = "user_id" if table.endswith("_user_count") else "channel_id"
    with sqlite3.connect(DATABASE_PATH) as conn:
        c = conn.cursor()
        c.execute(
            f"INSERT INTO {table} ({key}, count) VALUES (?, 1) "
            f"ON CONFLICT({key}) DO UPDATE SET count = count + 1",
            (id_value,),
        )
        conn.commit()


def get_top_sb_users(limit=5):
    with sqlite3.connect(DATABASE_PATH) as conn:
        c = conn.cursor()
        c.execute(
            "SELECT user_id, count FROM second_best_user_count ORDER BY count DESC LIMIT ?",
            (limit,),
        )
        return c.fetchall()


def get_top_sb_channels(limit=5):
    with sqlite3.connect(DATABASE_PATH) as conn:
        c = conn.cursor()
        c.execute(
            "SELECT channel_id, count FROM second_best_channel_count ORDER BY count DESC LIMIT ?",
            (limit,),
        )
        return c.fetchall()


class SecondBestTracker(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        ensure_sb_db_tables()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        if contains_second_best(message.content):
            increment_sb_stat("second_best_user_count", message.author.id)
            increment_sb_stat("second_best_channel_count", message.channel.id)
            audit_log(
                f"Recorded 'second best' in #{message.channel.name} "
                f"(ID: {message.channel.id}) by {message.author} "
                f"(ID: {message.author.id})."
            )

    @app_commands.command(
        name="secondbest_stats",
        description="Show Second Best trigger leaderboard (top users and channels)",
    )
    async def secondbest_stats(self, interaction: discord.Interaction):
        top_users = get_top_sb_users(5)
        top_channels = get_top_sb_channels(5)

        user_lines = []
        for user_id, count in top_users:
            member = interaction.guild.get_member(user_id)
            name = member.display_name if member else f"User {user_id}"
            user_lines.append(f"**{name}**: {count}")

        channel_lines = []
        for channel_id, count in top_channels:
            channel = interaction.guild.get_channel(channel_id)
            mention = channel.mention if channel else f"Channel {channel_id}"
            channel_lines.append(f"{mention}: {count}")

        embed = discord.Embed(
            title="Second Best Leaderboard",
            colour=discord.Colour.green(),
            timestamp=datetime.datetime.now(),
        )
        embed.add_field(
            name="Top Users",
            value="\n".join(user_lines) if user_lines else "No triggers yet.",
            inline=False,
        )
        embed.add_field(
            name="Top Channels",
            value="\n".join(channel_lines) if channel_lines else "No triggers yet.",
            inline=False,
        )

        # send non-ephemeral so everyone can see the leaderboard
        await interaction.response.send_message(embed=embed)
        audit_log(
            f"{interaction.user.name} (ID: {interaction.user.id}) used "
            f"/secondbest_stats in #{interaction.channel.name} "
            f"(ID: {interaction.channel.id})."
        )

    @app_commands.command(
        name="secondbest_rescan",
        description="Scan entire server history for 'second best' occurrences",
    )
    async def secondbest_rescan(self, interaction: discord.Interaction):
        # log start of rescan
        logging.info(
            f"User {interaction.user} (ID: {interaction.user.id}) initiated full rescan."
        )
        audit_log(
            f"{interaction.user.name} (ID: {interaction.user.id}) started full history rescan."
        )

        await interaction.response.defer(thinking=True)

        # clear existing stats
        with sqlite3.connect(DATABASE_PATH) as conn:
            c = conn.cursor()
            c.execute("DELETE FROM second_best_user_count")
            c.execute("DELETE FROM second_best_channel_count")
            conn.commit()
        logging.info("Cleared existing second_best stats tables.")
        audit_log("Cleared existing second_best stats tables before rescan.")

        total_count = 0
        for channel in interaction.guild.text_channels:
            logging.info(f"Scanning channel #{channel.name} (ID: {channel.id})...")
            audit_log(
                f"Scanning channel #{channel.name} (ID: {channel.id}) for 'second best'."
            )
            channel_count = 0

            try:
                async for msg in channel.history(limit=None, oldest_first=True):
                    if msg.author.bot:
                        continue
                    if contains_second_best(msg.content):
                        increment_sb_stat("second_best_user_count", msg.author.id)
                        increment_sb_stat("second_best_channel_count", channel.id)
                        channel_count += 1
                        total_count += 1
                logging.info(f"Found {channel_count} matches in #{channel.name}.")
                audit_log(
                    f"Found {channel_count} occurrences in channel #{channel.name}."
                )
            except (discord.Forbidden, discord.HTTPException) as e:
                logging.warning(
                    f"Could not scan channel #{channel.name} (ID: {channel.id}): {e}"
                )
                audit_log(
                    f"Failed to scan channel #{channel.name} (ID: {channel.id}): {e}"
                )
                continue

        # final report
        await interaction.followup.send(
            f"Full history scan completed. Found {total_count} occurrences of 'second best'."
        )
        logging.info(f"Rescan complete: {total_count} total matches found.")
        audit_log(f"Completed full history rescan. Total occurrences: {total_count}.")

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info("\033[96mSecondBestTracker\033[0m cog synced successfully.")
        audit_log("SecondBestTracker cog synced successfully.")


async def setup(bot: commands.Bot):
    await bot.add_cog(SecondBestTracker(bot))
