import discord
import logging
import yaml
from discord import app_commands
from discord.ext import commands
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import os
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import re
import platform


def audit_log(message: str):
    """Append a timestamped message to the audit log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("audit.log", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


class Scrape(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Load the config file with UTF-8 encoding to handle special characters like emoji.
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
        # Log the invocation of the scrape command.
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
        logging.info("Running scraper...")
        new_entries = []

        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--window-position=-2400,-2400")
        chrome_options.add_argument("--log-level=3")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--remote-debugging-port=9222")

        os.environ["WDM_LOG_LEVEL"] = "3"

        # Detect the operating system.
        system_os = platform.system()
        arch = platform.machine()
        logging.info(f"Detected OS: {system_os}, Architecture: {arch}")

        try:
            if system_os == "Windows":
                driver = webdriver.Chrome(
                    service=Service(ChromeDriverManager().install()),
                    options=chrome_options,
                )
            elif system_os == "Linux" and arch in ["arm64", "aarch64"]:
                chrome_options.binary_location = "/usr/bin/chromium-browser"
                chromedriver_path = "/usr/bin/chromedriver"
                if not os.path.exists(chromedriver_path):
                    logging.error(
                        "Chromedriver not found! Make sure it's installed at /usr/bin/chromedriver."
                    )
                    return []
                service = Service(chromedriver_path)
                driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                logging.error("Unsupported OS for this scraper.")
                return []

            driver.get("https://www.thelastdinnerparty.co.uk/#live")
            driver.implicitly_wait(10)

            event_rows = driver.find_elements(By.CLASS_NAME, "seated-event-row")
            logging.info(
                f"Successfully retrieved {len(event_rows)} event rows from website"
            )

            for row in event_rows:
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
                entry = (date.lower(), venue.lower(), location.lower())
                new_entries.append((date, venue, location))
                logging.info(f"New entry found: {entry}")
        except Exception as e:
            logging.error(f"An error occurred during scraping: {e}")
        finally:
            driver.quit()

        return new_entries

    def format_date(self, date_str):
        if "-" in date_str:
            start_date_str, end_date_str = map(str.strip, date_str.split("-"))
            start_date = datetime.strptime(start_date_str, "%b %d, %Y").strftime(
                "%d %B %Y"
            )
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
                start_dt = datetime(
                    dt_start.year, dt_start.month, dt_start.day, 8, 0, 0, tzinfo=tz
                )
                end_dt = datetime(
                    dt_end.year, dt_end.month, dt_end.day, 23, 0, 0, tzinfo=tz
                )
            else:
                dt = datetime.strptime(formatted_date, "%d %B %Y")
                start_dt = datetime(dt.year, dt.month, dt.day, 19, 0, 0, tzinfo=tz)
                end_dt = datetime(dt.year, dt.month, dt.day, 23, 0, 0, tzinfo=tz)
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
            event_date = entry[0]
            venue = entry[1]
            location = entry[2]
            # The thread title is just the date.
            thread_title = event_date.title()
            # Check if a thread exists with the matching title and that its starter message contains the location.
            exists = await self.thread_exists(gigchats_channel, thread_title, location)
            logging.info(
                f"Does thread '{thread_title}' with location '{location.title()}' exist in channel '{gigchats_channel.name}'? {exists}"
            )

            if not exists:
                try:
                    content = (
                        f"The Last Dinner Party at {venue.title()}, {location.title()}"
                    )
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
                    logging.error(
                        f"Permission denied when trying to create thread '{thread_title}'"
                    )
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
        normalized_title = thread_title.strip().lower()
        normalized_location = location.strip().lower()
        for thread in channel.threads:
            if thread.name.strip().lower() == normalized_title:
                try:
                    # Fetch the starter message of the thread.
                    starter_message = await thread.fetch_message(thread.id)
                except Exception as e:
                    continue
                if normalized_location in starter_message.content.lower():
                    return True
        return False

    async def check_server_events(self, guild, interaction, new_entries):
        new_events_created = 0

        # Load the event image from the root folder.
        try:
            with open("event-image.jpg", "rb") as img_file:
                event_image = img_file.read()
        except Exception as e:
            logging.error(f"Failed to load event image: {e}")
            event_image = None

        # Refresh the scheduled events list.
        scheduled_events = await guild.fetch_scheduled_events()

        for entry in new_entries:
            event_date = entry[0]
            venue = entry[1]
            location = entry[2]
            event_name = f"{event_date.title()} - {venue.title()}"

            exists = any(e.name.lower() == event_name.lower() for e in scheduled_events)
            logging.info(
                f"Does scheduled event '{event_name}' exist in guild '{guild.name}'? {exists}"
            )
            if not exists:
                start_time, end_time = self.parse_event_dates(event_date)
                try:
                    await guild.create_scheduled_event(
                        name=event_name,
                        description=f"The Last Dinner Party at {venue.title()}, {location.title()}",
                        start_time=start_time,
                        end_time=end_time,
                        location=f"{venue.title()}, {location.title()}",
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
                    logging.error(
                        f"Permission denied when trying to create scheduled event '{event_name}'"
                    )
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
                    logging.error(
                        f"Failed to create scheduled event '{event_name}': {e}"
                    )
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

    async def send_combined_summary(
        self, interaction, threads_created: int, events_created: int
    ):
        description = (
            f"**Forum Threads:** {threads_created} new thread{'s' if threads_created != 1 else ''} created.\n"
            f"**Scheduled Events:** {events_created} new scheduled event{'s' if events_created != 1 else ''} created."
        )
        embed = discord.Embed(
            title="Scrape Completed",
            description=description,
            color=(
                discord.Color.green()
                if (threads_created or events_created)
                else discord.Color.blurple()
            ),
        )
        await interaction.followup.send(embed=embed)

    async def setup_audit(self, interaction):
        audit_log(
            f"{interaction.user.name} (ID: {interaction.user.id}) initiated a scrape command in guild '{interaction.guild.name}' (ID: {interaction.guild.id})."
        )


async def setup(bot):
    await bot.add_cog(Scrape(bot))
