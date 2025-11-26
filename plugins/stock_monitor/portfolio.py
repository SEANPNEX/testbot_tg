from typing import Optional
from nonebot.adapters.telegram import Bot
from fintech_utils.momentum.config import MomentumConfig
from fintech_utils.momentum.signal import MomentumSignal
from plugins.stock_monitor.data import data_access
from scipy.stats import norm
import datetime
import nonebot
import pandas as pd
from pandas.errors import EmptyDataError
import os
import json
from pathlib import Path

class Portfolio:
    def __init__(self, uid: str, bot: Optional[Bot] = None, momentum_config: Optional[MomentumConfig] = None):
        self.uid = str(uid)
        self.bot = bot
        self.data_accessor = data_access()
        self.momentum_config = momentum_config or self.load_momentum_config()
        self.signal = MomentumSignal(self.momentum_config)
        # lazily loaded state
        self._positions: Optional[pd.DataFrame] = None
        self._latest_history: Optional[pd.DataFrame] = None

    @property
    def positions(self) -> pd.DataFrame:
        if self._positions is None:
            self._positions = self.load_positions()
        return self._positions

    @positions.setter
    def positions(self, value: pd.DataFrame):
        self._positions = value

    @property
    def latest_history(self) -> pd.DataFrame:
        if self._latest_history is None:
            self._latest_history = self.access_latest_history()
        return self._latest_history

    @latest_history.setter
    def latest_history(self, value: pd.DataFrame):
        self._latest_history = value
    
    def get_total_value(self):
        if self.positions.empty:
            return 0
        else:
            return self.positions['shares'] * self.positions['entry_price'].sum()
        

    def access_latest_history(self):
        symbols = self.positions['symbol'].tolist() if not self.positions.empty else []
        if not symbols:
            return pd.DataFrame()
        window = self.momentum_config.momentum_window
        tomorrow = datetime.datetime.now() + datetime.timedelta(days=1)
        start_date = tomorrow - datetime.timedelta(days=window * 3)  # buffer for non-trading days
        history = {}
        for symbol in symbols:
            latest_history = self.data_accessor.get_historical_data(
                symbol, start_date.strftime('%Y-%m-%d'), tomorrow.strftime('%Y-%m-%d')
            )
            if latest_history is not None and not latest_history.empty:
                history[symbol] = latest_history
        df_history = pd.DataFrame(history)
        # drop columns that are all NaN
        df_history = df_history.dropna(axis=1, how="all")
        return df_history

    async def create_positions(self, momentum_config: MomentumConfig):
        """Build initial positions based on momentum signals."""
        self.momentum_config = momentum_config
        self.save_momentum_config(momentum_config)
        prices = self.data_accessor.get_all_closes()
        if prices.empty:
            raise ValueError("No price data available to create positions (get_all_closes returned empty).")
        # compute signals on full price universe
        rel_signals = await self.signal.relative_signal(prices)
        high_percentile = momentum_config.high_percentile
        high = norm.ppf(high_percentile)
        # take top_n strongest signals above the high threshold
        entry_signals = rel_signals[rel_signals >= high].sort_values(ascending=False).head(momentum_config.top_n)
        positions = []
        for symbol, _rel in entry_signals.items():
            budget = momentum_config.budget_per_position
            if symbol not in prices.columns:
                continue
            hist_col = prices[symbol].dropna()
            if hist_col.empty:
                continue
            latest_price = hist_col.iloc[-1]
            shares = int(budget // latest_price)
            selected_option = await self.select_option(symbol)
            if selected_option is None:
                continue  # skip if no suitable option found
            position = {
                'symbol': symbol,
                'shares': shares,
                'entry_price': latest_price,
                'strike_price': selected_option['strike'],
                'premium': selected_option['bid'],
                'expiry_date': selected_option['expiration'],
                'iv': selected_option['implied_volatility'],
                'risk_free': 0.0408,  # hardcoded for now
            }
            positions.append(position)
        self.positions = pd.DataFrame(positions)
        # cache latest history for created symbols only
        self.latest_history = prices[entry_signals.index]
        self.save_positions()
        nonebot.logger.info(f"Created new positions for UID {self.uid}: {self.positions}")
        if self.bot:
            msg = f"Created new positions:\n{self.positions.to_string(index=False)}"
            await self.bot.send_message(chat_id=self.uid, text=msg)

    async def select_option(self, symbol: str):
        option_chain = await self.data_accessor.get_option_chain(symbol)
        # sanity checks and coercions
        if option_chain is None or option_chain.empty:
            nonebot.logger.warning(f"No option chain data for {symbol}. Skipping.")
            return None
        print(option_chain)
        # convert to num
        option_chain['delta'] = pd.to_numeric(option_chain['delta'], errors='coerce')
        # convert to datetime
        option_chain['expiration'] = pd.to_datetime(option_chain['expiration'], errors='coerce')
        # compute days to expiration
        target_delta_range = self.momentum_config.delta_range
        target_dtm_range = self.momentum_config.dtm_range
        today = datetime.datetime.now()
        time_range_low = today - datetime.timedelta(days=target_dtm_range[0])
        time_range_high = today + datetime.timedelta(days=target_dtm_range[1])
        mask = (
            (option_chain['delta'].abs() >= target_delta_range[0])
            & (option_chain['delta'].abs() <= target_delta_range[1])
            & (option_chain['expiration'] >= time_range_low)
            & (option_chain['expiration'] <= time_range_high)
        )
        filtered_options = option_chain[mask]
        if filtered_options.empty:
            nonebot.logger.warning(
                f"No suitable options found for {symbol} with given delta and DTM ranges. This asset should be skipped."
            )
            if self.bot:
                await self.bot.send_message(
                    chat_id=self.uid,
                    text=f"Warning: No suitable options found for {symbol} with given delta and DTM ranges. This asset will be skipped.",
                )
            return None
        filtered_options = filtered_options.sort_values(by='implied_volatility', ascending=False)
        return filtered_options.iloc[0]

    def load_momentum_config(self) -> MomentumConfig:
        config_path = Path("portfolios") / f"{self.uid}_momentum_config.json"
        if config_path.exists():
            data = json.loads(config_path.read_text(encoding="utf-8"))
            if hasattr(MomentumConfig, "model_validate"):
                return MomentumConfig.model_validate(data)  # type: ignore[attr-defined]
            return MomentumConfig(**data)

        # Missing config: create default and persist
        default_config = MomentumConfig()
        self.save_momentum_config(default_config)
        return default_config

    def save_momentum_config(self, config: MomentumConfig):
        config_path = Path("portfolios") / f"{self.uid}_momentum_config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # pydantic v2: model_dump
        if hasattr(config, "model_dump"):
            payload = config.model_dump()
        else:  # pydantic v1
            payload = config.dict()

        config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load_positions(self) -> pd.DataFrame:
        positions_path = f'portfolios/{self.uid}_positions.csv'
        if os.path.exists(positions_path):
            try:
                return pd.read_csv(positions_path)
            except EmptyDataError:
                msg = f"Positions file for UID {self.uid} is empty: {positions_path}"
                nonebot.logger.error(msg)
                raise ValueError(msg)
        # Initialize empty DataFrame when missing
        nonebot.logger.info(f"Positions file for UID {self.uid} not found. Initializing empty positions.")
        return pd.DataFrame(columns=['symbol', 'shares', 'entry_price', 'strike_price', 'premium', 'expiry_date', 'iv', 'risk_free'])

    def save_positions(self):
        positions_path = f'portfolios/{self.uid}_positions.csv'
        Path(positions_path).parent.mkdir(parents=True, exist_ok=True)
        self.positions.to_csv(positions_path, index=False)
        # refresh cached state to keep history consistent
        self._latest_history = self.access_latest_history() if not self.positions.empty else pd.DataFrame()

    def update_positions(self, new_positions: pd.DataFrame):
        self._positions = new_positions
        self.save_positions()
