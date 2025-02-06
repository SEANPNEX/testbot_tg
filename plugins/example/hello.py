from nonebot import on_message
from nonebot.adapters.telegram import Bot, Event
from nonebot.params import CommandArg
from nonebot.adapters.telegram.message import Message

hello_handler = on_message()

@hello_handler.handle()
async def handle_hello(bot: Bot, event: Event):
    if event.get_plaintext().strip().lower() == "hello":
        await bot.send(event, "Hello! How can I help you?")