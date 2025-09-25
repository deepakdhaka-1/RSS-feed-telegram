import os
import asyncio
import requests
from telethon import TelegramClient, events
from dotenv import load_dotenv

load_dotenv()

def get_env_var(name, cast_type=str, required=True):
    val = os.getenv(name)
    if required and not val:
        raise ValueError(f"Missing env: {name}")
    return cast_type(val) if val else None

API_ID = get_env_var("API_ID", int)
API_HASH = get_env_var("API_HASH")
BOT_TOKEN = get_env_var("BOT_TOKEN")
DEST_CHANNEL = get_env_var("DEST_CHANNEL")
SOURCE_CHANNELS = os.getenv("SOURCE_CHANNELS")

sources = []
for entry in SOURCE_CHANNELS.split(","):
    entry = entry.strip()
    # Remove URL prefix
    if entry.startswith("https://t.me/"): entry = entry[13:]
    elif entry.startswith("t.me/"): entry = entry[5:]
    parts = entry.split("/")
    if len(parts) == 1:
        sources.append((parts[0], None))  # username only, main chat/group/channel
        print(f"[DEBUG] Will monitor ALL messages in: {parts[0]}")
    elif len(parts) >= 2 and parts[-1].isdigit():
        username, topic_id = parts[-2], int(parts[-1])
        sources.append((username, topic_id))  # topic group/thread only
        print(f"[DEBUG] Will monitor topic: {username}/{topic_id}")
    else:
        print(f"[DEBUG] Skipping entry (must be t.me/username or t.me/username/topicid): {entry}")

if not sources:
    raise ValueError("[DEBUG] No valid username/topicid pairs in SOURCE_CHANNELS.")
channel_usernames = list({src[0] for src in sources})
print("[DEBUG] Monitoring usernames:", channel_usernames)

client = TelegramClient('forwarder', API_ID, API_HASH)

def extract_topic_id(msg):
    topic_id = None
    if msg.reply_to and getattr(msg.reply_to, "forum_topic", False):
        topic_id = getattr(msg.reply_to, "reply_to_msg_id", None)
    return topic_id

def forward_by_bot_api(bot_token, dest_channel, orig_msg, link):
    send_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    formatted_msg = f"{orig_msg.text}\n\nMessage URL: {link}"
    payload = {
        'chat_id': dest_channel,
        'text': formatted_msg,
        'parse_mode': 'HTML'
    }
    try:
        r = requests.post(send_url, data=payload, timeout=10)
        print("[DEBUG] Bot API response:", r.status_code, r.text)
        r.raise_for_status()
    except requests.ConnectionError as e:
        print("[ERROR] Connection error:", e)
    except Exception as e:
        print("[ERROR] Forward error:", e)

@client.on(events.NewMessage(chats=channel_usernames))
async def handler(event):
    chat = await event.get_chat()
    username = getattr(chat, "username", None)
    msg_id = getattr(event.message, "id", None)
    topic_id = extract_topic_id(event.message)
    # Create message link
    link = f"https://t.me/{username}/{topic_id}/{msg_id}" if topic_id else f"https://t.me/{username}/{msg_id}"

    for src_username, src_topic_id in sources:
        if username == src_username:
            # If src_topic_id is None, forward ALL messages. If src_topic_id, filter by topic.
            if src_topic_id is None:
                print(f"[DEBUG] Forwarding ALL messages from {username}")
                forward_by_bot_api(BOT_TOKEN, DEST_CHANNEL, event.message, link)
                return
            elif topic_id == src_topic_id:
                print(f"[DEBUG] Forwarding topic message from {username}/{topic_id}")
                forward_by_bot_api(BOT_TOKEN, DEST_CHANNEL, event.message, link)
                return
    print(f"[DEBUG] Skipping message {link}")

async def main():
    while True:
        try:
            await client.start()
            print("[DEBUG] Forwarder: Telethon listening, Bot API sending.")
            await client.run_until_disconnected()
        except Exception as e:
            print("[ERROR] Main loop crashed:", e)
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
