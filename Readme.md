# DarkNode Discord VPS Bot

This is a production-ready Discord bot for deploying and managing Ubuntu VPS instances via Docker, with tmate for secure SSH access.

## Features

-   **Discord.py v2.x with slash commands:** Modern, responsive command interface.
-   **Interactive UI:** Uses buttons and modals for a user-friendly experience.
-   **Docker & tmate:** Deploys Ubuntu containers and installs tmate to provide secure, temporary SSH sessions.
-   **JSON Persistence:** Session and user data are stored in local JSON files.
-   **Secure & Private:** Sensitive tmate links are sent directly to the user's DMs.
-   **Admin/User Separation:** Access control for VPS management and deployment.
-   **Black-Themed Embeds:** Visually consistent and appealing dark-themed embeds.

## Setup

### Prerequisites

1.  **Python 3.11+:** The bot is built using modern Python features.
2.  **Docker:** Must be installed on the host machine where you run the bot.
3.  **Discord Bot Token:** Create a bot application in the Discord Developer Portal and get your token.
4.  **Admin User ID:** Find your Discord User ID (enable Developer Mode in Discord settings).

### Installation

1.  **Clone this repository:**
    ```bash
    git clone [https://github.com/your-username/your-repo-name.git](https://github.com/your-username/your-repo-name.git)
    cd darknode_discord_vps_bot
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure `.env` file:**
    -   Copy the `.env.example` file to a new file named `.env`.
    -   Fill in your bot token and admin user ID. Note that the `DATA_DIR` is intentionally left blank.

    ```ini
    # .env
    DISCORD_TOKEN=your_bot_token_here
    ADMIN_USER_IDS=123456789012345678
    HOSTNAME=darknode
    WATERMARK=DarkNode
    DOCKER_IMAGE=ubuntu:22.04
    DATA_DIR=
    ```

5.  **Run the bot:**
    ```bash
    python main.py
    ```

The bot will connect to Discord and sync its slash commands. It will automatically create the `sessions.json` and `users.json` files in the same directory as `main.py` if they don't exist.

### File Structure

