from nonebot.rule import to_me
from nonebot.plugin import on_command
from nonebot.plugin import PluginMetadata, get_plugin_config
from nonebot.permission import SUPERUSER
import sys
import nonebot

__plugin_meta__ = PluginMetadata(
    name='shutdown',
    description='shutdown the bot by superuser',
    usage='mention the bot and use command shutdown',
    homepage='seanpnex.github.io',
    type='application',
    supported_adapters={'~onebot.v11'}
)
# Define the command
shutdown = on_command("shutdown", rule=to_me(), aliases={"shutdown", "关机"}, priority=10, permission=SUPERUSER)

@shutdown.handle()
async def handle_shutdown():
    await shutdown.send("Shutting down the bot...")  # Send a confirmation message
    nonebot.logger.info("Shutting down the bot as requested by the user.")
    # Exit the application gracefully
    sys.exit(0)