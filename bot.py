import nonebot
from nonebot.adapters.telegram import Adapter as TelegramAdapter
import nonebot.drivers

nonebot.init()
app = nonebot.get_asgi()

driver = nonebot.get_driver()
driver.register_adapter(TelegramAdapter)

nonebot.load_builtin_plugins("echo")
nonebot.load_plugin("plugins.shutdown")
nonebot.load_plugin("plugins.nonebot-plugin-deepseek.nonebot_plugin_deepseek")
nonebot.load_plugin("nonebot_plugin_status")
nonebot.load_plugin("nonebot_plugin_logpile")
nonebot.load_plugin("YetAnotherPicSearch")
# nonebot.load_plugin("nonebot_plugin_deepseek")
nonebot.load_plugins("plugins/example")

print(driver.config)

if __name__ == "__main__":
    nonebot.logger.warning("Always use `nb run` to start the bot instead of manually running!")
    nonebot.run(app="__mp_main__:app")
