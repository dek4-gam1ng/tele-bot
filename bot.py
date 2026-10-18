"""Send scheduled Telegram messages with catch-up and persistent deduplication."""
import asyncio
import base64
import json
import os
import secrets
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

WIB = ZoneInfo("Asia/Jakarta")
# Local WIB hours and minutes, in posting order.
TIMES = [
    (5, 45, "AUSTRALIA"),
    (7, 45, "LAOS"),
    (8, 0, "SOUTHKOREA"),
    (8, 30, "NORTHKOREA"),
    (8, 35, "NEW YORK"),
    (9, 10, "KENTUCKY EVENING"),
    (9, 20, "TEXAS"),
    (10, 45, "CAMBODIA"),
    (11, 15, "BRUNEI"),
    (11, 20, "BULLSEYE"),
    (12, 15, "TTM 13"),
    (12, 45, "SYDNEY"),
    (13, 45, "NEWZEALAND"),
    (14, 30, "CHINA"),
    (15, 15, "TTM 16"),
    (16, 15, "JAPAN"),
    (16, 45, "SGP"),
    (17, 15, "MAGNUM4D"),
    (17, 40, "MEXICO"),
    (18, 15, "TTM 19"),
    (19, 15, "PCSO"),
    (19, 45, "TAIWAN"),
    (21, 15, "TTM 22"),
    (21, 45, "HONGKONG"),
    (22, 15, "TTM 23"),
    (23, 15, "TTM 24"),
    (23, 30, "KENTUCKY DAY"),
]
STATE_PATH = ".telegram-sent.json"
CATCHUP_MINUTES = 15


def make_message(name: str, now: datetime) -> str:
    rng = secrets.SystemRandom()
    digits = ''.join(str(rng.randrange(10)) for _ in range(5))

    return (
        f"🔮 PREDIKSI {name} ({now:%d/%m})\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"⚡ {digits}\n"
        f"🎯 {digits[:4]}  |  {digits[2:]}  |  {digits[3:]}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        + (f"💤 OFF HARI INI: {' • '.join(off_today(now.weekday()))}\n━━━━━━━━━━━━━━━━━━\n" if off_today(now.weekday()) else "")
        + "🤞 SALAM JP PAUS & TETAP UPS!\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🌐 AKUN VIP · FACEBOOK · 𝕏\n"
        "🔗 https://mez.ink/theprediksitogel"
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
    state = {key: value for key, value in state.items() if (key.startswith("META:") or key[:10] >= cutoff)}
    payload = {
        "message": "Record Telegram schedule delivery",
        "content": base64.b64encode(
            (json.dumps(state, indent=2, ensure_ascii=False) + "\n").encode()
        ).decode(),
    }
    if sha:
        payload["sha"] = sha
    github_state("PUT", payload)


def is_off(name, day):
    return ((name == "TEXAS" and day == 0) or
            (name == "SGP" and day in (1, 4)) or
            (name == "MAGNUM4D" and day not in (2, 5, 6)))


def off_today(day):
    return [name for _, _, name in TIMES if is_off(name, day)]


async def handle_result_commands(bot, state, sha, chat_id):
    """Process admin-only result replies for any market with a saved post ID."""
    admin_id = os.getenv("TELEGRAM_ADMIN_ID", "").strip()
    if not admin_id:
        print("TELEGRAM_ADMIN_ID missing; skipping manual commands.")
        return state, sha

    markets = {name.lower().replace(" ", ""): name for _, _, name in TIMES}
    offset = int(state.get("META:UPDATE_OFFSET", 0))
    updates = await bot.get_updates(offset=offset, timeout=0, allowed_updates=["message"])
    for update in updates:
        state["META:UPDATE_OFFSET"] = update.update_id + 1
        message = update.effective_message
        if not message or not message.text or not message.from_user:
            continue
        if str(message.from_user.id) != admin_id or message.chat.type != "private":
            continue

        command = re.fullmatch(r"/([a-z0-9]+)(?:@\w+)?\s+(\d{4})\s+(\d{5})", message.text.strip(), re.I)
        if not command:
            continue
        short_name, result, digits = command.groups()
        market = markets.get(short_name.lower())
        if not market:
            continue

        today = datetime.now(WIB).strftime("%Y-%m-%d")
        sent = state.get(f"{today}:{market}")
        message_id = sent.get("message_id") if isinstance(sent, dict) else None
        if not message_id:
            await message.reply_text(f"ID posting {market} hari ini belum tersimpan. Tunggu prediksi berikutnya.")
            continue

        reply_key = f"META:RESULT_REPLY:{today}:{market}"
        legacy_key = f"META:SYDNEY_REPLY:{today}" if market == "SYDNEY" else None
        if state.get(reply_key) or (legacy_key and state.get(legacy_key)):
            await message.reply_text(f"Reply hasil {market} hari ini sudah dikirim.")
            continue

        mark = " (✅)" if set(result).issubset(set(digits)) else ""
        body = (
            f"{market} SAH : {result}\n"
            f"{digits}{mark}\n\n"
            "Salam JP & tetap UPS! 🔥\n\n"
            "Jangan lupa support lewat LINK 💛"
        )
        await bot.send_message(chat_id=chat_id, text=body, reply_to_message_id=message_id)
        state[reply_key] = True
        save_state(state, sha)
        state, sha = read_state()
        await message.reply_text(f"Reply {market} berhasil dikirim ke channel.")

    if updates:
        save_state(state, sha)
        return read_state()
    return state, sha


def menu_keyboard(state):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔮 BUKA LIST PASARAN / PROGRESS", url="https://t.me/theprediksitogelbot/pasaran"),
    ]])


async def main():
    now = datetime.now(WIB)
    manual = os.getenv("MANUAL_NAME", "").strip().upper()
    if manual == "AUTO":
        manual = ""
    names = {name for _, _, name in TIMES}
    if manual and manual not in names:
        raise ValueError(f"Unknown prediction name: {manual}")
    if manual and is_off(manual, now.weekday()):
        print(f"{manual} is OFF today; skipping manual prediction.")
        return

    state, sha = read_state()
    due = []
    if manual:
        due.append((manual, now))
    else:
        for hour, minute, name in TIMES:
            planned = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            delay = (now - planned).total_seconds() / 60
            if 0 <= delay <= CATCHUP_MINUTES:
                if is_off(name, now.weekday()):
                    continue
                due.append((name, planned))

    if not due:
        print("No scheduled messages due.")

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    async with Bot(token=token) as bot:
        state, sha = await handle_result_commands(bot, state, sha, chat_id)
        for name, planned in due:
            key = f"{planned:%Y-%m-%d}:{name}"
            if key in state:
                print(f"Already sent {key}; skipping.")
                continue
            sent = await bot.send_message(chat_id=chat_id, text=make_message(name, now), reply_markup=menu_keyboard(state))
            state[key] = {"sent_at": datetime.now(WIB).isoformat(), "message_id": sent.message_id}
            save_state(state, sha)
            # Reload the new SHA before recording the next delivery.
            state, sha = read_state()
            print(f"Sent {key}.")

if __name__ == "__main__":
    asyncio.run(main())
