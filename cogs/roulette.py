import discord
import random
import sqlite3
import logging
import yaml
from discord.ext import commands
from discord import app_commands

# Database setup – using the same database file for both cogs.
conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS roulette_players (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        wins INTEGER DEFAULT 0,
        losses INTEGER DEFAULT 0,
        streak INTEGER DEFAULT 0,
        plays INTEGER DEFAULT 0
    )
    """
)
conn.commit()


class Roulette(commands.Cog):
    """
    A Discord cog for a roulette game with improved error handling, type hints, documentation,
    command cooldowns, and configurable win/loss/mystery fates loaded from config.yaml.
    """

    def __init__(self, bot: commands.Bot) -> None:
        """
        Initialise the Roulette cog.

        :param bot: The instance of the Discord bot.
        """
        self.bot = bot
        # Load configuration from config.yaml for roulette fates.
        try:
            with open("config.yaml", "r", encoding="utf-8") as config_file:
                self.config = yaml.safe_load(config_file)
        except Exception as e:
            logging.error(f"Failed to load configuration file: {e}")
            raise

        # Rely solely on the configuration file for roulette fates.
        try:
            self.winning_fates = self.config["roulette_fates"]["winning"]
            self.losing_fates = self.config["roulette_fates"]["losing"]
            self.mystery_fates = self.config["roulette_fates"]["mystery"]
        except KeyError as e:
            logging.error(f"Missing required roulette fate configuration: {e}")
            raise

    @app_commands.command(
        name="roulette", description="Take a risk and roll for your fate!"
    )
    @commands.cooldown(1, 10, commands.BucketType.user)  # 1 use per 10 seconds per user
    async def roulette(self, interaction: discord.Interaction) -> None:
        """
        Executes the roulette command, randomly choosing a win, loss, or mystery fate.
        Updates the player's stats and sends an embed message with the result.

        :param interaction: The Discord interaction object.
        """
        try:
            user_id: int = interaction.user.id
            fate_type: str = random.choice(["win", "loss", "mystery"])

            if fate_type == "win":
                fate: str = random.choice(self.winning_fates)
                embed_color = discord.Color.green()
            elif fate_type == "loss":
                fate = random.choice(self.losing_fates)
                embed_color = discord.Color.red()
            else:
                fate = random.choice(self.mystery_fates)
                embed_color = discord.Color.gold()

            # Update player stats regardless of the outcome.
            self.update_stats(user_id, fate_type, interaction.user.display_name)

            embed = discord.Embed(
                title="🎲 Nothing Matters Roulette 🎲",
                description=f"{fate}",
                color=embed_color,
            )
            await interaction.response.send_message(embed=embed)
        except sqlite3.Error as db_err:
            logging.error(f"Database error for user {interaction.user.id}: {db_err}")
            error_embed = discord.Embed(
                title="Database Error",
                description="An error occurred while updating your stats. Please try again later.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=error_embed)
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            error_embed = discord.Embed(
                title="Error",
                description="Failed to process your roulette roll. Please try again later.",
                color=discord.Color.red(),
            )
            try:
                await interaction.response.send_message(embed=error_embed)
            except Exception as inner_e:
                logging.error(f"Error sending error message: {inner_e}")

    @app_commands.command(
        name="roulette_stats", description="Check your roulette game stats!"
    )
    @commands.cooldown(1, 5, commands.BucketType.user)  # 1 use per 5 seconds per user
    async def stats(self, interaction: discord.Interaction) -> None:
        """
        Displays the player's roulette stats including wins, losses, plays and current streak.

        :param interaction: The Discord interaction object.
        """
        try:
            user_id: int = interaction.user.id
            cursor.execute(
                "SELECT wins, losses, streak, plays FROM roulette_players WHERE user_id = ?",
                (user_id,),
            )
            result = cursor.fetchone()

            if result:
                wins, losses, streak, plays = result
                win_rate = (wins / plays) * 100 if plays > 0 else 0

                if streak > 1:
                    streak_display = f"Winning streak of {streak}!"
                elif streak < -1:
                    streak_display = f"Losing streak of {abs(streak)}!"
                else:
                    streak_display = "No current streak..."

                embed = discord.Embed(
                    title=f"📊 {interaction.user.display_name}'s Roulette Stats 📊",
                    color=discord.Color.blurple(),
                )
                embed.set_author(
                    name=interaction.user.display_name,
                    icon_url=interaction.user.display_avatar.url,
                )
                embed.add_field(name="🏹 Plays", value=plays, inline=True)
                embed.add_field(name="🏅 Wins", value=wins, inline=True)
                embed.add_field(name="🥀 Losses", value=losses, inline=True)
                embed.add_field(
                    name="🎯 Win Rate", value=f"{win_rate:.1f}%", inline=True
                )
                embed.add_field(name="🔥 Streak", value=streak_display, inline=False)
                embed.set_footer(text="Keep spinning your fate and chase those wins!")
            else:
                embed = discord.Embed(
                    title="No Data Found",
                    description="You haven't played yet! Use `/roulette` to start your journey.",
                    color=discord.Color.red(),
                )

            await interaction.response.send_message(embed=embed)
        except sqlite3.Error as db_err:
            logging.error(
                f"Database error fetching stats for user {interaction.user.id}: {db_err}"
            )
            error_embed = discord.Embed(
                title="Database Error",
                description="Failed to retrieve your stats due to a database error. Please try again later.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=error_embed)
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            error_embed = discord.Embed(
                title="Error",
                description="Failed to retrieve your roulette stats. Please try again later.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=error_embed)

    @app_commands.command(
        name="roulette_leaderboard",
        description="Display the top 10 players in roulette!",
    )
    @commands.cooldown(1, 10, commands.BucketType.user)  # 1 use per 10 seconds per user
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        """
        Displays the top 10 players in the roulette game based on wins.

        :param interaction: The Discord interaction object.
        """
        try:
            cursor.execute(
                "SELECT user_id, username, wins, plays FROM roulette_players ORDER BY wins DESC LIMIT 10"
            )
            results = cursor.fetchall()

            if results:
                description: str = ""
                for idx, (user_id, username, wins, plays) in enumerate(
                    results, start=1
                ):
                    win_rate = (wins / plays) * 100 if plays > 0 else 0
                    description += f"**{idx}. {username}** - Wins: {wins}, Win Rate: {win_rate:.1f}%\n"
                embed = discord.Embed(
                    title="🏅 Roulette Leaderboard 🏅",
                    description=description,
                    color=discord.Color.blurple(),
                )
            else:
                embed = discord.Embed(
                    title="Error",
                    description="No players found.",
                    color=discord.Color.red(),
                )

            await interaction.response.send_message(embed=embed)
        except sqlite3.Error as db_err:
            logging.error(f"Database error fetching leaderboard: {db_err}")
            error_embed = discord.Embed(
                title="Database Error",
                description="Failed to retrieve leaderboard due to a database error. Please try again later.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=error_embed)
        except Exception as e:
            logging.error(f"Unexpected error in leaderboard: {e}")
            error_embed = discord.Embed(
                title="Error",
                description="Failed to retrieve leaderboard. Please try again later.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=error_embed)

    def update_stats(self, user_id: int, outcome: str, username: str) -> None:
        """
        Updates the player's statistics in the database based on the outcome.

        :param user_id: The Discord user's ID.
        :param outcome: The outcome of the roulette spin ('win', 'loss', or 'mystery').
        :param username: The display name of the user.
        """
        try:
            cursor.execute(
                "SELECT wins, losses, streak, plays FROM roulette_players WHERE user_id = ?",
                (user_id,),
            )
            result = cursor.fetchone()

            if result:
                wins, losses, streak, plays = result
            else:
                wins, losses, streak, plays = 0, 0, 0, 0

            plays += 1
            if outcome == "win":
                wins += 1
                streak = streak + 1 if streak >= 0 else 1
            elif outcome == "loss":
                losses += 1
                streak = streak - 1 if streak <= 0 else -1

            cursor.execute(
                "REPLACE INTO roulette_players (user_id, username, wins, losses, streak, plays) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, username, wins, losses, streak, plays),
            )
            conn.commit()
        except sqlite3.Error as db_err:
            logging.error(f"Database error updating stats for user {user_id}: {db_err}")
        except Exception as e:
            logging.error(f"Unexpected error updating stats for user {user_id}: {e}")

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """
        Logs that the Roulette cog has been successfully synced.
        """
        logging.info("\033[96mRoulette\033[0m cog synced successfully.")


async def setup(bot: commands.Bot) -> None:
    """
    Asynchronously adds the Roulette cog to the bot.

    :param bot: The instance of the Discord bot.
    """
    await bot.add_cog(Roulette(bot))
