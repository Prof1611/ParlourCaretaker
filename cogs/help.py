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
        if command is None:
            # Get all commands
            commands_list = list(self.bot.tree.walk_commands())
            embeds = []

            # Create embeds with max 25 fields each
            for i in range(0, len(commands_list), 25):
                embed = discord.Embed(
                    title="List of Commands:",
                    description="Use `/help [command]` to see detailed info about a command.",
                    color=discord.Color.blurple(),
                )
                for cmd in commands_list[i:i+25]:
                    cmd_name = cmd.name
                    cmd_desc = cmd.description or "No description available."
                    embed.add_field(name=cmd_name, value=cmd_desc, inline=False)
                embeds.append(embed)

            # Send first embed as main response
            await interaction.response.send_message(embed=embeds[0], ephemeral=True)

            # Send any extra pages as followups
            for extra_embed in embeds[1:]:
                await interaction.followup.send(embed=extra_embed, ephemeral=True)

            audit_log(
                f"{interaction.user.name} (ID: {interaction.user.id}) requested a list of commands."
            )

        else:
            # Search for specific command
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

                # Display arguments if available
                if hasattr(found_command, "parameters") and found_command.parameters:
                    option_texts = []
                    if isinstance(found_command.parameters, dict):
                        for name, param in found_command.parameters.items():
                            req = "Required" if param.required else "Optional"
                            opt_desc = param.description or "No description provided."
                            option_texts.append(f"`{name}` ({req}) - {opt_desc}")
                    elif isinstance(found_command.parameters, list):
                        for param in found_command.parameters:
                            req = "Required" if param.required else "Optional"
                            opt_desc = param.description or "No description provided."
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

                await interaction.response.send_message(embed=embed, ephemeral=True)
                audit_log(
                    f"{interaction.user.name} (ID: {interaction.user.id}) requested detailed help for /{found_command.name}."
                )

            else:
                embed = discord.Embed(
                    title="Command Not Found",
                    description=f"No command named `{command}` was found.",
                    color=discord.Color.red(),
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                audit_log(
                    f"{interaction.user.name} (ID: {interaction.user.id}) requested help for unknown command: {command}."
                )


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
