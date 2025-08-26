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


def _is_channel_nsfw(channel: Optional[discord.abc.GuildChannel]) -> bool:
    """Best effort NSFW check for text channels and threads."""
    if channel is None:
        return False
    if isinstance(channel, discord.TextChannel):
        return channel.is_nsfw()
    if isinstance(channel, discord.Thread):
        parent = channel.parent
        return bool(parent and parent.is_nsfw())
    if isinstance(channel, discord.ForumChannel):
        return channel.is_nsfw()
    return False


def _user_has_required_perms(member: discord.Member, required: discord.Permissions) -> bool:
    """Return True if member's guild permissions satisfy all required bits."""
    if member.guild is None:
        return False
    # Administrators implicitly have all permissions
    if member.guild_permissions.administrator:
        return True
    # Permissions has a value bitfield; ensure all required bits are present
    user_bits = member.guild_permissions.value
    req_bits = required.value
    return (user_bits & req_bits) == req_bits


def can_user_run_command(
    interaction: discord.Interaction, cmd: app_commands.Command
) -> bool:
    """
    Heuristic filter for whether the invoking user can use this command here.
    Notes and limitations:
    - Respects dm_permission, NSFW flag, and default_member_permissions.
    - Cannot read role allow/deny restrictions configured in Server Settings → Integrations.
    """
    # DM availability
    if interaction.guild is None:
        # In DMs only allow commands with dm_permission True
        if hasattr(cmd, "dm_permission") and cmd.dm_permission is False:
            return False
    else:
        # In guilds only: if command forbids DMs, that is fine; we are in a guild.
        pass

    # NSFW-only command must be used in an NSFW channel
    if getattr(cmd, "nsfw", False):
        if interaction.guild is None:
            return False
        if not _is_channel_nsfw(interaction.channel):  # type: ignore[arg-type]
            return False

    # Default member permissions check (guild only)
    if interaction.guild is not None:
        req_perms = getattr(cmd, "default_member_permissions", None)
        if isinstance(req_perms, discord.Permissions):
            member = interaction.user
            if isinstance(member, discord.Member):
                if not _user_has_required_perms(member, req_perms):
                    return False
            else:
                # If for some reason we do not have a Member object, be conservative
                return False

    # If the command is part of a guild and command is disabled at guild scope,
    # discord.py does not expose that directly; we cannot check it here.

    return True


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

    @commands.Cog.listener())
    async def on_ready(self):
        logging.info("\033[96mHelp\033[0m cog synced successfully.")
        audit_log("Help cog synced successfully.")

    def _new_list_embed(self) -> discord.Embed:
        return discord.Embed(
            title="List of Commands",
            description="Only commands you can use here are shown. Use `/help [command]` for details.",
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

    def _collect_visible_commands(
        self, interaction: discord.Interaction
    ) -> List[app_commands.Command]:
        """Return commands the invoking user can reasonably run here."""
        visible: List[app_commands.Command] = []
        for cmd in self.bot.tree.walk_commands():
            if not isinstance(cmd, app_commands.Command):
                continue
            # Hide context menu commands in this help, only slash commands
            if getattr(cmd, "guild_only", False) and interaction.guild is None:
                # discord.py sets dm_permission False for guild_only. Covered next.
                pass
            if can_user_run_command(interaction, cmd):
                visible.append(cmd)
        # Sort by name for stable output
        visible.sort(key=lambda c: c.name)
        return visible

    @app_commands.command(
        name="help",
        description="Displays a list of commands you can use here, or details for a specific command.",
    )
    @app_commands.describe(
        command="Optional: The name of the command for detailed help."
    )
    async def help(
        self, interaction: discord.Interaction, command: Optional[str] = None
    ):
        try:
            if command is None:
                # Build list from only visible commands
                visible_cmds = self._collect_visible_commands(interaction)
                cmds: List[Tuple[str, str]] = []
                for c in visible_cmds:
                    name = getattr(c, "name", "unknown")[:EMBED_FIELD_NAME_LIMIT]
                    desc = getattr(c, "description", "") or "No description available."
                    cmds.append((name, desc))

                if not cmds:
                    embed = discord.Embed(
                        title="No Commands Available",
                        description="You do not have permission to use any commands here.",
                        color=discord.Color.red(),
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return

                pages = self.build_command_list_pages(cmds)
                view = PagedView(interaction.user.id, pages)
                await interaction.response.send_message(
                    embed=pages[0], view=view, ephemeral=True
                )
                audit_log(
                    f"{interaction.user.name} (ID: {interaction.user.id}) requested a filtered list of commands."
                )
                return

            # Detailed help for a specific command, respecting visibility
            found_command = None
            for cmd in self.bot.tree.walk_commands():
                if isinstance(cmd, app_commands.Command) and cmd.name.lower() == command.lower():
                    found_command = cmd
                    break

            if found_command and can_user_run_command(interaction, found_command):
                pages = self.build_detailed_command_pages(found_command)
                view = PagedView(interaction.user.id, pages)
                await interaction.response.send_message(
                    embed=pages[0], view=view, ephemeral=True
                )
                audit_log(
                    f"{interaction.user.name} (ID: {interaction.user.id}) requested detailed help for /{found_command.name}."
                )
            elif found_command:
                embed = discord.Embed(
                    title="Insufficient Permission",
                    description=f"You do not have permission to use `/ {found_command.name}` here.",
                    color=discord.Color.red(),
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
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
        except discord.NotFound:
            logging.warning("Interaction expired before response could be sent.")
        except discord.HTTPException as e:
            logging.exception(f"Failed to send help message: {e}")
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(
                        "Sorry, I could not send the help message due to a Discord error.", ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        "Sorry, I could not send the help message due to a Discord error.", ephemeral=True
                    )
            except Exception:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))