import discord
import logging
from discord.ext import commands
from discord import app_commands
import datetime
import sqlite3
import unicodedata
import time

STICKER_ID = 1364364888171872256
COOLDOWN_SECONDS = 15
DATABASE_PATH = "database.db"


def audit_log(message: str):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("audit.log", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


def ensure_db_tables():
    with sqlite3.connect(DATABASE_PATH) as conn:
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS godzilla_user_count (
                user_id INTEGER PRIMARY KEY,
                count INTEGER NOT NULL
            )
        """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS godzilla_channel_count (
                channel_id INTEGER PRIMARY KEY,
                count INTEGER NOT NULL
            )
        """
        )
        conn.commit()


def increment_stat(table: str, id_value: int):
    with sqlite3.connect(DATABASE_PATH) as conn:
        c = conn.cursor()
        c.execute(
            f"INSERT INTO {table} VALUES (?, 1) ON CONFLICT({table.split('_')[1]}_id) DO UPDATE SET count = count + 1",
            (id_value,),
        )
        conn.commit()


def get_top_users(limit=5):
    with sqlite3.connect(DATABASE_PATH) as conn:
        c = conn.cursor()
        c.execute(
            "SELECT user_id, count FROM godzilla_user_count ORDER BY count DESC LIMIT ?",
            (limit,),
        )
        return c.fetchall()


def get_top_channels(limit=5):
    with sqlite3.connect(DATABASE_PATH) as conn:
        c = conn.cursor()
        c.execute(
            "SELECT channel_id, count FROM godzilla_channel_count ORDER BY count DESC LIMIT ?",
            (limit,),
        )
        return c.fetchall()


# Mapping for common accented/leet Unicode letters to ASCII
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
    return text.translate(table).lower().replace(" ", "")


def contains_godzilla(text: str) -> bool:
    return "godzilla" in normalise_text(text)


class GodzillaSticker(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cooldowns = {}
        ensure_db_tables()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        if not contains_godzilla(message.content):
            return

        now = time.time()
        last = self.cooldowns.get(message.author.id, 0)
        if now - last < COOLDOWN_SECONDS:
            return

        self.cooldowns[message.author.id] = now

        try:
            await message.channel.send(
                stickers=[discord.Object(STICKER_ID)],
                reference=message,
                mention_author=False,
            )
            increment_stat("godzilla_user_count", message.author.id)
            increment_stat("godzilla_channel_count", message.channel.id)
            audit_log(
                f"Sent Godzilla sticker in #{message.channel.name} for user {message.author}."
            )
            logging.info(
                f"Godzilla sticker sent for {message.author} in #{message.channel.name}."
            )
        except discord.Forbidden as e:
            logging.error(f"Missing permissions to send sticker: {e}")
            audit_log(f"Failed to send sticker in #{message.channel.name}: {e}")
        except discord.HTTPException as e:
            logging.error(f"HTTP error sending sticker: {e}")
            audit_log(f"HTTPException in #{message.channel.name}: {e}")

    @app_commands.command(
        name="godzilla_stats",
        description="Show Godzilla sticker trigger leaderboard (top users and channels)",
    )
    async def godzilla_stats(self, interaction: discord.Interaction):
        top_users = get_top_users(5)
        top_channels = get_top_channels(5)

        user_lines = []
        for user_id, count in top_users:
            member = interaction.guild.get_member(user_id)
            name = member.display_name if member else f"User {user_id}"
            user_lines.append(f"**{name}**: {count}")

        channel_lines = []
        for channel_id, count in top_channels:
            channel = interaction.guild.get_channel(channel_id)
            name = channel.mention if channel else f"Channel {channel_id}"
            channel_lines.append(f"{name}: {count}")

        embed = discord.Embed(
            title="Godzilla Sticker Leaderboard",
            colour=discord.Colour.blurple(),
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

        await interaction.response.send_message(embed=embed)

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info("GodzillaSticker cog synced successfully.")
        audit_log("GodzillaSticker cog synced successfully.")


async def setup(bot: commands.Bot):
    await bot.add_cog(GodzillaSticker(bot))