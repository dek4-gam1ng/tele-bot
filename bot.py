"""Scheduled Telegram number-combination messages (random, not predictive)."""
import asyncio
import os
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Bot

WIB = ZoneInfo("Asia/Jakarta")
SLOTS = {
    "45 3 * * *": "CAMBODIA",
    "15 5 * * *": "TTM P1",
    "45 5 * * *": "SYDNEY",
    "30 7 * * *": "CHINA",
    "15 8 * * *": "TTM P2",
    "15 9 * * *": "JAPAN",
    "45 9 * * *": "SGP",
    "15 11 * * *": "TTM P3",
    "45 12 * * *": "TAIWAN",
    "15 14 * * *": "TTM P4",
    "45 14 * * *": "HONGKONG",
    "15 15 * * *": "TTM P5",
    "15 16 * * *": "TTM P6",
}

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

async def main() -> None:
    schedule = os.getenv("GITHUB_SCHEDULE", "").strip()
    manual_name = os.getenv("MANUAL_NAME", "").strip().upper()
    if manual_name:
        if manual_name not in SLOTS.values():
            raise ValueError("Unknown manual prediction name")
        name = manual_name
    else:
        if schedule not in SLOTS:
            raise ValueError(f"Unrecognized cron schedule: {schedule!r}")
        name = SLOTS[schedule]

    now = datetime.now(WIB)
    if not manual_name and name == "SGP" and now.weekday() in (1, 4):
        print("SGP skipped on Tuesday/Friday (WIB).")
        return

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    async with Bot(token=token) as bot:
        await bot.send_message(chat_id=chat_id, text=make_message(name, now))
    print(f"Sent {name} for {now:%Y-%m-%d} WIB.")

if __name__ == "__main__":
    asyncio.run(main())
