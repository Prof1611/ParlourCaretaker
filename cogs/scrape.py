import logging
import discord
from discord.ext import commands
from dateutil.parser import parse
from discord import EntityType, PrivacyLevel
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import yaml
import os
import asyncio
from datetime import datetime
import pytz
import re


class Scrape(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cover_image_url = "event_image.jpg"

        # Load the config file with UTF-8 encoding to handle special characters
        with open("config.yaml", "r", encoding="utf-8") as config_file:
            self.config = yaml.safe_load(config_file)

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"\033[35m{__name__}\033[0m synced successfully.")

    @discord.app_commands.command(
        name="scrape",
        description="Checks the band's website for new shows and updates #gig-chats.",
    )
    async def scrape(self, interaction: discord.Interaction):
        await interaction.response.defer()

        try:
            new_shows = await asyncio.to_thread(self.run_scraper)
            await self.check_forum_threads(interaction.guild, interaction, new_shows)
        except Exception as e:
            logging.error(f"An error occurred in the scrape command: {e}")

    def run_scraper(self):
        logging.info("Running scraper...")
        shows = []

        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--window-position=-2400,-2400")
        chrome_options.add_argument("--log-level=3")
        os.environ["WDM_LOG_LEVEL"] = "3"

        try:
            driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()), options=chrome_options
            )
            driver.get("https://www.thelastdinnerparty.co.uk/#live")
            driver.implicitly_wait(10)

            event_rows = driver.find_elements(By.CLASS_NAME, "seated-event-row")

            for row in event_rows:
                try:
                    date_str = row.find_element(
                        By.CLASS_NAME, "seated-event-date-cell"
                    ).text.strip()
                    venue = row.find_element(
                        By.CLASS_NAME, "seated-event-venue-name"
                    ).text.strip()
                    location = row.find_element(
                        By.CLASS_NAME, "seated-event-venue-location"
                    ).text.strip()

                    date = self.format_date(date_str)
                    if date != "Invalid Date":
                        shows.append((date, venue, location))
                    else:
                        logging.error(
                            f"Invalid date format for venue: {venue}, location: {location}"
                        )

                except Exception as e:
                    logging.error(f"Error processing event row: {e}")

        except Exception as e:
            logging.error(f"An error occurred during scraping: {e}")
        finally:
            driver.quit()

        logging.info(f"Scraper found {len(shows)} events from website.")
        return shows

    def format_date(self, date_str):
        # Ensure date string is properly formatted before parsing
        date_str = (
            date_str.strip().title()
        )  # Strip extra spaces and capitalise the month abbreviation
        logging.info(f"Formatting date: {date_str}")

        # Handle date ranges (e.g., "Jul 31, 2025 - Aug 3, 2025")
        if "-" in date_str:
            start_date_str, end_date_str = map(str.strip, date_str.split("-"))

            try:
                start_date = datetime.strptime(start_date_str, "%b %d, %Y").strftime(
                    "%d %B %Y"
                )
                end_date = datetime.strptime(end_date_str, "%b %d, %Y").strftime(
                    "%d %B %Y"
                )
                formatted_date = f"{start_date} - {end_date}"
            except ValueError as e:
                logging.error(f"Error formatting date range: {e}")
                formatted_date = "Invalid Date Range"
        else:
            # Handle single dates (e.g., "Nov 6, 2024")
            try:
                formatted_date = datetime.strptime(date_str, "%b %d, %Y").strftime(
                    "%d %B %Y"
                )
            except ValueError as e:
                logging.error(f"Error formatting single date: {e}")
                formatted_date = "Invalid Date"

        logging.debug(f"Formatted date: {formatted_date}")
        return formatted_date

    async def check_forum_threads(self, guild, interaction, shows):
        gigchats_id = self.config["gigchats_id"]
        gigchats_channel = guild.get_channel(gigchats_id)

        if gigchats_channel is None:
            logging.error(f"Channel with ID {gigchats_id} not found.")
            await interaction.followup.send("The specified channel was not found.")
            return

        new_threads_created = 0
        new_events_created = 0

        for date_info, venue, location in shows:
            if isinstance(date_info, tuple) and len(date_info) == 2:  # Date range
                start_date, end_date = date_info
                date_display = f"{start_date} - {end_date}"
            else:
                start_date = end_date = date_info[0]
                date_display = start_date

            logging.info(
                f"Checking if thread and event exist for {venue}, {location} on {date_display}."
            )
            exists = await self.thread_exists(gigchats_channel, date_display)
            if not exists:
                await self.create_thread(
                    gigchats_channel, date_display, venue, location
                )
                new_threads_created += 1

            event_exists = await self.event_exists(guild, venue, location, date_display)
            if not event_exists:
                await self.create_discord_event(
                    guild, venue, location, (start_date, end_date)
                )
                new_events_created += 1

        await self.send_summary(interaction, new_threads_created, new_events_created)

    async def send_summary(self, interaction, new_threads_created, new_events_created):
        logging.info(
            f"Sending summary: {new_threads_created} threads and {new_events_created} new events created."
        )
        embed = (
            discord.Embed(
                title=f"{new_threads_created} new threads created and {new_events_created} events created",
                description="New show threads and events have been created for upcoming events.",
                color=discord.Color.green(),
            )
            if new_threads_created or new_events_created
            else discord.Embed(
                title="No new threads or events created",
                description="All existing events already have threads and events.",
                color=discord.Color.blurple(),
            )
        )
        await interaction.followup.send(embed=embed)

    async def thread_exists(self, channel, event_date):
        pattern = rf"^{re.escape(event_date)}( - CANCELLED)?$"
        for thread in channel.threads:
            if re.match(pattern, thread.name, re.IGNORECASE):
                logging.info(f"Thread found: {thread.name}")
                return True
        logging.info("No existing thread found.")
        return False

    async def event_exists(self, guild, venue, location, event_date):
        events = await guild.fetch_scheduled_events()
        title = f"TLDP @ {venue.title()}, {location.title()}"

        if isinstance(event_date, tuple) and len(event_date) == 2:  # Date range
            start_date, end_date = event_date
            date_range = [
                datetime.strptime(start_date, "%d %B %Y").date(),
                datetime.strptime(end_date, "%d %B %Y").date(),
            ]
        else:
            date_range = [datetime.strptime(event_date, "%d %B %Y").date()]

        for event in events:
            event_date_in_guild = event.start_time.date()
            if event.name.lower() == title.lower() and any(
                event_date_in_guild == date for date in date_range
            ):
                logging.info(f"Event found: {event.name} on {event_date_in_guild}")
                return True

        logging.info("No existing event found.")
        return False

    async def create_thread(self, channel, event_date, venue, location):
        logging.info(f"Creating thread for {event_date} at {venue}, {location}")
        title_case_event_date = event_date.title()
        content = f"The Last Dinner Party at {venue.title()}, {location.title()}"
        await channel.create_thread(
            name=title_case_event_date,
            content=content,
            auto_archive_duration=60,
        )
        logging.info(f"Thread created: {title_case_event_date}")

    async def create_discord_event(self, guild, venue, location, date_info):
        title = f"TLDP @ {venue.title()}, {location.title()}"
        logging.info(f"Creating event '{title}' for dates '{date_info}'")

        # Specify your local timezone
        local_tz = pytz.timezone("Europe/London")

        if isinstance(date_info, tuple) and len(date_info) == 2:  # Date range
            start_date_str, end_date_str = date_info
            start_time = local_tz.localize(
                datetime.strptime(f"{start_date_str} 19:00", "%d %B %Y %H:%M")
            )
            end_time = local_tz.localize(
                datetime.strptime(f"{end_date_str} 23:00", "%d %B %Y %H:%M")
            )
        else:
            start_time = local_tz.localize(
                datetime.strptime(f"{date_info[0]} 19:00", "%d %B %Y %H:%M")
            )
            end_time = local_tz.localize(
                datetime.strptime(f"{date_info[0]} 23:00", "%d %B %Y %H:%M")
            )

        # Convert local time to UTC
        start_time_utc = start_time.astimezone(pytz.utc)
        end_time_utc = end_time.astimezone(pytz.utc)

        current_time = discord.utils.utcnow()
        if start_time_utc < current_time:
            logging.warning(
                f"Event '{title}' is in the past ({start_time_utc} < {current_time}). Not creating the event."
            )
            return

        cover_image_bytes = None
        if os.path.exists(self.cover_image_url):
            with open(self.cover_image_url, "rb") as image_file:
                cover_image_bytes = image_file.read()
        else:
            logging.warning(
                f"Cover image '{self.cover_image_url}' not found. Skipping image upload."
            )

        description = f"The Last Dinner Party at {venue.title()}, {location.title()}"
        entity_type = EntityType.external
        privacy_level = PrivacyLevel.guild_only

        try:
            event = await guild.create_scheduled_event(
                name=title,
                description=description,
                start_time=start_time_utc,
                end_time=end_time_utc,
                location=location.title(),
                entity_type=entity_type,
                privacy_level=privacy_level,
                image=cover_image_bytes,
            )
            logging.info(
                f"Successfully created event: {event.name} from {start_time_utc} to {end_time_utc}"
            )
            await asyncio.sleep(5)
        except Exception as e:
            logging.error(f"Failed to create event '{title}': {e}")


async def setup(bot):
    await bot.add_cog(Scrape(bot))
