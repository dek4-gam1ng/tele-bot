"""Send scheduled Telegram messages with catch-up and persistent deduplication."""
import asyncio
import base64
from collections import Counter
import json
import os
import secrets
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions

WIB = ZoneInfo("Asia/Jakarta")
# Local WIB hours and minutes, in posting order.
TIMES = [
    (5, 45, "AUSTRALIA"),
    (7, 45, "LAOS"),
    (8, 0, "SOUTHKOREA"),
    (8, 30, "NORTHKOREA"),
    (9, 20, "TEXAS NIGHT"),
    (9, 35, "NEW YORK EVENING"),
    (10, 10, "KENTUCKY EVENING"),
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
    (19, 45, "HONGKONG"),
    (21, 15, "TTM 22"),
    (22, 15, "TTM 23"),
    (23, 15, "TTM 24"),
    (23, 30, "KENTUCKY DAY"),
]
STATE_PATH = ".telegram-sent.json"
CATCHUP_MINUTES = 15
NAME_ALIASES = {"NEW YORK": "NEW YORK EVENING", "TEXAS": "TEXAS NIGHT"}
VIP_LINKS = (
    "https://mez.ink/theprediksijitu",
    "https://heylink.me/landaktotorute/",
)


# Shared historical sample supplied by the user; dates and markets are unknown.
# Treat each result as a string to preserve leading zeros. No recency weighting.
HISTORICAL_RESULTS = """
7792 6948 9854 1184 8277 4153 5872 1680 1510 3834 4580 0509 7256 7231 4830
7174 4597 9532 5480 1269 3581 5096 8280 3778 8385 8262 5379 6297 7345 3967
5805 6754 2615 3534 6469 8270 6196 3268 9181 7176 6962 3686 2164 6987 5232
3159 5872 6807 2771 0823 9540 4659 9608 2036 0860 3725 9059 5065 0379 4332
9298 0040 1401 0076 6140 9348 3462 4146 5162 0752 0096 0841 4207 2055 8129
7085 4795 4953 6492 6038 9598 6190 9925 8710 3732 0507 0863 9160 0747 9487
""".split()
MODEL_VERSION = "pooled-frequency-v1"
DIGITS = "0123456789"
# Add-one smoothing keeps every digit eligible; this is not an accuracy claim.
DIGIT_COUNTS = Counter("".join(HISTORICAL_RESULTS))
DIGIT_WEIGHTS = tuple(DIGIT_COUNTS[digit] + 1 for digit in DIGITS)


def generate_digits(rng=None) -> str:
    """Draw five digits with replacement using the same pooled weights for all markets."""
    if not HISTORICAL_RESULTS or any(
        len(result) != 4 or any(digit not in DIGITS for digit in result)
        for result in HISTORICAL_RESULTS
    ):
        raise ValueError("Historical results must contain four ASCII digits each")
    rng = rng if rng is not None else secrets.SystemRandom()
    return "".join(rng.choices(DIGITS, weights=DIGIT_WEIGHTS, k=5))


def make_message(name: str, now: datetime, vip_url: str, digits: str = None) -> str:
    digits = generate_digits() if digits is None else digits

    parts = [
        f"🔮 {name} · {now:%d/%m}",
        f"⚡\n{digits}",
        f"🎯\n{digits[:4]} · {digits[2:]} · {digits[3:]}",
        "──────────",
    ]
    if off_today(now.weekday()):
        parts.append(f"💤 OFF HARI INI: {' • '.join(off_today(now.weekday()))}")
    parts.extend([
        "🤞 SALAM JP PAUS & TETAP UPS!",
        f"VIP · FB · X\n🔗 {vip_url}",
    ])
    return "\n\n".join(parts)


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
    state = json.loads(contents)
    for key in list(state):
        date, separator, name = key.partition(":")
        if separator and name in NAME_ALIASES:
            state.setdefault(f"{date}:{NAME_ALIASES[name]}", state[key])
    return state, result["sha"]


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
    return ((name == "PCSO" and day == 6) or
            (name == "TEXAS NIGHT" and day == 0) or
            (name == "SGP" and day in (1, 4)) or
            (name == "MAGNUM4D" and day not in (2, 5, 6)))


def off_today(day):
    return [name for _, _, name in TIMES if is_off(name, day)]


def menu_keyboard(state):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔮 BUKA LIST PASARAN / PROGRESS", url="https://t.me/theprediksitogelbot/pasaran"),
    ]])


async def main():
    now = datetime.now(WIB)
    manual = os.getenv("MANUAL_NAME", "").strip().upper()
    manual = NAME_ALIASES.get(manual, manual)
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
        for name, planned in due:
            key = f"{planned:%Y-%m-%d}:{name}"
            if key in state:
                print(f"Already sent {key}; skipping.")
                continue
            vip_index = int(state.get("META:VIP_NEXT", 0)) % len(VIP_LINKS)
            digits = generate_digits()
            sent = await bot.send_message(chat_id=chat_id, text=make_message(name, now, VIP_LINKS[vip_index], digits), reply_markup=menu_keyboard(state), link_preview_options=LinkPreviewOptions(is_disabled=True))
            state[key] = {
                "sent_at": datetime.now(WIB).isoformat(),
                "message_id": sent.message_id,
                "digits": digits,
                "model": MODEL_VERSION,
                "sample_size": len(HISTORICAL_RESULTS),
            }
            state["META:VIP_NEXT"] = (vip_index + 1) % len(VIP_LINKS)
            save_state(state, sha)
            # Reload the new SHA before recording the next delivery.
            state, sha = read_state()
            print(f"Sent {key}.")

if __name__ == "__main__":
    asyncio.run(main())
