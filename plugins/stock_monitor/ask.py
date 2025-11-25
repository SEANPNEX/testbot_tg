from nonebot.adapters.telegram.event import MessageEvent
from nonebot.adapters.telegram import Bot
from nonebot_plugin_waiter import waiter
from typing import Tuple

# ask one field with default fallback
async def ask_field(bot: Bot, event: MessageEvent, field_name: str, default_value, type_hint):
    uid = int(event.get_user_id())

    # Ask user
    await bot.send_message(
        chat_id=uid,
        text=f"{field_name} (default: {default_value})\nSend value or leave empty to use default."
    )

    # Define waiter *inside* so we can capture uid
    @waiter(waits=["message"], keep_session=True)
    async def _wait(event2: MessageEvent):
        # only accept same user
        if event2.chat.id != uid:
            return None
        return event2.get_message().extract_plain_text().strip()

    # ✅ correct usage: use .wait(), not await function
    reply = await _wait.wait(timeout=120)  # or any timeout you like

    # If timeout or user sends empty → use default
    if not reply:
        return default_value

    # Type parsing logic
    try:
        if type_hint == int:
            return int(reply)
        elif type_hint == float:
            return float(reply)
        elif type_hint == Tuple[int, int]:
            a, b = reply.split(",")
            return (int(a.strip()), int(b.strip()))
        elif type_hint == Tuple[float, float]:
            a, b = reply.split(",")
            return (float(a.strip()), float(b.strip()))
        else:
            return reply
    except Exception:
        await bot.send_message(chat_id=uid, text=f"Invalid format. Using default: {default_value}")
        return default_value