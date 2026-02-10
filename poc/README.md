# Telegram contact card POC

Minimal proof-of-concept: connect to Telegram and read a contact card when the user shares one with the bot.

## What you need

1. **A bot token** from Telegram:
   - Open Telegram and search for **@BotFather**.
   - Send `/newbot`, choose a name and a username (e.g. `bimoi_poc_bot`).
   - Copy the **HTTP API token** (e.g. `7123456789:AAH...`).

2. **Python 3.10+** and a virtual environment (see below).

## Setup (use a venv)

From the **project root** (the `bimoi` directory):

```bash
# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate

# Install POC dependencies
pip install -r poc/requirements.txt
```

## Configure the token

Either:

- **Option A:** Create `poc/.env` with your token (recommended):
  ```bash
  cp poc/.env.example poc/.env
  # Edit poc/.env and set TELEGRAM_BOT_TOKEN=your_token_here
  ```

- **Option B:** Export the token in your shell:
  ```bash
  export TELEGRAM_BOT_TOKEN='your_token_here'
  ```

Do not commit `poc/.env` or any file containing the real token (`.env` is in `.gitignore`).

## Run the bot

With the venv activated and the token set:

```bash
python poc/bot.py
```

You should see: `POC bot running (polling). Send a contact card to the bot to test.`

## Test

1. Open Telegram and find your bot (by its username).
2. Send `/start` — the bot replies with instructions.
3. Share a contact card with the bot (choose a contact and “Share” to the bot, or use “Share contact” in the chat).
4. The bot should reply with the contact’s name, phone, and Telegram user_id.

If that works, the technical feasibility of reading contact cards via the Telegram Bot API is validated.
