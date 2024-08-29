# The Parlour Caretaker Discord Bot

The Parlour Caretaker is a custom Discord bot designed to assist with moderation tasks, such as sending notices to users and logging actions. This bot is tailored to handle specific server requirements with ease, ensuring smooth server management.

Built for [The Last Dinner Party Discord Server](https://discord.gg/theparlour)

## Features

- **Send Notices via DM:** Moderators can send predefined notices to members via direct messages.
- **Ban Members:** Moderators can ban members and auto send a notice to them with the reason.
- **Logging:** Logs all moderation actions in a specified channel for easy tracking.

## Usage

### Commands

- **`>notice @user "title" "message"`**: Sends a written notice to a user via DM. The notice includes a title and message within quotes.
  
  Example:
  
    ```bash
    >notice @Wumpus "Notice of Violation" "We have received reports of..."
    ```

### Roles

The bot checks if the user has a specific role before allowing them to execute commands. Configure this role in the `.env` file.

## Logging

All moderation actions, such as sending notices, are logged in a specified channel. This helps keep track of actions taken by moderators.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

For any issues or questions, feel free to open an issue in the [GitHub repository](https://github.com/Prof1611/ParlourCaretaker/issues).

---

## Maintained by:
GitHub: **[Prof1611](https://github.com/Prof1611)**
Discord: Tygafire

GitHub: **[HazzaWaltham123](https://github.com/HazzaWaltham123)**
Discord: Harry0278


**TO DO**

- [x] Test
