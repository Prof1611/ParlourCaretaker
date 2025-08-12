import discord
from discord import app_commands
from discord.ext import commands
import aiohttp

class TrackDetails(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Create a command group "track"
        self.track_group = app_commands.Group(name="track", description="Track related commands")

        # Add the 'details' subcommand to the group
        @self.track_group.command(name="details", description="Get track details from a Spotify URL")
        @app_commands.describe(url="Spotify song URL")
        async def details(interaction: discord.Interaction, url: str):
            await interaction.response.defer()

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

        # Add the command group to the bot's tree
        self.bot.tree.add_command(self.track_group)

async def setup(bot):
    await bot.add_cog(TrackDetails(bot))
