import discord
import random
import sqlite3
import logging
import yaml
from discord.ext import commands
from discord import app_commands
import datetime

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


def audit_log(message: str):
    """Append a timestamped message to the audit log file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("audit.log", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


class MysteryView(discord.ui.View):
    def __init__(self, cog: "Roulette", actor: discord.User):
        super().__init__(timeout=60)
        self.cog = cog
        self.actor = actor

    @discord.ui.button(label="Roll Again", style=discord.ButtonStyle.primary)
    async def roll_again(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        fate_type, fate, embed_color = self.cog.get_roulette_outcome()
        user_id = interaction.user.id
        self.cog.update_stats(user_id, fate_type, interaction.user.display_name)
        embed = discord.Embed(
            title="🎲 Nothing Matters Roulette 🎲",
            description=f"{fate}",
            color=embed_color,
        )
        await interaction.response.send_message(embed=embed)
        audit_log(
            f"{interaction.user.name} (ID: {interaction.user.id}) re-rolled and received a {fate_type.upper()} outcome: {fate}."
        )

    @discord.ui.button(label="View Your Stats", style=discord.ButtonStyle.secondary)
    async def view_stats(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.cog.stats_callback(interaction)


class StatsLeaderboardView(discord.ui.View):
    def __init__(self, cog: "Roulette", actor: discord.User):
        super().__init__(timeout=60)
        self.cog = cog
        self.actor = actor

    @discord.ui.button(label="View Your Stats", style=discord.ButtonStyle.primary)
    async def view_stats(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.cog.stats_callback(interaction)

    @discord.ui.button(label="View Leaderboard", style=discord.ButtonStyle.secondary)
    async def leaderboard(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.cog.leaderboard_callback(interaction)


class Roulette(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        try:
            with open("config.yaml", "r", encoding="utf-8") as config_file:
                self.config = yaml.safe_load(config_file)
            self.winning_fates = self.config["roulette_fates"]["winning"]
            self.losing_fates = self.config["roulette_fates"]["losing"]
            self.mystery_fates = self.config["roulette_fates"]["mystery"]
            # Load outcome probabilities; default to equal weights if not found.
            self.probabilities = self.config.get(
                "roulette_probabilities", {"win": 1, "loss": 1, "mystery": 1}
            )
        except Exception as e:
            logging.error(f"Failed to load roulette configuration: {e}")
            raise

    def get_roulette_outcome(self):
        # Use the probabilities from config (or default equal weights)
        outcomes = ["win", "loss", "mystery"]
        weights = [
            self.probabilities.get("win", 1),
            self.probabilities.get("loss", 1),
            self.probabilities.get("mystery", 1),
        ]
        fate_type = random.choices(outcomes, weights=weights, k=1)[0]

        if fate_type == "win":
            fate = random.choice(self.winning_fates)
            embed_color = discord.Color.green()
        elif fate_type == "loss":
            fate = random.choice(self.losing_fates)
            embed_color = discord.Color.red()
        else:
            fate = random.choice(self.mystery_fates)
            embed_color = discord.Color.gold()
        return fate_type, fate, embed_color

    async def stats_callback(self, interaction: discord.Interaction):
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
            embed.add_field(name="🎯 Win Rate", value=f"{win_rate:.1f}%", inline=True)
            embed.add_field(name="🔥 Streak", value=streak_display, inline=False)
            embed.set_footer(text="Keep spinning your fate and chase those wins!")
        else:
            embed = discord.Embed(
                title="No Data Found",
                description="You haven't played yet! Use `/roulette` to start your journey.",
                color=discord.Color.red(),
            )
        await interaction.response.send_message(embed=embed)
        audit_log(
            f"{interaction.user.name} (ID: {interaction.user.id}) viewed their roulette stats."
        )

    async def leaderboard_callback(self, interaction: discord.Interaction):
        cursor.execute(
            "SELECT user_id, username, wins, plays FROM roulette_players ORDER BY wins DESC LIMIT 10"
        )
        results = cursor.fetchall()
        if results:
            description: str = ""
            for idx, (user_id, username, wins, plays) in enumerate(results, start=1):
                win_rate = (wins / plays) * 100 if plays > 0 else 0
                description += (
                    f"**{idx}. {username}** - Wins: {wins}, Win Rate: {win_rate:.1f}%\n"
                )
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
        audit_log(
            f"{interaction.user.name} (ID: {interaction.user.id}) viewed the roulette leaderboard."
        )

    @app_commands.command(
        name="roulette", description="Take a risk and roll for your fate!"
    )
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def roulette(self, interaction: discord.Interaction) -> None:
        actor = interaction.user
        audit_log(
            f"{actor.name} (ID: {actor.id}) invoked /roulette in guild '{interaction.guild.name}' (ID: {interaction.guild.id})."
        )
        try:
            user_id: int = actor.id
            fate_type, fate, embed_color = self.get_roulette_outcome()

            # Update player stats regardless of the outcome.
            self.update_stats(user_id, fate_type, actor.display_name)
            audit_log(
                f"{actor.name} (ID: {actor.id}) rolled {fate_type.upper()} and received outcome: {fate}."
            )

            embed = discord.Embed(
                title="🎲 Nothing Matters Roulette 🎲",
                description=f"{fate}",
                color=embed_color,
            )
            # Choose the appropriate view based on outcome.
            if fate_type == "mystery":
                view = MysteryView(self, actor)
            else:
                view = StatsLeaderboardView(self, actor)
            await interaction.response.send_message(embed=embed, view=view)
        except Exception as e:
            logging.error(f"Discord API Error. Error: {e}")
            audit_log(
                f"{actor.name} (ID: {actor.id}) encountered error in /roulette: {e}"
            )
            error_embed = discord.Embed(
                title="Error",
                description="Failed to process your roulette roll. Please try again later.",
                color=discord.Color.red(),
            )
            try:
                await interaction.response.send_message(embed=error_embed)
            except Exception:
                pass

    @app_commands.command(
        name="roulette_stats", description="Check your roulette game stats!"
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def stats(self, interaction: discord.Interaction) -> None:
        actor = interaction.user
        audit_log(
            f"{actor.name} (ID: {actor.id}) invoked /roulette_stats in guild '{interaction.guild.name}' (ID: {interaction.guild.id})."
        )
        try:
            user_id: int = actor.id
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
                    title=f"📊 {actor.display_name}'s Roulette Stats 📊",
                    color=discord.Color.blurple(),
                )
                embed.set_author(
                    name=actor.display_name, icon_url=actor.display_avatar.url
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
        except Exception as e:
            logging.error(f"Discord API Error. Error: {e}")
            audit_log(
                f"{actor.name} (ID: {actor.id}) encountered error in /roulette_stats: {e}"
            )
            error_embed = discord.Embed(
                title="Error",
                description="Failed to retrieve your roulette stats. Please try again later.",
                color=discord.Color.red(),
            )
            try:
                await interaction.response.send_message(embed=error_embed)
            except Exception:
                pass

    @app_commands.command(
        name="roulette_leaderboard",
        description="Display the top 10 players in roulette!",
    )
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        actor = interaction.user
        audit_log(
            f"{actor.name} (ID: {actor.id}) invoked /roulette_leaderboard in guild '{interaction.guild.name}' (ID: {interaction.guild.id})."
        )
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
        except Exception as e:
            logging.error(f"Discord API Error. Error in leaderboard: {e}")
            audit_log(
                f"{actor.name} (ID: {actor.id}) encountered error in /roulette_leaderboard: {e}"
            )
            error_embed = discord.Embed(
                title="Error",
                description="Failed to retrieve leaderboard. Please try again later.",
                color=discord.Color.red(),
            )
            try:
                await interaction.response.send_message(embed=error_embed)
            except Exception:
                pass

    @app_commands.command(
        name="roulette_update", description="Manually adjust a player's roulette stats."
    )
    async def roulette_update(
        self,
        interaction: discord.Interaction,
        target: discord.User,
        wins: int,
        losses: int,
        streak: int,
        plays: int,
    ):
        """Allows adjustment of a player's stats."""
        try:
            cursor.execute(
                "REPLACE INTO roulette_players (user_id, username, wins, losses, streak, plays) VALUES (?, ?, ?, ?, ?, ?)",
                (target.id, target.display_name, wins, losses, streak, plays),
            )
            conn.commit()
            embed = discord.Embed(
                title="✅ Stats Updated",
                description=(
                    f"Updated stats for {target.display_name}:\nWins: {wins}\nLosses: {losses}\nStreak: {streak}\nPlays: {plays}"
                ),
                color=discord.Color.green(),
            )
            await interaction.response.send_message(embed=embed)
            audit_log(
                f"{interaction.user.name} (ID: {interaction.user.id}) updated stats for {target.display_name} (ID: {target.id}) to Wins: {wins}, Losses: {losses}, Streak: {streak}, Plays: {plays}."
            )
        except Exception as e:
            logging.error(f"Error updating stats via command: {e}")
            audit_log(
                f"Error by {interaction.user.name} (ID: {interaction.user.id}) while updating stats for user ID {target.id}: {e}"
            )
            error_embed = discord.Embed(
                title="❌ Error",
                description="Failed to update player stats. Please check the parameters and try again.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=error_embed)

    @app_commands.command(
        name="roulette_global_stats",
        description="Display global roulette statistics, outcome probabilities, and future projections.",
    )
    async def global_stats(self, interaction: discord.Interaction):
        """Shows overall game statistics along with outcome probabilities and projections for future plays."""
        try:
            cursor.execute(
                "SELECT SUM(wins), SUM(losses), SUM(plays) FROM roulette_players"
            )
            result = cursor.fetchone()
            total_wins, total_losses, total_plays = result if result else (0, 0, 0)

            cursor.execute("SELECT COUNT(*) FROM roulette_players")
            total_players = cursor.fetchone()[0]

            if total_plays == 0:
                embed = discord.Embed(
                    title="Global Roulette Statistics",
                    description="No data available yet. Start playing to generate statistics!",
                    color=discord.Color.red(),
                )
                await interaction.response.send_message(embed=embed)
                return

            mystery_outcomes = total_plays - (total_wins + total_losses)
            win_prob = total_wins / total_plays
            loss_prob = total_losses / total_plays
            mystery_prob = mystery_outcomes / total_plays

            future_plays = 1000
            projected_wins = win_prob * future_plays
            projected_losses = loss_prob * future_plays
            projected_mystery = mystery_prob * future_plays

            embed = discord.Embed(
                title="🌐 Global Roulette Statistics 🌐",
                color=discord.Color.blurple(),
            )
            embed.add_field(name="Total Plays", value=total_plays, inline=False)
            embed.add_field(name="Total Wins", value=total_wins, inline=True)
            embed.add_field(name="Total Losses", value=total_losses, inline=True)
            embed.add_field(
                name="Total Mystery Outcomes", value=mystery_outcomes, inline=True
            )
            embed.add_field(name="Total Players", value=total_players, inline=False)
            embed.add_field(
                name="Outcome Probabilities",
                value=(
                    f"Win: {win_prob*100:.1f}%\nLoss: {loss_prob*100:.1f}%\nMystery: {mystery_prob*100:.1f}%"
                ),
                inline=False,
            )
            embed.add_field(
                name="Projections (Next 1,000 Plays)",
                value=(
                    f"Projected Wins: {projected_wins:.0f}\nProjected Losses: {projected_losses:.0f}\nProjected Mystery: {projected_mystery:.0f}"
                ),
                inline=False,
            )
            embed.set_footer(
                text="These projections are based on current outcome probabilities."
            )
            await interaction.response.send_message(embed=embed)
            audit_log(
                f"{interaction.user.name} (ID: {interaction.user.id}) viewed global roulette statistics."
            )
        except Exception as e:
            logging.error(f"Error fetching global statistics: {e}")
            audit_log(
                f"Error in /roulette_global_stats by {interaction.user.name} (ID: {interaction.user.id}): {e}"
            )
            error_embed = discord.Embed(
                title="❌ Error",
                description="Failed to retrieve global statistics. Please try again later.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=error_embed)

    def update_stats(self, user_id: int, outcome: str, username: str) -> None:
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
        except Exception as e:
            logging.error(
                f"Discord API Error. Error updating stats for user {user_id}: {e}"
            )
            audit_log(f"Error updating stats for user ID {user_id}: {e}")

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        logging.info("\033[96mRoulette\033[0m cog synced successfully.")
        audit_log("Roulette cog synced successfully.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Roulette(bot))
