import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import logging

class TrackDetails(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="track",
        description="Get track details from a Spotify URL"
    )
    @app_commands.describe(url="Spotify song URL")
    async def track(self, interaction: discord.Interaction, url: str):
        await interaction.response.defer()

        api_url = f"https://api.song.link/v1-alpha.1/links?url={url}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url) as resp:
                    if resp.status != 200:
                        await interaction.followup.send(
                            f"Failed to retrieve data from API (status code {resp.status}).",
                            ephemeral=True
                        )
                        return
                    data = await resp.json()
        except Exception as e:
            logging.error(f"API request error: {e}")
            await interaction.followup.send(
                "An error occurred while fetching track data.",
                ephemeral=True
            )
            return

        entity = data.get("entityUniqueId")
        if not entity:
            await interaction.followup.send(
                "No track data found for the provided URL.",
                ephemeral=True
            )
            return

        entities = data.get("entitiesByUniqueId", {})
        details = entities.get(entity, {})

        track_name = details.get("title", "Unknown title")
        artist_name = details.get("artistName", "Unknown artist")
        page_url = data.get("pageUrl", "")
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

async def setup(bot: commands.Bot):
    await bot.add_cog(TrackDetails(bot))
