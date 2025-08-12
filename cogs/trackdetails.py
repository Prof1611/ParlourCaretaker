import discord
import logging
import yaml
from discord import app_commands
from discord.ext import commands
import aiohttp
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional


def audit_log(message: str):
    """Append a timestamped message to the audit log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("audit.log", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


def colour_from_value(value: Optional[str], fallback: discord.Color) -> discord.Color:
    """
    Convert a hex string like '#0ca115' or '0ca115' into a discord.Color.
    If invalid or None, return the provided fallback colour.
    """
    if not value or not isinstance(value, str):
        return fallback
    try:
        v = value.strip().lower()
        if v.startswith("#"):
            v = v[1:]
        return discord.Color(int(v, 16))
    except Exception:
        return fallback


class TrackDetails(commands.Cog):
    """
    Fetches rich cross-platform track details using the Songlink/Odesli API
    from a supplied Spotify (or other) track URL and returns an embed with
    a formatted platform list and link buttons.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Load config if present; fall back to sensible defaults.
        try:
            with open("config.yaml", "r", encoding="utf-8") as f:
                self.config: Dict[str, Any] = yaml.safe_load(f) or {}
        except Exception:
            self.config = {}

        # Configurable options with defaults
        api_cfg = self.config.get("songlink", {})
        self.api_base: str = api_cfg.get(
            "base_url", "https://api.song.link/v1-alpha.1/links"
        )
        self.timeout_seconds: int = int(api_cfg.get("timeout_seconds", 12))
        self.common_platform_order = api_cfg.get(
            "platform_order",
            [
                "spotify",
                "appleMusic",
                "youtube",
                "youtubeMusic",
                "itunes",
                "amazonMusic",
                "amazonStore",
                "deezer",
                "tidal",
                "soundcloud",
                "pandora",
                "napster",
                "yandex",
                "gaana",
                "saavn",
                "anghami",
                "playMusic",
                "itune",
            ],
        )

        colours_cfg = self.config.get("colours", {})
        self.success_colour = colour_from_value(
            colours_cfg.get("success", "#0ca115"), discord.Color.green()
        )
        self.info_colour = colour_from_value(
            colours_cfg.get("info", "#5865F2"), discord.Color.blurple()
        )
        self.error_colour = colour_from_value(
            colours_cfg.get("error", "#ED4245"), discord.Color.red()
        )

        # Mapping of platform keys to friendly names + emojis
        self.platform_map: Dict[str, str] = {
            "spotify": "🎵 Spotify",
            "appleMusic": "🍎 Apple Music",
            "youtube": "📺 YouTube",
            "youtubeMusic": "🎶 YouTube Music",
            "itunes": "📀 iTunes",
            "amazonMusic": "📱 Amazon Music",
            "amazonStore": "🛒 Amazon Store",
            "deezer": "📡 Deezer",
            "tidal": "💿 TIDAL",
            "soundcloud": "🎧 SoundCloud",
        }

        audit_log("TrackDetails cog initialised and configuration loaded successfully.")

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info("\033[96mTrackDetails\033[0m cog synced successfully.")
        audit_log("TrackDetails cog synced successfully.")

    @app_commands.command(
        name="track",
        description="Get cross-platform track details from a Spotify (or other) URL",
    )
    @app_commands.describe(url="A Spotify, Apple Music, YouTube, or other track URL")
    async def track(self, interaction: discord.Interaction, url: str):
        await interaction.response.defer()
        audit_log(
            f"{interaction.user.name} (ID: {interaction.user.id}) invoked /track with URL: {url}"
        )

        api_url = f"{self.api_base}?url={url}"

        # Fetch from Songlink/Odesli
        try:
            data = await self.fetch_json(api_url, timeout=self.timeout_seconds)
            if not data:
                await self.send_error(
                    interaction,
                    "No data was returned from the track lookup. Please check the URL.",
                )
                audit_log("Songlink API returned no data.")
                return
        except Exception as e:
            logging.error(f"API request error: {e}")
            audit_log(f"Error during Songlink API request: {e}")
            await self.send_error(
                interaction,
                "An error occurred while fetching track data. Please try again shortly.",
            )
            return

        # Extract entity and details
        entity_id = data.get("entityUniqueId")
        entities = data.get("entitiesByUniqueId", {}) or {}
        details = entities.get(entity_id, {}) if entity_id else {}

        # Fall back if entityUniqueId missing but entities contain one item
        if not details and entities:
            try:
                details = next(iter(entities.values()))
            except StopIteration:
                details = {}

        if not details:
            await self.send_error(
                interaction, "No track details were found for the provided URL."
            )
            audit_log("No track details found in API response.")
            return

        track_name = details.get("title") or "Unknown title"
        artist_name = details.get("artistName") or "Unknown artist"
        page_url = data.get("pageUrl") or url
        thumbnail = details.get("thumbnailUrl")

        # Build embed
        embed = discord.Embed(
            title=f"{track_name} — {artist_name}",
            url=page_url,
            color=self.success_colour,
        )
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)

        # Platforms section, formatted nicely with emojis and ordering
        links_by_platform: Dict[str, Dict[str, Any]] = (
            data.get("linksByPlatform", {}) or {}
        )
        available_platforms = list(links_by_platform.keys())

        if available_platforms:
            ordered_platforms = sorted(
                available_platforms,
                key=lambda p: self._order_key(p, available_platforms),
            )
            formatted_list = "\n".join(
                self.platform_map.get(p, p.replace("_", " ").title())
                for p in ordered_platforms
            )
            embed.add_field(name="Available on", value=formatted_list, inline=False)
        else:
            embed.add_field(
                name="Available on", value="Unknown or not provided", inline=False
            )

        # Type field
        if details.get("type"):
            embed.add_field(
                name="Type", value=str(details.get("type")).title(), inline=False
            )

        # Detected platforms field (formatted nicely if possible)
        if details.get("platforms"):
            detected = [
                self.platform_map.get(p, p.replace("_", " ").title())
                for p in details.get("platforms")
            ]
            embed.add_field(
                name="Detected platforms",
                value=", ".join(detected),
                inline=False,
            )

        # Create a view with buttons to common platforms in a sensible order
        view = self.build_platform_buttons(links_by_platform)

        try:
            await interaction.followup.send(embed=embed, view=view if view else None)
            audit_log(
                f"Track embed sent successfully for '{track_name}' by '{artist_name}'."
            )
        except discord.HTTPException as e:
            logging.error(f"Failed to send track details: {e}")
            audit_log(f"Failed to send track details: {e}")
            await self.send_error(
                interaction, f"Failed to send the track details: `{e}`"
            )

    def _order_key(self, platform_key: str, available_platforms: list) -> int:
        """
        Helper to create a stable ordering key:
        - Known platforms ordered by self.common_platform_order index.
        - Unknown platforms come afterwards in the order they appear.
        """
        if platform_key in self.common_platform_order:
            return self.common_platform_order.index(platform_key)
        # place after known list but retain stable order among unknowns
        return len(self.common_platform_order) + available_platforms.index(platform_key)

    async def fetch_json(self, url: str, timeout: int = 10) -> Optional[Dict[str, Any]]:
        """Fetch JSON from a URL using aiohttp with a timeout."""
        timeout_cfg = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=timeout_cfg) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logging.error(
                        f"Songlink API responded with status {resp.status}: {text[:200]}"
                    )
                    raise RuntimeError(f"API status {resp.status}")
                return await resp.json()

    def build_platform_buttons(
        self, links_by_platform: Dict[str, Dict[str, Any]]
    ) -> Optional[discord.ui.View]:
        """
        Build a Discord view containing URL buttons for platforms.
        Discord allows up to 5 buttons per row and 5 rows total.
        """
        if not links_by_platform:
            return None

        # Preserve preferred order, then append any extras not in the order list.
        ordered = [p for p in self.common_platform_order if p in links_by_platform]
        extras = [p for p in links_by_platform.keys() if p not in ordered]
        final_order = ordered + extras

        view = discord.ui.View()
        buttons_added = 0

        for platform in final_order:
            platform_info = links_by_platform.get(platform) or {}
            url = platform_info.get("url")
            if not url:
                continue

            label = self.pretty_platform_name(platform)
            try:
                # Note: URL buttons cannot include emoji in the label reliably across clients,
                # so we keep labels clean and readable.
                view.add_item(discord.ui.Button(label=label, url=url))
                buttons_added += 1
            except Exception:
                break

            if buttons_added >= 25:
                break

        return view if buttons_added > 0 else None

    def pretty_platform_name(self, key: str) -> str:
        """
        Convert Songlink platform keys to nicer button labels.
        Example: 'appleMusic' -> 'Apple Music'
        """
        mapping = {
            "spotify": "Spotify",
            "appleMusic": "Apple Music",
            "youtubeMusic": "YouTube Music",
            "youtube": "YouTube",
            "amazonMusic": "Amazon Music",
            "deezer": "Deezer",
            "tidal": "TIDAL",
            "soundcloud": "SoundCloud",
        }
        return mapping.get(key, key.replace("_", " ").title())

    async def send_error(self, interaction: discord.Interaction, message: str):
        """Send a standardised error embed."""
        embed = discord.Embed(
            title="Error", description=message, color=self.error_colour
        )
        try:
            await interaction.followup.send(embed=embed, ephemeral=True)
        except discord.HTTPException:
            try:
                await interaction.response.send_message(embed=embed, ephemeral=True)
            except Exception:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(TrackDetails(bot))
