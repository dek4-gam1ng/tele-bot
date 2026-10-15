"""Send scheduled Telegram messages with catch-up and persistent deduplication."""
import asyncio
import base64
import json
import os
import secrets
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import Bot

WIB = ZoneInfo("Asia/Jakarta")
# Local WIB hours and minutes, in posting order.
TIMES = [
    (10, 45, "CAMBODIA"), (12, 15, "TTM P1"),
    (12, 45, "SYDNEY"), (14, 30, "CHINA"),
    (15, 15, "TTM P2"), (16, 15, "JAPAN"),
    (16, 45, "SGP"), (18, 15, "TTM P3"),
    (19, 45, "TAIWAN"), (21, 15, "TTM P4"),
    (21, 45, "HONGKONG"), (22, 15, "TTM P5"),
    (23, 15, "TTM P6"),
]
STATE_PATH = ".telegram-sent.json"
CATCHUP_MINUTES = 30


def make_message(name: str, now: datetime) -> str:
    digits = [secrets.randbelow(10) for _ in range(5)]
    bbfs = digits.copy()
    index = secrets.randbelow(4)
    bbfs[index], bbfs[index + 1] = bbfs[index + 1], bbfs[index]
    # If swapped digits match, the BBFS can remain unchanged.
    return (
        f"✦ {name} ✦\n"
        f"📅 {now:%d/%m/%Y}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🧩 ANGKA INCERAN\n"
        f"{' • '.join(map(str, digits))}\n\n"
        "🪐 4D\n"
        f"{''.join(map(str, digits[:4]))} | {''.join(map(str, [digits[4], digits[3], digits[2], digits[1]]))}\n\n"
        "🫧 3D\n"
        f"{''.join(map(str, digits[2:]))} | {''.join(map(str, digits[:3]))}\n\n"
        "🗝️ 2D\n"
        f"{''.join(map(str, digits[3:]))} | {''.join(map(str, digits[1:3]))}\n\n"
        "🌀 BBFS\n"
        f"{''.join(map(str, bbfs))}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🤞 MOGA HOKINYA NYANGKUT\n\n"
        "🔗 Join VIP :\n"
        "https://mez.ink/theprediksitogel"
    )


def github_state(method="GET", payload=None):
    """Read/write persistent sent-state on the default branch."""
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GH_TOKEN"]
    url = f"https://api.github.com/repos/{repo}/contents/{STATE_PATH}"
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if method == "GET" and exc.code == 404:
            return None
        raise


def read_state():
    result = github_state()
    if result is None:
        return {}, None
    contents = base64.b64decode(result["content"]).decode()
    return json.loads(contents), result["sha"]


def save_state(state, sha):
    # Keep only recent days to avoid growing the file forever.
    cutoff = (datetime.now(WIB).date() - timedelta(days=7)).isoformat()
    state = {key: value for key, value in state.items() if key[:10] >= cutoff}
    payload = {
        "message": "Record Telegram schedule delivery",
        "content": base64.b64encode(
            (json.dumps(state, indent=2, ensure_ascii=False) + "\n").encode()
        ).decode(),
    }
    if sha:
        payload["sha"] = sha
    github_state("PUT", payload)


async def main():
    now = datetime.now(WIB)
    manual = os.getenv("MANUAL_NAME", "").strip().upper()
    names = {name for _, _, name in TIMES}
    if manual and manual not in names:
        raise ValueError(f"Unknown prediction name: {manual}")

    state, sha = read_state()
    due = []
    if manual:
        due.append((manual, now))
    else:
        for hour, minute, name in TIMES:
            planned = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            delay = (now - planned).total_seconds() / 60
            if 0 <= delay <= CATCHUP_MINUTES:
                if name == "SGP" and now.weekday() in (1, 4):
                    continue
                due.append((name, planned))

    if not due:
        print("No scheduled messages due.")
        return

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    async with Bot(token=token) as bot:
        for name, planned in due:
            key = f"{planned:%Y-%m-%d}:{name}"
            if key in state:
                print(f"Already sent {key}; skipping.")
                continue
            await bot.send_message(chat_id=chat_id, text=make_message(name, now))
            state[key] = datetime.now(WIB).isoformat()
            save_state(state, sha)
            # Reload the new SHA before recording the next delivery.
            state, sha = read_state()
            print(f"Sent {key}.")

if __name__ == "__main__":
    asyncio.run(main())
