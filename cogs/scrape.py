import logging
import discord
import yaml
from discord.ext import commands
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import os
import asyncio
from datetime import datetime
import re
import platform


class Scrape(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Load the config file with UTF-8 encoding to handle special characters like emoji
        with open("config.yaml", "r", encoding="utf-8") as config_file:
            self.config = yaml.safe_load(config_file)

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"\033[35mScrape\033[0m cog synced successfully.")

    @discord.app_commands.command(
        name="scrape",
        description="Checks the band's website for new shows and updates #gig-chats.",
    )
    async def scrape(self, interaction: discord.Interaction):
        await interaction.response.defer()

        try:
            # Run the scraper asynchronously in a separate thread
            new_entries = await asyncio.to_thread(self.run_scraper)
            await self.check_forum_threads(interaction.guild, interaction, new_entries)
        except Exception as e:
            logging.error(f"An error occurred in the scrape command: {e}")

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

        # Detect the operating system
        system_os = platform.system()
        arch = platform.machine()
        logging.info(f"Detected OS: {system_os}, Architecture: {arch}")

        try:
            if system_os == "Windows":
                # Windows: Use WebDriver Manager
                driver = webdriver.Chrome(
                    service=Service(ChromeDriverManager().install()),
                    options=chrome_options,
                )

            elif system_os == "Linux" and arch in ["arm64", "aarch64"]:
                # Raspberry Pi: Use manually installed ChromiumDriver
                chrome_options.binary_location = "/usr/bin/chromium-browser"
                chromedriver_path = "/usr/bin/chromedriver"  # Path to chromedriver
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

            # Loop through each event and collect its data
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

    async def check_forum_threads(self, guild, interaction, new_entries):
        gigchats_id = self.config["gigchats_id"]
        gigchats_channel = guild.get_channel(gigchats_id)

        if gigchats_channel is None:
            logging.error(f"Channel with ID {gigchats_id} not found.")
            await interaction.followup.send("The specified channel was not found.")
            return

        new_threads_created = 0

        for entry in new_entries:
            event_date = entry[0]
            venue = entry[1]
            location = entry[2]

            exists = await self.thread_exists(gigchats_channel, event_date)
            logging.info(
                f"Does thread '{event_date.title()}' exist in channel '{gigchats_channel.name}'? {exists}"
            )

            if not exists:
                try:
                    title_case_event_date = event_date.title()
                    content = (
                        f"The Last Dinner Party at {venue.title()}, {location.title()}"
                    )
                    logging.info(f"Creating thread for: {title_case_event_date}")
                    await gigchats_channel.create_thread(
                        name=title_case_event_date,
                        content=content,
                        auto_archive_duration=60,
                    )
                    new_threads_created += 1
                    logging.info(
                        f"Successfully created thread: {title_case_event_date}"
                    )
                    await asyncio.sleep(5)
                except discord.Forbidden:
                    logging.error(
                        f"Permission denied when trying to create thread '{title_case_event_date}'"
                    )
                except discord.HTTPException as e:
                    logging.error(
                        f"Failed to create thread '{title_case_event_date}': {e}"
                    )

        await self.send_summary(interaction, new_threads_created)

    async def send_summary(self, interaction, new_threads_created):
        if new_threads_created > 0:
            logging.info(f"{new_threads_created} new threads created.")
            embed = discord.Embed(
                title=f"{new_threads_created} new threads created",
                description="New threads successfully created for upcoming events.",
                color=discord.Color.green(),
            )
        else:
            logging.info("No new threads created.\n")
            embed = discord.Embed(
                title="No new threads created",
                description="All existing events already have threads.",
                color=discord.Color.blurple(),
            )
        await interaction.followup.send(embed=embed)

    async def thread_exists(self, channel, event_date):
        pattern = rf"^{re.escape(event_date)}( - CANCELLED)?$"

        for thread in channel.threads:
            if re.match(pattern, thread.name, re.IGNORECASE):
                return True
        return False


async def setup(bot):
    await bot.add_cog(Scrape(bot))
