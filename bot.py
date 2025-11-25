import nonebot
from nonebot.adapters.telegram import Adapter as TelegramAdapter
import nonebot.drivers
from nonebot.adapters.telegram import Bot

nonebot.init()
app = nonebot.get_asgi()

driver = nonebot.get_driver()
driver.register_adapter(TelegramAdapter)

config = nonebot.get_driver().config

nonebot.load_builtin_plugins("echo")
nonebot.load_plugin("plugins.shutdown")
nonebot.load_plugin("plugins.nonebot-plugin-deepseek.nonebot_plugin_deepseek")
nonebot.load_plugin("nonebot_plugin_status")
nonebot.load_plugin("nonebot_plugin_logpile")
nonebot.load_plugin("YetAnotherPicSearch")
# nonebot.load_plugin("nonebot_plugin_deepseek")
nonebot.load_plugins("plugins/example")
nonebot.load_plugins("nonebot_plugin_apscheduler")
nonebot.load_plugins('plugins/stock_monitor')

@driver.on_bot_connect
async def _on_tg_connect(bot: Bot):
    # SUPERUSERS from your .env / config
    su = bot.config.superusers
    print("[sendxxx] on_bot_connect, superusers:", su)
    print("[sendxxx] bot self_id:", bot.self_id)

    for user in su:
        chat_id = int(user) if isinstance(user, str) and user.isdigit() else user
        await bot.send_message(chat_id=chat_id, text="Bot has started!")
 
if __name__ == "__main__":
    nonebot.logger.warning("Always use `nb run` to start the bot instead of manually running!")
    nonebot.run(app="__mp_main__:app")
