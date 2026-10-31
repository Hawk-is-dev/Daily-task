# Study Bot (Telegram) - PW lecture planner + group chat lock

Telegram bot + userbot in ONE process. Hosted free on Render, kept awake by cron-job.org, data in MongoDB Atlas.

## Env variables (Render -> Environment)
| Name | Value |
|---|---|
| `BOT_TOKEN` | token from @BotFather |
| `API_ID`, `API_HASH` | from https://my.telegram.org |
| `SESSION` | string printed by `python gen_session.py` (run on your phone/PC) |
| `MONGODB_URI` | MongoDB Atlas connection string |
| `LOCK_ENABLED` | optional, set `0` to turn the group lock off |

## Render setup
1. Push this folder to a private GitHub repo.
2. Render -> New -> Web Service -> pick the repo. Runtime Python, **Instance type: Free**.
3. Build command: `pip install -r requirements.txt`  |  Start command: `python main.py`
4. Add the env variables above, deploy. Copy the `https://xxx.onrender.com` URL.
5. cron-job.org -> new job -> that URL -> every 10 minutes.
6. Open your bot in Telegram and send `/start` once (needed so the bot can message you). First plan arrives automatically at 12:00 AM on 1 Nov 2026, then every day at 12:00 AM.

## How it works
- 12:00 AM IST: message 1 = full plan, message 2 = tick buttons.
- Tick is accepted only after the lecture duration (+15 min free time) has passed since your previous tick (first tick of the day is free).
- Every tick = 15 min free group chatting. All lectures ticked = free till 12 AM. Otherwise your messages in **groups** are deleted. DMs, channels and Saved Messages are never touched.
- Lecture order: chapter lectures first, then that chapter's NCERT Punch. Deadline 31 Dec 2026.
