import discord
from discord import app_commands
from discord.ext import commands
import aiohttp

GUILD_ID = 1151481698786213960  # Replace with your test guild/server ID (int)

class TrackDetails(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    track_group = app_commands.Group(name="track", description="Track related commands")

    @track_group.command(name="details", description="Get track details from a Spotify URL")
    @app_commands.describe(url="Spotify song URL")
    async def details(self, interaction: discord.Interaction, url: str):
        await interaction.response.defer()  # Acknowledge command and defer response

        api_url = f"https://api.song.link/v1-alpha.1/links?url={url}"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(api_url) as resp:
                    if resp.status != 200:
                        await interaction.followup.send(f"Failed to get data from API, status code: {resp.status}")
                        return
                    data = await resp.json()
            except Exception as e:
                await interaction.followup.send(f"Error fetching data: {e}")
                return

        entity = data.get("entityUniqueId", None)
        if not entity:
            await interaction.followup.send("No track data found for that URL.")
            return

        page_url = data.get("pageUrl", "No page URL found")
        entities = data.get("entitiesByUniqueId", {})
        details = entities.get(entity, {})

        track_name = details.get("title", "Unknown title")
        artist_name = details.get("artistName", "Unknown artist")
        thumbnail = details.get("thumbnailUrl")

        embed = discord.Embed(
            title=f"{track_name} - {artist_name}",
            url=page_url,
            color=discord.Color.green()
        )

        if thumbnail:
            embed.set_thumbnail(url=thumbnail)

        platforms = data.get("linksByPlatform", {})
        platform_names = ", ".join(platforms.keys()) if platforms else "Unknown"

        embed.add_field(name="Available on", value=platform_names, inline=False)

        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(TrackDetails(bot))


# ------------- Main bot code -------------

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        guild = discord.Object(id=GUILD_ID)
        synced = await bot.tree.sync(guild=guild)  # Sync commands to your test guild
        print(f"Synced {len(synced)} commands to guild {GUILD_ID}")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

async def main():
    async with bot:
        await bot.load_extension("track_cog")  # Make sure this file is named track_cog.py
        await bot.start("YOUR_BOT_TOKEN")

import asyncio
asyncio.run(main())
