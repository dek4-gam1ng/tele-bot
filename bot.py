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
    # Digits may repeat within each set; at most two distinct digits shared.
    rng = secrets.SystemRandom()
    bbfs = [rng.randrange(10) for _ in range(5)]
    while True:
        poltar = [rng.randrange(10) for _ in range(5)]
        if len(set(bbfs) & set(poltar)) <= 2 and bbfs != poltar:
            break

    def pick(source, count):
        return ''.join(map(str, source[:count]))

    return (
        f"🔮 PREDIKSI {name} ({now:%d/%m})\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "⚡ BBFS x POLTAR\n"
        f"{pick(bbfs, 5)} x {pick(poltar, 5)}\n\n"
        "🎯 4D\n"
        f"{pick(bbfs, 4)} | {pick(poltar, 4)}\n\n"
        "🎯 3D\n"
        f"{pick(bbfs[2:], 3)} | {pick(poltar[2:], 3)}\n\n"
        "🎯 2D\n"
        f"{pick(bbfs[3:], 2)} | {pick(poltar[3:], 2)}\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🤞 SALAM JP PAUS & TETAP UPS!\n\n"
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
    return (name == "SGP" and day in (1, 4)) or (
        name == "MAGNUM4D" and day not in (2, 5, 6)
    )


def list_message():
    lines = ["📋 DAFTAR PASARAN", "━━━━━━━━━━━━━━━━━━"]
    for index, (_, _, name) in enumerate(TIMES, 1):
        if name == "SGP":
            name += " (OFF: Selasa, Jumat)"
        elif name == "MAGNUM4D":
            name += " (OFF: Senin, Selasa, Kamis, Jumat)"
        lines.append(f"{index:02d}. {name}")
    lines.extend(["━━━━━━━━━━━━━━━━━━", f"📊 TOTAL: {len(TIMES)} PASARAN"])
    return "\n".join(lines)


def progress_message(now, state):
    done, pending, off = [], [], []
    for hour, minute, name in TIMES:
        if is_off(name, now.weekday()):
            off.append(name)
        elif f"{now:%Y-%m-%d}:{name}" in state:
            done.append(name)
        else:
            pending.append(name)
    lines = [
        "📊 PROGRESS PREDIKSI HARI INI",
        f"🕒 {now:%d/%m/%Y %H:%M} WIB",
        "━━━━━━━━━━━━━━━━━━",
    ]
    for title, items in (
        ("✅ SUDAH DIKIRIM", done),
        ("⏳ BELUM DIKIRIM", pending),
        ("💤 OFF HARI INI", off),
    ):
        lines.extend(["", f"{title} ({len(items)})", *items])
    lines.extend(["", "━━━━━━━━━━━━━━━━━━", f"📊 TOTAL AKTIF: {len(done) + len(pending)} PASARAN"])
    return "\n".join(lines)


def menu_keyboard(state):
    list_id = state.get("META:LIST_ID")
    progress_id = state.get("META:PROGRESS_ID")
    if not list_id or not progress_id:
        return None
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📋 LIST PASARAN", url=f"https://t.me/theprediksitogel/{list_id}"),
        InlineKeyboardButton("📊 PROGRESS", url=f"https://t.me/theprediksitogel/{progress_id}"),
    ]])


async def update_menu_posts(bot, chat_id, state, sha, now):
    for label, content in (("LIST", list_message()), ("PROGRESS", progress_message(now, state))):
        key = f"META:{label}_ID"
        if key not in state:
            msg = await bot.send_message(chat_id=chat_id, text=content)
            state[key] = msg.message_id
            save_state(state, sha)
            state, sha = read_state()
        elif label == "PROGRESS":
            try:
                await bot.edit_message_text(chat_id=chat_id, message_id=state[key], text=content)
            except Exception as exc:
                if "Message is not modified" not in str(exc):
                    print(f"Progress update failed: {exc}")
    return state, sha


async def main():
    now = datetime.now(WIB)
    manual = os.getenv("MANUAL_NAME", "").strip().upper()
    if manual == "AUTO":
        manual = ""
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
                if name == "MAGNUM4D" and now.weekday() not in (2, 5, 6):
                    continue
                due.append((name, planned))

    if not due:
        print("No scheduled messages due.")

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    async with Bot(token=token) as bot:
        try:
            state, sha = await update_menu_posts(bot, chat_id, state, sha, now)
        except Exception as exc:
            print(f"Menu setup failed, continuing predictions: {exc}")
            state, sha = read_state()
        for name, planned in due:
            key = f"{planned:%Y-%m-%d}:{name}"
            if key in state:
                print(f"Already sent {key}; skipping.")
                continue
            await bot.send_message(chat_id=chat_id, text=make_message(name, now), reply_markup=menu_keyboard(state))
            state[key] = datetime.now(WIB).isoformat()
            save_state(state, sha)
            # Reload the new SHA before recording the next delivery.
            state, sha = read_state()
            print(f"Sent {key}.")
        if due:
            try:
                await update_menu_posts(bot, chat_id, state, sha, now)
            except Exception as exc:
                print(f"Progress refresh failed: {exc}")

if __name__ == "__main__":
    asyncio.run(main())
