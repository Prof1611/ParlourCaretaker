import discord
from discord import app_commands
from discord.ext import commands
import aiohttp

class TrackDetails(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="track", description="Get track details from a Spotify URL")
    @app_commands.describe(url="Spotify song URL")
    async def track(self, interaction: discord.Interaction, url: str):
        await interaction.response.defer()  # Acknowledge command to allow time for API call

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

        # Extract some relevant info from data to show
        entity = data.get("entityUniqueId", "Unknown")
        page_url = data.get("pageUrl", "No page URL found")

        # Often the data has a "entitiesByUniqueId" dictionary with details
        entities = data.get("entitiesByUniqueId", {})
        details = entities.get(entity, {})

        # Extract track name and artist from details if possible
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

        # Optionally add other useful fields from data if you want
        # For example, platforms that have the song
        platforms = data.get("linksByPlatform", {})
        platform_names = ", ".join(platforms.keys())

        embed.add_field(name="Available on", value=platform_names or "Unknown", inline=False)

        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(TrackDetails(bot))
