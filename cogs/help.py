import discord
import logging
from discord import app_commands
from discord.ext import commands
import datetime
from typing import Optional


def audit_log(message: str):
    """Append a timestamped message to the audit log file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("audit.log", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info("\033[96mHelp\033[0m cog synced successfully.")
        audit_log("Help cog synced successfully.")

    @app_commands.command(
        name="help",
        description="Displays a list of commands or detailed info about a specific command.",
    )
    @app_commands.describe(
        command="Optional: The name of the command for detailed help."
    )
    async def help(
        self, interaction: discord.Interaction, command: Optional[str] = None
    ):
        # Do not defer response to avoid delay; this command should respond immediately.
        if command is None:
            # Build a list of all commands.
            embed = discord.Embed(
                title="List of Commands:",
                description="Use `/help [command]` to see detailed info about a command.",
                color=discord.Color.blurple(),
            )
            for cmd in self.bot.tree.walk_commands():
                cmd_name = cmd.name
                cmd_desc = (
                    cmd.description if cmd.description else "No description available."
                )
                embed.add_field(name=cmd_name, value=cmd_desc, inline=False)
            try:
                await interaction.response.send_message(embed=embed, ephemeral=True)
            except discord.NotFound:
                logging.warning("Interaction expired when sending command list.")
            audit_log(
                f"{interaction.user.name} (ID: {interaction.user.id}) requested a list of commands."
            )
        else:
            # Search for the command (case-insensitive)
            found_command = None
            for cmd in self.bot.tree.walk_commands():
                if cmd.name.lower() == command.lower():
                    found_command = cmd
                    break

            if found_command:
                embed = discord.Embed(
                    title=f"Help for /{found_command.name}",
                    color=discord.Color.blurple(),
                )
                embed.add_field(
                    name="Description",
                    value=found_command.description or "No description available.",
                    inline=False,
                )
                # Display arguments (parameters) if available.
                if hasattr(found_command, "parameters") and found_command.parameters:
                    if isinstance(found_command.parameters, dict):
                        option_texts = []
                        for name, param in found_command.parameters.items():
                            req = "Required" if param.required else "Optional"
                            opt_desc = (
                                param.description
                                if param.description
                                else "No description provided."
                            )
                            option_texts.append(f"`{name}` ({req}) - {opt_desc}")
                        embed.add_field(
                            name="Arguments",
                            value="\n".join(option_texts),
                            inline=False,
                        )
                    elif isinstance(found_command.parameters, list):
                        option_texts = []
                        for param in found_command.parameters:
                            req = "Required" if param.required else "Optional"
                            opt_desc = (
                                param.description
                                if param.description
                                else "No description provided."
                            )
                            option_texts.append(f"`{param.name}` ({req}) - {opt_desc}")
                        embed.add_field(
                            name="Arguments",
                            value="\n".join(option_texts),
                            inline=False,
                        )
                else:
                    embed.add_field(
                        name="Arguments",
                        value="This command does not have any arguments.",
                        inline=False,
                    )
                try:
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                except discord.NotFound:
                    logging.warning(
                        "Interaction expired when sending detailed command help."
                    )
                audit_log(
                    f"{interaction.user.name} (ID: {interaction.user.id}) requested detailed help for /{found_command.name}."
                )
            else:
                embed = discord.Embed(
                    title="Command Not Found",
                    description=f"No command named `{command}` was found.",
                    color=discord.Color.red(),
                )
                try:
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                except discord.NotFound:
                    logging.warning(
                        "Interaction expired when sending 'Command Not Found' message."
                    )
                audit_log(
                    f"{interaction.user.name} (ID: {interaction.user.id}) requested help for unknown command: {command}."
                )


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
