import logging
import discord
import yaml
from discord.ext import commands
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import csv
import os
import sys
import asyncio
from datetime import datetime


class Scrape(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.output_csv_path = "scraper_output.csv"

        # Load the config file with UTF-8 encoding to handle special characters like emojis
        with open("config.yaml", 'r', encoding='utf-8') as config_file:
            self.config = yaml.safe_load(config_file)

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"\033[35m{__name__}\033[0m synced successfully.")

    @discord.app_commands.command(name="scrape", description="Checks the band's website for new shows and updates #gig-chats.")
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
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--window-position=-2400,-2400")
        chrome_options.add_argument("--log-level=3")
        os.environ['WDM_LOG_LEVEL'] = '3'

        try:
            driver = webdriver.Chrome(service=Service(
                ChromeDriverManager().install()), options=chrome_options)
            driver.get("https://www.thelastdinnerparty.co.uk/#live")
            driver.implicitly_wait(10)

            event_rows = driver.find_elements(
                By.CLASS_NAME, 'seated-event-row')
            logging.info(
                "Successfully retrieved %d event rows from website", len(event_rows))

            existing_entries = self.load_existing_entries()

            # Open the CSV with newline='\n' to ensure each new entry is correctly separated
            with open(self.output_csv_path, 'a', newline='\n', encoding='utf-8') as csv_file:
                csv_writer = csv.writer(csv_file)

                for row in event_rows:
                    date_str = row.find_element(
                        By.CLASS_NAME, 'seated-event-date-cell').text.strip()
                    venue = row.find_element(
                        By.CLASS_NAME, 'seated-event-venue-name').text.strip()
                    location = row.find_element(
                        By.CLASS_NAME, 'seated-event-venue-location').text.strip()

                    date = self.format_date(date_str)

                    # Normalise new entry data for comparison and writing
                    entry = (date.strip().lower(),
                             venue.strip().lower(), location.strip().lower())
                    if entry not in existing_entries:
                        csv_writer.writerow([date, venue, location])
                        new_entries.append((date, venue, location))
                        logging.info(f"New entry added: {entry}")

        except Exception as e:
            logging.error(f"An error occurred during scraping: {e}")
        finally:
            driver.quit()

        return new_entries

    def load_existing_entries(self):
        existing_entries = set()
        if os.path.exists(self.output_csv_path) and os.path.getsize(self.output_csv_path) > 0:
            with open(self.output_csv_path, 'r', encoding='utf-8') as read_csv_file:
                csv_reader = csv.reader(read_csv_file)
                next(csv_reader)  # Skip header
                for row in csv_reader:
                    normalised_row = tuple(item.strip().lower()
                                           for item in row)
                    existing_entries.add(normalised_row)
        return existing_entries

    def format_date(self, date_str):
        if '-' in date_str:
            start_date_str, end_date_str = map(str.strip, date_str.split('-'))
            start_date = datetime.strptime(
                start_date_str, '%b %d, %Y').strftime('%d %B %Y')
            end_date = datetime.strptime(
                end_date_str, '%b %d, %Y').strftime('%d %B %Y')
            return f"{start_date} - {end_date}"
        else:
            return datetime.strptime(date_str, '%b %d, %Y').strftime('%d %B %Y')

    async def check_forum_threads(self, guild, interaction, new_entries):
        gigchats_id = self.config["gigchats_id"]
        gigchats_channel = guild.get_channel(gigchats_id)

        if gigchats_channel is None:
            logging.error(f"Channel with ID {gigchats_id} not found.")
            await interaction.followup.send("The specified channel was not found.")
            return

        new_threads_created = 0
        all_entries = self.load_existing_entries()

        for entry in all_entries:
            event_date = entry[0]  # already normalised
            venue = entry[1]
            location = entry[2]

            exists = await self.thread_exists(gigchats_channel, event_date.title())
            logging.info(
                f"Does thread '{event_date.title()}' exist in channel '{gigchats_channel.name}'? {exists}")

            if not exists:
                try:
                    title_case_event_date = event_date.title()
                    content = f"The Last Dinner Party at {venue.title()}, {location.title()}"
                    logging.info(
                        f"Creating thread for: {title_case_event_date}")
                    await gigchats_channel.create_thread(name=title_case_event_date, content=content, auto_archive_duration=60)
                    new_threads_created += 1
                    logging.info(
                        f"Successfully created thread: {title_case_event_date}")
                    await asyncio.sleep(5)
                except discord.Forbidden:
                    logging.error(
                        f"Permission denied when trying to create thread '{title_case_event_date}'")
                except discord.HTTPException as e:
                    logging.error(
                        f"Failed to create thread '{title_case_event_date}': {e}")

        await self.send_summary(interaction, new_threads_created)

    async def send_summary(self, interaction, new_threads_created):
        if new_threads_created > 0:
            logging.info(f"{new_threads_created} new threads created.")
            embed = discord.Embed(
                title=f"{new_threads_created} new threads created",
                description="New show threads have been created for upcoming events.",
                color=discord.Color.green()
            )
        else:
            logging.info("No new threads created.\n")
            embed = discord.Embed(
                title="No new threads created",
                description="All existing events already have threads.",
                color=discord.Color.blurple()
            )
        await interaction.followup.send(embed=embed)

    async def thread_exists(self, channel, title):
        return discord.utils.get(channel.threads, name=title) is not None


async def setup(bot):
    await bot.add_cog(Scrape(bot))
