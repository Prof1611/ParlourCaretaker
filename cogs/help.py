import discord
import logging
from discord import app_commands
from discord.ext import commands
import datetime
from typing import Optional, List, Tuple

# Discord embed limits
EMBED_TOTAL_CHAR_LIMIT = 6000
EMBED_DESCRIPTION_LIMIT = 4096
EMBED_TITLE_LIMIT = 256
EMBED_FIELD_NAME_LIMIT = 256
EMBED_FIELD_VALUE_LIMIT = 1024
EMBED_MAX_FIELDS = 25


def audit_log(message: str):
    """Append a timestamped message to the audit log file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("audit.log", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


def embed_length(embed: discord.Embed) -> int:
    """Estimate total characters in an embed to avoid hitting the global 6000 character cap."""
    total = 0
    if embed.title:
        total += len(embed.title)
    if embed.description:
        total += len(embed.description)
    if embed.footer and embed.footer.text:
        total += len(embed.footer.text)
    if embed.author and embed.author.name:
        total += len(embed.author.name)
    for f in embed.fields:
        total += len(f.name or "")
        total += len(f.value or "")
    return total


def chunk_field_value(text: str, limit: int = EMBED_FIELD_VALUE_LIMIT) -> List[str]:
    """Split a long field value into chunks that fit the per-field value limit."""
    if len(text) <= limit:
        return [text]
    parts: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + limit, len(text))
        newline_pos = text.rfind("\n", start, end)
        if newline_pos != -1 and newline_pos > start:
            parts.append(text[start:newline_pos])
            start = newline_pos + 1
        else:
            parts.append(text[start:end])
            start = end
    return parts


class PagedView(discord.ui.View):
    """Button view that paginates through a list of embeds. Restricted to the requesting user."""

    def __init__(
        self, user_id: int, pages: List[discord.Embed], timeout: Optional[float] = 120
    ):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.pages = pages
        self.index = 0
        self._update_button_states()

    def _update_button_states(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "first":
                    child.disabled = self.index == 0
                elif child.custom_id == "prev":
                    child.disabled = self.index == 0
                elif child.custom_id == "next":
                    child.disabled = self.index >= len(self.pages) - 1
                elif child.custom_id == "last":
                    child.disabled = self.index >= len(self.pages) - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "Only the requester can use these buttons.", ephemeral=True
            )
            return False
        return True

    async def _show(self, interaction: discord.Interaction):
        self._update_button_states()
        try:
            await interaction.response.edit_message(
                embed=self.pages[self.index], view=self
            )
        except discord.InteractionResponded:
            await interaction.edit_original_response(
                embed=self.pages[self.index], view=self
            )

    @discord.ui.button(
        label="⏮ First", style=discord.ButtonStyle.secondary, custom_id="first"
    )
    async def first(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = 0
        await self._show(interaction)

    @discord.ui.button(
        label="◀ Previous", style=discord.ButtonStyle.secondary, custom_id="prev"
    )
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.index > 0:
            self.index -= 1
        await self._show(interaction)

    @discord.ui.button(
        label="Next ▶", style=discord.ButtonStyle.secondary, custom_id="next"
    )
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.index < len(self.pages) - 1:
            self.index += 1
        await self._show(interaction)

    @discord.ui.button(
        label="Last ⏭", style=discord.ButtonStyle.secondary, custom_id="last"
    )
    async def last(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = len(self.pages) - 1
        await self._show(interaction)


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info("\033[96mHelp\033[0m cog synced successfully.")
        audit_log("Help cog synced successfully.")

    def _new_list_embed(self) -> discord.Embed:
        return discord.Embed(
            title="List of Commands",
            description="Use `/help [command]` to see detailed info about a command.",
            color=discord.Color.blurple(),
        )

    def build_command_list_pages(
        self, commands_list: List[Tuple[str, str]]
    ) -> List[discord.Embed]:
        """Build paginated embeds for the full command list with hard field and char caps."""
        pages: List[discord.Embed] = []
        current = self._new_list_embed()
        fields_on_page = 0

        for name, desc in commands_list:
            field_name = (name or "unknown")[:EMBED_FIELD_NAME_LIMIT]
            field_value = (desc or "No description available.")[
                :EMBED_FIELD_VALUE_LIMIT
            ]

            if (
                fields_on_page >= EMBED_MAX_FIELDS
                or (embed_length(current) + len(field_name) + len(field_value))
                > EMBED_TOTAL_CHAR_LIMIT
            ):
                pages.append(current)
                current = self._new_list_embed()
                fields_on_page = 0

            current.add_field(name=field_name, value=field_value, inline=False)
            fields_on_page += 1

        if fields_on_page > 0 or not pages:
            pages.append(current)

        total = len(pages)
        for idx, emb in enumerate(pages, start=1):
            emb.set_footer(text=f"Page {idx} of {total}")

        return pages

    def _new_detail_embed(self, cmd_name: str) -> discord.Embed:
        return discord.Embed(
            title=f"Help for /{cmd_name}",
            color=discord.Color.blurple(),
        )

    def build_detailed_command_pages(
        self, cmd: app_commands.Command
    ) -> List[discord.Embed]:
        """Build paginated embeds for a specific command with strict caps."""
        pages: List[discord.Embed] = []
        current = self._new_detail_embed(cmd.name)
        fields_on_page = 0

        desc = cmd.description or "No description available."
        if len(desc) <= EMBED_DESCRIPTION_LIMIT:
            current.description = desc
        else:
            current.description = desc[:EMBED_DESCRIPTION_LIMIT]
            remain = desc[EMBED_DESCRIPTION_LIMIT:]
            for chunk in chunk_field_value(remain):
                if (
                    fields_on_page >= EMBED_MAX_FIELDS
                    or (embed_length(current) + len(chunk)) > EMBED_TOTAL_CHAR_LIMIT
                ):
                    pages.append(current)
                    current = self._new_detail_embed(cmd.name)
                    fields_on_page = 0
                current.add_field(
                    name="Description (continued)", value=chunk, inline=False
                )
                fields_on_page += 1

        option_lines: List[str] = []
        params = getattr(cmd, "parameters", None)
        if params:
            if isinstance(params, dict):
                for name, param in params.items():
                    required = getattr(param, "required", False)
                    pdesc = (
                        getattr(param, "description", "") or "No description provided."
                    )
                    option_lines.append(
                        f"`{name}` ({'Required' if required else 'Optional'}) - {pdesc}"
                    )
            elif isinstance(params, list):
                for param in params:
                    required = getattr(param, "required", False)
                    pdesc = (
                        getattr(param, "description", "") or "No description provided."
                    )
                    pname = getattr(param, "name", "unknown")
                    option_lines.append(
                        f"`{pname}` ({'Required' if required else 'Optional'}) - {pdesc}"
                    )

        if option_lines:
            options_text = "\n".join(option_lines)
            chunks = chunk_field_value(options_text, EMBED_FIELD_VALUE_LIMIT)
            for i, chunk in enumerate(chunks, start=1):
                field_name = "Arguments" if i == 1 else f"Arguments (continued {i})"
                if (
                    fields_on_page >= EMBED_MAX_FIELDS
                    or (embed_length(current) + len(chunk)) > EMBED_TOTAL_CHAR_LIMIT
                ):
                    pages.append(current)
                    current = self._new_detail_embed(cmd.name)
                    fields_on_page = 0
                current.add_field(name=field_name, value=chunk, inline=False)
                fields_on_page += 1
        else:
            if fields_on_page >= EMBED_MAX_FIELDS:
                pages.append(current)
                current = self._new_detail_embed(cmd.name)
                fields_on_page = 0
            current.add_field(
                name="Arguments",
                value="This command does not have any arguments.",
                inline=False,
            )
            fields_on_page += 1

        pages.append(current)

        total = len(pages)
        for idx, emb in enumerate(pages, start=1):
            emb.set_footer(text=f"Page {idx} of {total}")

        return pages

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
                if (
                    isinstance(cmd, app_commands.Command)
                    and cmd.name.lower() == command.lower()
                ):
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
