# Poe Telegram Bot with Gemini Vision

A powerful Telegram bot that integrates Poe API and Google Gemini image recognition, supporting multiple AI models.

## Features

- Supports multiple AI models: GPT-4, Claude-3-Opus, and Claude-3.5-Sonnet
- Image analysis: Uses Google Gemini 2.0 Flash model for image recognition
- User whitelist management: Restricts bot usage permissions
- Usage tracking and limits: Monitor and control user request quotas
- Session context management: Remembers conversation history
- Command menu: Easy access to bot functions

## Installation

### Prerequisites

- Docker and Docker Compose
- Telegram Bot Token (from BotFather)
- Poe API Key (from Poe website)
- Google Gemini API Key (from Google AI Studio)

### Installation Process

1. Clone the repository:

```bash
git clone https://github.com/miludeerforest/poe-telegram-bot.git
cd poe-telegram-bot
```

2. Configure environment variables:

Copy the `.env.example` file to `.env` and fill in your API keys:

```bash
cp .env.example .env
# Edit the .env file
```

Or directly fill in the corresponding API keys in the `docker-compose.yml` file.

3. Build and start Docker containers:

```bash
docker compose up -d
```

## Usage

### Basic Commands

- `/start` - Start chatting with the bot
- `/new` - Start a new conversation, clear context
- `/gpt4` - Switch to GPT-4 model
- `/claude3` - Switch to Claude-3-Opus model
- `/claude35` - Switch to Claude-3.5-Sonnet model
- `/stats` - View your usage statistics

### Admin Commands

- `/adduser <user ID>` - Add user to whitelist
- `/removeuser <user ID>` - Remove user from whitelist
- `/listusers` - List all allowed users
- `/allstats` - View usage statistics for all users
- `/setlimit <user ID> <limit>` - Set daily usage limit for a user
- `/resetusage [user ID]` - Reset daily usage count (for all users or a specific user)

### Image Processing Feature

Simply send an image to the bot, and the system will use Google Gemini 2.0 Flash model to analyze the image content, then send the analysis results and partial base64 encoding of the image to Claude-3.5-Sonnet for processing.

You can add descriptive text when sending images to specify which aspects of the image you want to learn about.

### Usage Tracking and Limits

The bot tracks usage statistics for each user and enforces daily request limits:
- Default users: 50 requests per day
- Admin users: 200 requests per day
- Custom limits can be set per user by admins

The statistics tracked include:
- Daily usage counts
- Total request counts
- Image processing counts
- Model usage distribution
- Weekly usage summary

## Configuration

In the `docker-compose.yml` file, you can set the following environment variables:

- `TELEGRAM_BOT_TOKEN`: Telegram Bot Token
- `POE_API_KEY`: Poe API Key
- `GOOGLE_API_KEY`: Google Gemini API Key
- `ADMIN_USERS`: List of admin user IDs (comma-separated)
- `ALLOWED_USERS`: List of regular user IDs allowed to use the bot (comma-separated)

## Contribution Guidelines

Pull Requests or Issues are welcome to improve this project.

## License

MIT

## Disclaimer

This project is for learning and research purposes only. Please follow the terms of use of the respective APIs. 