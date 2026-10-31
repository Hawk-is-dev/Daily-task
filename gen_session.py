"""Run this ONCE on your phone/PC (not on Render) to get the SESSION string.
    pip install telethon
    python gen_session.py
Keep the printed string secret: anyone with it can control your Telegram account."""
from telethon.sessions import StringSession
from telethon.sync import TelegramClient

api_id = int(input("API_ID: ").strip())
api_hash = input("API_HASH: ").strip()
with TelegramClient(StringSession(), api_id, api_hash) as client:
    print("\nYOUR SESSION STRING (copy everything below):\n")
    print(client.session.save())
