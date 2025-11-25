import pandas as pd
from typing import Tuple
import nonebot
from nonebot.rule import to_me
from nonebot.plugin import on_command
from nonebot.plugin import PluginMetadata, get_plugin_config
from nonebot.adapters.telegram.event import MessageEvent
import nonebot.drivers
from nonebot.adapters.telegram import Bot
from nonebot.permission import SUPERUSER
import os
import asyncio
from plugins.stock_monitor.data import data_access
from plugins.stock_monitor.portfolio import Portfolio
from plugins.stock_monitor.risk import RiskAnalyzer
from plugins.stock_monitor.ask import ask_field
from nonebot import require
require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_waiter import waiter
import json
from fintech_utils.momentum.config import MomentumConfig

portfolios = {}

__plugin_meta__ = PluginMetadata(
    name='stock_monitor',
    description='monitor stock prices and manage portfolios',
    usage='commands to monitor stocks and manage portfolios',
    homepage='seanpnex.github.io',
    type='application',
    supported_adapters={'~onebot.v11'}
)

driver = nonebot.get_driver()
# create basic working environment if not exist
data_accessor = data_access()

async def setup_environment(bot: Bot = None):
    if not os.path.exists('sp500.csv'):
        raise FileNotFoundError("sp500.csv not found. Please provide the file with S&P 500 ticker symbols.")
    if not os.path.exists('sp500_data'):
        data_accessor.fetch_initial_data()
    # else:
    #     data_accessor.update_data()
    if not os.path.exists('portfolios'):
        os.makedirs('portfolios')
    # monitor existing portfolios

async def load_existing_portfolios(bot: Bot = None):
    portfolios = {}
    for filename in os.listdir('portfolios'):
        if filename.endswith('_momentum_config.json'):
            uid = filename.split('_momentum_config.json')[0]
            # skip failed loads
            try:
                portfolios[uid] = Portfolio(uid, bot)
            except FileNotFoundError:
                nonebot.logger.error(f"Failed to load portfolio for UID {uid}.")
    return portfolios

@driver.on_bot_connect
async def setup(bot: Bot):
    global portfolios

    await setup_environment()

    portfolios = await load_existing_portfolios(bot)
    nonebot.logger.info(f"Loaded portfolios for UIDs: {list(portfolios.keys())}")

# Schedule for price check every mininute

driver = nonebot.get_driver()

@scheduler.scheduled_job("interval", minutes=1)
async def scheduled_price_check():
    nonebot.logger.info("Minute price check initiated.")

    # get all telegram bots
    bots = [b for b in driver.bots.values() if isinstance(b, Bot)]
    bot = bots[0] if bots else None

    # superusers come from global config, not plugin config
    su = driver.config.superusers

    for bot in bots:
        for su_id in su:
            # superusers are strings in config; Telegram wants int chat_id
            chat_id = int(su_id)
            await bot.send_message(chat_id=chat_id, text="Minute price check initiated.")

    for uid, portfolio in portfolios.items():
        if bots:
            portfolio.bot = bots[0]
        await monitor_portfolios(portfolio)

@scheduler.scheduled_job("cron", hour=18, minute=0)
async def daily_es_report():
    bots = [b for b in driver.bots.values() if isinstance(b, Bot)]
    if not bots:
        nonebot.logger.warning("No Telegram bot available for daily_es_report")
        return
    bot = bots[0]

    for uid, portfolio in portfolios.items():
        portfolio.bot = bot
        risk_analyzer = RiskAnalyzer(portfolio, bot)
        es = await risk_analyzer.get_es()
        msg = f"Daily Expected Shortfall (ES) report for your portfolio: ES at 95% confidence level is ${es:,.2f}."
        await bot.send_message(chat_id=int(uid), text=msg)
        await risk_analyzer.send_es_report()

async def monitor_portfolios(portfolio):
    risk_analyzer = RiskAnalyzer(portfolio, getattr(portfolio, "bot", None))
    await risk_analyzer.es_risk_warn()
    await risk_analyzer.price_change_warn()
    await risk_analyzer.option_roll_warn()
    await risk_analyzer.exit_signal_warn()
    await risk_analyzer.abs_threshold_warn()

# create portfolios for new users on command
create_portfolio = on_command("create_portfolio", rule=to_me(), aliases={"cp"})

