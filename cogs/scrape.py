import discord
import logging
import yaml
from discord import app_commands
from discord.ext import commands
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import requests  # For API requests
import unicodedata
import string


def audit_log(message: str):
    """Append a timestamped message to the audit log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("audit.log", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


def normalize_string(s: str) -> str:
    """
    Normalize a string by removing diacritics, punctuation, extra whitespace,
    and converting to lowercase.
    """
    s = unicodedata.normalize("NFKD", s).encode("ASCII", "ignore").decode("utf-8")
    s = s.translate(str.maketrans("", "", string.punctuation))
    return " ".join(s.split()).lower()


class Scrape(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Load the config file with UTF-8 encoding.
        with open("config.yaml", "r", encoding="utf-8") as config_file:
            self.config = yaml.safe_load(config_file)

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"\033[96mScrape\033[0m cog synced successfully.")
        audit_log("Scrape cog synced successfully.")

    @discord.app_commands.command(
        name="scrape",
        description="Checks the band's website for new shows and updates #gig-chats and server events.",
    )
    async def scrape(self, interaction: discord.Interaction):
        await interaction.response.defer()
        audit_log(
            f"{interaction.user.name} (ID: {interaction.user.id}) invoked /scrape command in guild '{interaction.guild.name}' (ID: {interaction.guild.id})."
        )
        try:
            # Run the scraper asynchronously in a separate thread.
            new_entries = await asyncio.to_thread(self.run_scraper)
            audit_log(
                f"{interaction.user.name} (ID: {interaction.user.id}) retrieved {len(new_entries)} new entries from the website."
            )
            # Create forum threads and get count.
            threads_created = await self.check_forum_threads(
                interaction.guild, interaction, new_entries
            )
            # Create scheduled events and get count.
            events_created = await self.check_server_events(
                interaction.guild, interaction, new_entries
            )
            # Send a combined summary.
            await self.send_combined_summary(
                interaction, threads_created, events_created
            )
            logging.info(
                f"Full scrape and creation process done: {threads_created} threads, {events_created} events created."
            )
        except Exception as e:
            logging.error(f"An error occurred in the scrape command: {e}")
            audit_log(
                f"{interaction.user.name} (ID: {interaction.user.id}) encountered an error in /scrape command: {e}"
            )
            error_embed = discord.Embed(
                title="Error",
                description=f"An error occurred during scraping:\n`{e}`",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=error_embed)

    def run_scraper(self):
        logging.info("Running scraper using Seated API...")
        new_entries = []
        try:
            # API endpoint that returns event data (powered by Seated)
            url = "https://cdn.seated.com/api/tour/deb5e9f0-4af5-413c-a24b-1b22f11513b2?include=tour-events"
            response = requests.get(url)
            response.raise_for_status()  # Raise an exception for bad responses
            data = response.json()
            logging.info(f"Full API response: {data}")  # Debug: log entire response

            # Extract events from the "included" array where type is "tour-events"
            included = data.get("included", [])
            events = [event for event in included if event.get("type") == "tour-events"]
            logging.info(f"Retrieved {len(events)} events from API.")

            for event in events:
                attributes = event.get("attributes", {})
                start_date = attributes.get("starts-at-date-local", "")
                end_date = attributes.get("ends-at-date-local", "")
                if start_date:
                    formatted_start = self.format_api_date(start_date)
                else:
                    formatted_start = ""
                if end_date and end_date.lower() != "none" and end_date != start_date:
                    formatted_end = self.format_api_date(end_date)
                    formatted_date = f"{formatted_start} - {formatted_end}"
                else:
                    formatted_date = formatted_start

                venue = attributes.get("venue-name", "")
                location = attributes.get("formatted-address", "")
                entry = (formatted_date, venue, location)
                new_entries.append(entry)
                logging.info(
                    f"New entry found: ({normalize_string(formatted_date)}, {normalize_string(venue)}, {normalize_string(location)})"
                )
        except Exception as e:
            logging.error(f"An error occurred during API scraping: {e}")
        return new_entries

    def format_api_date(self, iso_date_str):
        """
        Convert an ISO date string (YYYY-MM-DD) into the format "DD Month YYYY".
        For example, "2025-04-15" becomes "15 April 2025".
        """
        try:
            dt = datetime.strptime(iso_date_str, "%Y-%m-%d")
            return dt.strftime("%d %B %Y")
        except Exception as e:
            logging.error(f"Error formatting API date '{iso_date_str}': {e}")
            return iso_date_str

    def format_date(self, date_str):
        # Original method for page-based dates remains unchanged.
        if "-" in date_str:
            start_date_str, end_date_str = map(str.strip, date_str.split("-"))
            start_date = datetime.strptime(start_date_str, "%b %d, %Y").strftime("%d %B %Y")
            end_date = datetime.strptime(end_date_str, "%b %d, %Y").strftime("%d %B %Y")
            return f"{start_date} - {end_date}"
        else:
            return datetime.strptime(date_str, "%b %d, %Y").strftime("%d %B %Y")

    def parse_event_dates(self, formatted_date: str):
        """
        Parse the formatted date string (e.g. "01 January 2025" or "01 January 2025 - 02 January 2025")
        into start and end timezone-aware datetime objects.

        - If it's a single date, set the event from 7:00 PM to 11:00 PM.
        - If it's a range, set the start time to 8:00 AM on the first day and the end time to 11:00 PM on the last day.
        """
        try:
            tz = ZoneInfo("Europe/London")
            if "-" in formatted_date:
                start_date_str, end_date_str = map(str.strip, formatted_date.split("-"))
                dt_start = datetime.strptime(start_date_str, "%d %B %Y")
                dt_end = datetime.strptime(end_date_str, "%d %B %Y")
                start_dt = datetime(dt_start.year, dt_start.month, dt_start.day, 8, 0, 0, tzinfo=tz)
                end_dt = datetime(dt_end.year, dt_end.month, dt_end.day, 23, 0, 0, tzinfo=tz)
            else:
                dt = datetime.strptime(formatted_date, "%d %B %Y")
                start_dt = datetime(dt.year, dt.month, dt.day, 19, 0, 0, tzinfo=tz)
                end_dt = datetime(dt.year, dt.month, dt.day, 23, 0, 0, tzinfo=tz)
            logging.info(f"Parsed event dates from '{formatted_date}' -> start: {start_dt}, end: {end_dt}")
            return start_dt, end_dt
        except Exception as e:
            logging.error(f"Error parsing event dates from '{formatted_date}': {e}")
            now = datetime.now(ZoneInfo("Europe/London"))
            return now, now + timedelta(hours=4)

    async def check_forum_threads(self, guild, interaction, new_entries):
        gigchats_id = self.config["gigchats_id"]
        gigchats_channel = guild.get_channel(gigchats_id)
        if gigchats_channel is None:
            logging.error(f"Channel with ID {gigchats_id} not found.")
            error_embed = discord.Embed(
                title="Error",
                description="Threads channel was not found. Please double-check the config.",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=error_embed)
            audit_log(
                f"{interaction.user.name} (ID: {interaction.user.id}): Failed to update threads because channel with ID {gigchats_id} was not found in guild '{guild.name}' (ID: {guild.id})."
            )
            return 0

        new_threads_created = 0
        for entry in new_entries:
            event_date, venue, location = entry
            thread_title = event_date.title()
            norm_title = normalize_string(thread_title)
            norm_location = normalize_string(location)
            logging.info(f"Checking thread: original title='{thread_title}', normalized='{norm_title}', location normalized='{norm_location}'")
            exists = await self.thread_exists(gigchats_channel, norm_title, norm_location)
            logging.info(
                f"Does thread '{thread_title}' with location '{location}' exist in channel '{gigchats_channel.name}'? {exists}"
            )
            if not exists:
                try:
                    content = f"The Last Dinner Party at {venue.title()}, {location.title()}"
                    logging.info(f"Creating thread for: {thread_title}")
                    await gigchats_channel.create_thread(
                        name=thread_title,
                        content=content,
                        auto_archive_duration=60,
                    )
                    new_threads_created += 1
                    logging.info(f"Successfully created thread: {thread_title}")
                    audit_log(
                        f"{interaction.user.name} (ID: {interaction.user.id}) created thread '{thread_title}' in channel #{gigchats_channel.name} (ID: {gigchats_channel.id}) in guild '{guild.name}' (ID: {guild.id})."
                    )
                    await asyncio.sleep(5)
                except discord.Forbidden:
                    logging.error(f"Permission denied when trying to create thread '{thread_title}'")
                    error_embed = discord.Embed(
                        title="Error",
                        description=f"Permission denied when trying to create thread '{thread_title}'.",
                        color=discord.Color.red(),
                    )
                    await interaction.followup.send(embed=error_embed)
                    audit_log(
                        f"{interaction.user.name} (ID: {interaction.user.id}) encountered permission error creating thread '{thread_title}' in channel #{gigchats_channel.name} (ID: {gigchats_channel.id})."
                    )
                except discord.HTTPException as e:
                    logging.error(f"Failed to create thread '{thread_title}': {e}")
                    error_embed = discord.Embed(
                        title="Error",
                        description=f"Failed to create thread '{thread_title}': `{e}`",
                        color=discord.Color.red(),
                    )
                    await interaction.followup.send(embed=error_embed)
                    audit_log(
                        f"{interaction.user.name} (ID: {interaction.user.id}) failed to create thread '{thread_title}' in channel #{gigchats_channel.name} (ID: {gigchats_channel.id}) due to HTTP error: {e}"
                    )
        return new_threads_created

    async def thread_exists(self, channel, thread_title, location):
        """Check if a thread exists with the given title and if its starter message contains the location."""
        norm_title = normalize_string(thread_title)
        norm_location = normalize_string(location)
        logging.info(f"Checking existence for thread with normalized title '{norm_title}' and location '{norm_location}'")
        try:
            threads = channel.threads
            logging.info(f"Channel '{channel.name}' has {len(threads)} active threads.")
        except Exception as e:
            logging.error(f"Error accessing channel threads: {e}")
            threads = []
        for thread in threads:
            thread_norm = normalize_string(thread.name)
            logging.info(f"Comparing with thread: original name='{thread.name}', normalized='{thread_norm}'")
            if thread_norm == norm_title:
                try:
                    starter_message = await thread.fetch_message(thread.id)
                    message_norm = normalize_string(starter_message.content)
                    logging.info(f"Starter message for thread '{thread.name}' normalized to: '{message_norm}'")
                except Exception as e:
                    logging.error(f"Error fetching starter message for thread '{thread.name}': {e}")
                    return True  # Assume thread exists if we can't fetch the message
                if norm_location and norm_location in message_norm:
                    logging.info(f"Found matching location '{norm_location}' in message for thread '{thread.name}'.")
                    return True
        # Fallback: check scheduled events for matching thread title
        try:
            scheduled_events = await channel.guild.fetch_scheduled_events()
            logging.info(f"Fetched {len(scheduled_events)} scheduled events for guild '{channel.guild.name}'.")
            for event in scheduled_events:
                normalized_event_name = normalize_string(event.name)
                logging.info(f"Comparing with scheduled event: original name='{event.name}', normalized='{normalized_event_name}'")
                # Use startswith to allow for extra details in scheduled event names
                if normalized_event_name.startswith(norm_title):
                    logging.info(f"Match found in scheduled events: '{normalized_event_name}' starts with '{norm_title}'")
                    return True
        except Exception as e:
            logging.error(f"Error fetching scheduled events: {e}")
        return False

    async def check_server_events(self, guild, interaction, new_entries):
        new_events_created = 0
        try:
            with open("event-image.jpg", "rb") as img_file:
                event_image = img_file.read()
        except Exception as e:
            logging.error(f"Failed to load event image: {e}")
            event_image = None

        scheduled_events = await guild.fetch_scheduled_events()
        logging.info(f"Guild '{guild.name}' has {len(scheduled_events)} scheduled events.")
        for entry in new_entries:
            event_date, venue, location = entry
            event_name = f"{event_date.title()} - {venue.title() if venue else ''}"
            norm_event_name = normalize_string(event_name)
            logging.info(f"Normalized scheduled event name: '{norm_event_name}'")
            exists = any(normalize_string(e.name) == norm_event_name for e in scheduled_events)
            logging.info(
                f"Does scheduled event '{event_name}' exist in guild '{guild.name}'? {exists}"
            )
            if not exists:
                start_time, end_time = self.parse_event_dates(event_date)
                try:
                    await guild.create_scheduled_event(
                        name=event_name,
                        description=f"The Last Dinner Party at {venue.title() if venue else ''}, {location.title() if location else ''}",
                        start_time=start_time,
                        end_time=end_time,
                        location=f"{venue.title() if venue else ''}, {location.title() if location else ''}",
                        entity_type=discord.EntityType.external,
                        image=event_image,
                        privacy_level=discord.PrivacyLevel.guild_only,
                    )
                    new_events_created += 1
                    logging.info(f"Successfully created scheduled event: {event_name}")
                    audit_log(
                        f"{interaction.user.name} (ID: {interaction.user.id}) created scheduled event '{event_name}' in guild '{guild.name}' (ID: {guild.id})."
                    )
                    await asyncio.sleep(5)
                except discord.Forbidden:
                    logging.error(f"Permission denied when trying to create scheduled event '{event_name}'")
                    error_embed = discord.Embed(
                        title="Error",
                        description=f"Permission denied when trying to create scheduled event '{event_name}'.",
                        color=discord.Color.red(),
                    )
                    await interaction.followup.send(embed=error_embed)
                    audit_log(
                        f"{interaction.user.name} (ID: {interaction.user.id}) encountered permission error creating scheduled event '{event_name}' in guild '{guild.name}' (ID: {guild.id})."
                    )
                except discord.HTTPException as e:
                    logging.error(f"Failed to create scheduled event '{event_name}': {e}")
                    error_embed = discord.Embed(
                        title="Error",
                        description=f"Failed to create scheduled event '{event_name}': `{e}`",
                        color=discord.Color.red(),
                    )
                    await interaction.followup.send(embed=error_embed)
                    audit_log(
                        f"{interaction.user.name} (ID: {interaction.user.id}) failed to create scheduled event '{event_name}' in guild '{guild.name}' (ID: {guild.id}) due to HTTP error: {e}"
                    )
        return new_events_created

    async def send_combined_summary(self, interaction, threads_created: int, events_created: int):
        if threads_created == 0 and events_created == 0:
            description = "All up to date! No new threads or scheduled events created."
        else:
            description = (
                f"**Forum Threads:** {threads_created} new thread{'s' if threads_created != 1 else ''} created.\n"
                f"**Scheduled Events:** {events_created} new scheduled event{'s' if events_created != 1 else ''} created."
            )
        embed = discord.Embed(
            title="Scrape Completed",
            description=description,
            color=(discord.Color.green() if (threads_created or events_created) else discord.Color.blurple()),
        )
        logging.info(f"Sending summary embed with description: {description}")
        await interaction.followup.send(embed=embed)

    async def setup_audit(self, interaction):
        audit_log(
            f"{interaction.user.name} (ID: {interaction.user.id}) initiated a scrape command in guild '{interaction.guild.name}' (ID: {interaction.guild.id})."
        )


async def setup(bot):
    await bot.add_cog(Scrape(bot))
