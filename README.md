# The Parlour Caretaker Discord Bot

The Parlour Caretaker is a custom Discord bot designed to assist with moderation and utility tasks for [The Last Dinner Party Discord Server](https://discord.gg/theparlour). It provides a range of features to help streamline server management and enhance community engagement.

## Features
- Custom Moderation Commands:
Easily ban, kick, or temporarily ban users, with automated DM notifications.
- Utility Commands:
Send customised messages, forward direct messages, and set sticky messages that remain visible in channels.
- Auto Logging:
All moderation actions are automatically logged to a designated channel, helping moderators track actions and maintain transparency.
- Games Night Announcements:
Quickly announce games nights in a dedicated channel.
- Show Scraping:
Checks the band’s website for new shows and updates a specified channel with the latest events.

## Usage

### Commands

- `/help` Displays a list of available commands.
- `/uptime` Displays how long the bot has been running.
- `/restart` Restarts the bot.<br><br>
- `/ban [user] [reason]` Permanently bans a user and sends them a DM with the reason.
- `/tempban [user] [duration] [reason]` Temporarily bans a user and sends them a DM with the reason and duration.
- `/kick [user] [reason]` Kicks a user and sends them a DM with the reason.
- `/dm [user] [message]` Sends a custom direct message to a specified user.
- `/message [channel] [message]` Posts a custom message in a designated channel.
- `/gamesnight [message]` Sends a games night announcement in the #parlour-games channel.
- `/scrape` Checks the band’s website for new shows and updates the #gig-chats channel.
- `/setsticky` Sets a sticky message in the current channel that remains at the bottom.
- `/removesticky` Removes the sticky message from the current channel.

### Logging

All moderation and administrative actions are automatically logged in a dedicated channel. This logging feature helps maintain a clear record of actions taken by moderators for accountability and transparency.

## License

This project is licensed under the GPL-3.0 License - see the [LICENSE](LICENSE) file for details.

## Support

For any bugs or feature requests, feel free to open an issue in the [Issues](https://github.com/Prof1611/ParlourCaretaker/issues) tab.

---

## Maintained by:
GitHub: **[Prof1611](https://github.com/Prof1611)**<br>Discord: Tygafire

GitHub: **[MichaelEavis](https://github.com/MichaelEavis)**<br>Discord: Harry0278
