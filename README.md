# The Parlour Caretaker Discord Bot

The Parlour Caretaker is a custom Discord bot designed to assist with moderation and utility tasks for [The Last Dinner Party Discord Server](https://discord.gg/theparlour). It provides a range of features to help streamline server management, engage the community, and maintain a transparent moderation process.

## Features

- **Custom Moderation Commands:**  
  Easily ban, kick, timeout, or temporarily ban users, with automated DM notifications.
  
- **Utility Commands:**  
  Send customized messages, forward direct messages, and set sticky messages that remain visible in channels.

- **Roulette Game:**  
  Try your luck with Nothing Matters Roulette! This game lets users risk a roll for their fate—with outcomes ranging from winning exciting rewards to facing humorous penalties. Player statistics are tracked using a persistent SQLite database, allowing you to view individual game stats and compare rankings on a leaderboard.

- **Timeout Command:**  
  Moderators can timeout members (i.e. disable their communication) for a specified duration. This feature leverages Discord's built‑in timeout functionality and logs all actions for accountability.

- **Auto Logging & Audit Trails:**  
  All moderation and administrative actions are automatically logged to a dedicated channel for transparency. In addition, every command interaction is also recorded in an internal audit log file (`audit.log`) that captures detailed actor, target, and context information.

- **Games Night Announcements:**  
  Quickly announce games nights in a dedicated channel with customizable embed messages.

- **Show Scraping:**  
  The bot periodically checks the band’s website for new shows and updates a specified channel with the latest event details.

## Usage

### Commands

- `/help` Displays a list of available commands.
- `/uptime` Displays how long the bot has been running.
- `/restart` Restarts the bot.<br><br>
- `/ban [user] [reason]` Permanently bans a user and sends them a DM with the reason.
- `/tempban [user] [duration] [reason]` Temporarily bans a user and sends them a DM with the reason and duration.
- `/kick [user] [reason]` Kicks a user and sends them a DM with the reason.
- `/dm [user] [message]` Sends a custom direct message to a specified user.
- `/message` Posts a custom message in a chosen channel.
- `/gamesnight [message]` Sends a games night announcement in the #parlour-games channel.
- `/scrape` Checks the band’s website for new shows and updates the #gig-chats channel.
- `/setsticky` Sets a sticky message in the current channel that remains at the bottom.
- `/removesticky` Removes the sticky message from the current channel.

### Logging & Audit Trails

- **Moderation Logs:**  
  All moderation and administrative actions (ban, kick, timeout, etc.) are automatically logged in a dedicated log channel. This feature helps maintain a clear record of actions for accountability and transparency.

- **Internal Audit Log:**  
  In addition to channel logging, every command action (including game commands) is recorded in an internal audit log file (`audit.log`). The audit entries include detailed information such as:
  - Actor’s name and user ID (the moderator or user who invoked the command)
  - Target details (e.g., target member’s name and ID)
  - Guild and channel names and IDs
  - Outcome details (for the roulette game, for example)

## Data Storage

- **SQLite Database:**  
  Persistent data for features like the roulette game and sticky messages are stored using SQLite, ensuring that user statistics and sticky messages persist across bot restarts.

## License

This project is licensed under the GPL-3.0 License - see the [LICENSE](LICENSE) file for details.

## Support

For any bugs or feature requests, feel free to open an issue in the [Issues](https://github.com/Prof1611/ParlourCaretaker/issues) tab.

---

## Maintained by:

- **GitHub:** [Prof1611](https://github.com/Prof1611) | **Discord:** Tygafire  
- **GitHub:** [MichaelEavis](https://github.com/MichaelEavis) | **Discord:** Harry0278
