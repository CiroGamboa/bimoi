"""
Telegram bot runs only via the FastAPI backend (webhook). Do not run this module directly.

For production: run the backend (e.g. uvicorn or Docker) and set the Telegram webhook
to https://<your-domain>/webhook/telegram.

For local development: run the backend, expose it with ngrok, then set the webhook
to the ngrok URL. See README "Development with ngrok".
"""
import sys

_MESSAGE = """
The bot does not run in polling mode. Use the FastAPI backend with a webhook.

  Production: run the backend and set webhook to https://<your-domain>/webhook/telegram
  Local dev:  run the backend, start ngrok, then run: python scripts/set_webhook_ngrok.py

See the README for step-by-step instructions.
"""


def main() -> None:
    print(_MESSAGE.strip(), file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