@create_portfolio.handle()
async def _(bot: Bot, event: MessageEvent):
    uid = event.get_user_id()
    cfg_path = f"portfolios/{uid}_momentum_config.json"
    if os.path.exists(cfg_path):
        try:
            portfolio = Portfolio(uid, bot=bot)
        except ValueError as e:
            await bot.send_message(chat_id=uid, text=f"Portfolio data invalid: {e}")
            return
        await bot.send_message(chat_id=uid, text="Portfolio already exists.")
    else:
        # prompt for config setup
        defaults = MomentumConfig()
        # Step-by-step ask each field
        momentum_window = await ask_field(bot, event, "Momentum Window", defaults.momentum_window, int)
        zscore_window = await ask_field(bot, event, "Z-Score Window", defaults.zscore_window, int)
        abs_threshold = await ask_field(bot, event, "Absolute Threshold", defaults.abs_threshold, float)
        dtm_range = await ask_field(bot, event, "DTM Range (e.g. 30,45)", defaults.dtm_range, Tuple[int, int])
        delta_range = await ask_field(bot, event, "Delta Range (e.g. 0.25,0.40)", defaults.delta_range, Tuple[float, float])
        es_target = await ask_field(bot, event, "ES Target", defaults.es_target, float)
        low_percentile = await ask_field(bot, event, "Low Percentile", defaults.low_percentile, float)
        high_percentile = await ask_field(bot, event, "High Percentile", defaults.high_percentile, float)
        var_alpha = await ask_field(bot, event, "VaR Alpha", defaults.var_alpha, float)
        es_alpha = await ask_field(bot, event, "ES Alpha", defaults.es_alpha, float)
        roll_min_dtm = await ask_field(bot, event, "Roll Min DTM", defaults.roll_min_dtm, int)
        budget_per_position = await ask_field(bot, event, "Budget Per Position", defaults.budget_per_position, int)
        top_n = await ask_field(bot, event, "Top N", defaults.top_n, int)

        config = MomentumConfig(
            momentum_window=momentum_window,
            zscore_window=zscore_window,
            abs_threshold=abs_threshold,
            dtm_range=dtm_range,
            delta_range=delta_range,
            es_target=es_target,
            low_percentile=low_percentile,
            high_percentile=high_percentile,
            var_alpha=var_alpha,
            es_alpha=es_alpha,
            roll_min_dtm=roll_min_dtm,
            budget_per_position=budget_per_position,
            top_n=top_n,
        )
        await bot.send_message(chat_id=uid, text=f"Please confirm your configuration:\n{config.json()}\nSend 'yes' to confirm or 'no' to cancel.")
        @waiter(waits=["message"], keep_session=True)
        async def confirm_wait(event2: MessageEvent):
            if event2.chat.id != int(uid):
                return None
            return event2.get_message().extract_plain_text().strip().lower()

        confirmation = await confirm_wait.wait(timeout=120)
        if confirmation == "yes":
            portfolio = Portfolio(uid, bot=bot, momentum_config=config)
            await portfolio.create_positions(config)
            msg = "New portfolio created."
            await bot.send_message(chat_id=uid, text=msg)
        else:
            msg = "Portfolio creation cancelled."
            await bot.send_message(chat_id=uid, text=msg)
            return

    # send portfolio summary
    portfolios[uid] = portfolio 
    positions = portfolio.positions
    summary = f"Your current portfolio positions:\n{positions.to_string(index=False)}"
    await bot.send_message(chat_id=uid, text=summary)

create_portfolio_default = on_command("create_portfolio_default", rule=to_me(), aliases={"cpdef"})

@create_portfolio_default.handle()
async def _(bot: Bot, event: MessageEvent):
    uid = event.get_user_id()
    defaults = MomentumConfig()
    cfg_path = f'portfolios/{uid}_momentum_config.json'
    if os.path.exists(cfg_path):
        try:
            portfolio = Portfolio(uid, bot=bot)
        except ValueError as e:
            await bot.send_message(chat_id=uid, text=f"Portfolio data invalid: {e}")
        else:
            await bot.send_message(chat_id=uid, text="Portfolio already exists.")
            return

    portfolio = Portfolio(uid, bot=bot, momentum_config=defaults)
    await portfolio.create_positions(defaults)
    msg = "New portfolio created with default configuration."
    await bot.send_message(chat_id=uid, text=msg)
    # send portfolio summary
    portfolios[uid] = portfolio 
    positions = portfolio.positions
    summary = f"Your current portfolio positions:\n{positions.to_string(index=False)}"
    await bot.send_message(chat_id=uid, text=summary)

change_positions = on_command("change_positions", rule=to_me(), aliases={"cp2"})

@change_positions.handle()
async def _(bot: Bot, event: MessageEvent):
    uid = event.get_user_id()
    try:
        portfolio = Portfolio(uid, bot=bot)
    except (FileNotFoundError, ValueError) as e:
        msg = f"Portfolio does not exist or is invalid ({e}). Please create one first."
        await bot.send_message(chat_id=uid, text=msg)
        return
    # prompt for new positions
    await bot.send_message(chat_id=uid, text="Please send your new positions in JSON format. Example:\n[{\"symbol\": \"AAPL\", \"shares\": 100}, {\"symbol\": \"MSFT\", \"shares\": 50}]")

    @waiter(waits=["message"], keep_session=True)
    async def wait_positions(event2: MessageEvent):
        if event2.chat.id != int(uid):
            return None
        return event2.get_message().extract_plain_text().strip()

    reply = await wait_positions.wait(timeout=300)
    try:
        new_positions = json.loads(reply)
        new_positions_df = pd.DataFrame(new_positions)
        portfolio.update_positions(new_positions_df)
        msg = "Positions updated successfully."
        await bot.send_message(chat_id=uid, text=msg)
    except Exception as e:
        msg = f"Failed to update positions. Error: {str(e)}"
        await bot.send_message(chat_id=uid, text=msg)

change_positions_single = on_command("change_positions_single", rule=to_me(), aliases={"cps"})

@change_positions_single.handle()
async def _(bot: Bot, event: MessageEvent):
    uid = event.get_user_id()
    try:
        portfolio = Portfolio(uid, bot=bot)
    except FileNotFoundError:
        msg = "Portfolio does not exist. Please create one first."
        await bot.send_message(chat_id=uid, text=msg)
        return
    # prompt for new single position
    await bot.send_message(chat_id=uid, text="Please send your new position in JSON format. Example:\n{\"symbol\": \"AAPL\", \"shares\": 100}")
    @waiter(waits=["message"], keep_session=True)
    async def wait_single(event2: MessageEvent):
        if event2.chat.id != int(uid):
            return None
        return event2.get_message().extract_plain_text().strip()

    reply = await wait_single.wait(timeout=300)
    try:
        new_position = json.loads(reply)
        new_positions_df = pd.DataFrame([new_position])
        portfolio.update_positions(new_positions_df)
        msg = "Position updated successfully."
        await bot.send_message(chat_id=uid, text=msg)
    except Exception as e:
        msg = f"Failed to update position. Error: {str(e)}"
        await bot.send_message(chat_id=uid, text=msg)   
    
