# The Parlour Caretaker Discord Bot

The Parlour Caretaker is a custom Discord bot designed to assist with moderation tasks, such as sending notices to users and logging actions. This bot is tailored to handle specific server requirements with ease, ensuring smooth server management.

Built for [The Last Dinner Party Discord Server](https://discord.gg/theparlour)

## Features
- Custom moderation and utility commands.
- Auto logging for disciplinary actions.
- Direct message forwarding.
- Sticky messages.

## Usage

### Commands

- `/help` Sends a list of all commands.
- `/uptime` Displays how long the bot has been running.
- `/restart` Restarts the bot.<br><br>
- `/ban [user] [reason]` Permanently bans a user and sends them a notice with the reason via DM.
- `/tempban [user] [duration] [reason]` Temporarily bans a user and sends them a notice with the reason via DM.
- `/kick [user] [reason]` Kicks a user and sends them a notice with the reason via DM.
- `/dm [user] [message]` Sends a specified user a custom message via DM.
- `/message [channel] [message]` Sends a custom message to the specified channel.
- `/gamesnight [message]` Sends a games night announcement in #parlour-games.
- `/scrape` Checks the band's website for new shows and updates #gig-chats.
- `/setsticky` Sets a sticky message in the current channel.
- `/removesticky` Removes the sticky message from the current channel.

### Logging

All moderation actions are automatically logged in a specified channel. This helps keep track of actions taken by moderators.

## License

This project is licensed under the GPL-3.0 License - see the [LICENSE](LICENSE) file for details.

## Support

For any bugs or feature requests, feel free to open an issue in the [Issues](https://github.com/Prof1611/ParlourCaretaker/issues) tab.

---

## Maintained by:
GitHub: **[Prof1611](https://github.com/Prof1611)**<br>Discord: Tygafire

GitHub: **[MichaelEavis](https://github.com/MichaelEavis)**<br>Discord: Harry0278
