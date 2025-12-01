import asyncio
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
import os
import nonebot
# Initialize nonebot before importing plugins that rely on get_driver()

# Set dummy API key for testing before nonebot init if not present
if "ALPHAVANTAGE_API_KEY" not in os.environ:
    os.environ["ALPHAVANTAGE_API_KEY"] = "test_key"
nonebot.init()

# Explicitly inject API key into nonebot config for the test
driver = nonebot.get_driver()
if not hasattr(driver.config, "alphavantage_api_key"):
    setattr(driver.config, "alphavantage_api_key", os.environ.get("ALPHAVANTAGE_API_KEY", "test_key"))

from plugins.stock_monitor.risk import RiskAnalyzer
from plugins.stock_monitor.portfolio import Portfolio
from fintech_utils.momentum.config import MomentumConfig
from fintech_utils.momentum.signal import MomentumSignal

# Mock Bot
class MockBot:
    async def send_message(self, uid, text):
        print(f"[MOCK BOT] To {uid}: {text}")

# Mock Data Access
class MockDataAccess:
    def __init__(self, market_data):
        self.market_data = market_data

    def get_all_closes(self):
        return self.market_data

async def run_test():
    print("--- Starting Exit Signal Test ---")

    # 1. Setup Configuration
    config = MomentumConfig(
        momentum_window=10,
        low_percentile=0.10, # Bottom 10% triggers exit
        high_percentile=0.90,
        budget_per_position=10000
    )

    # 2. Generate Synthetic Data
    # Dates: 30 days
    dates = pd.date_range(start="2023-01-01", periods=30, freq="D")
    
    # Market Context (Steady growth)
    market_data = pd.DataFrame(index=dates)
    market_data['SPY'] = np.linspace(100, 105, 30) # Benchmark-ish
    market_data['C'] = np.linspace(50, 55, 30)
    market_data['D'] = np.linspace(50, 55, 30)

    # Portfolio Assets
    # Asset A: Was strong, now crashing (Should trigger EXIT)
    # Price goes 100 -> 120 (day 20) -> 90 (day 29)
    price_a = np.concatenate([np.linspace(100, 120, 20), np.linspace(120, 90, 10)])
    market_data['A'] = price_a

    # Asset B: Strong and steady (Should HOLD)
    # Price goes 100 -> 130
    price_b = np.linspace(100, 130, 30)
    market_data['B'] = price_b

    print("Market Data Tail:")
    print(market_data.tail())

    # 3. Setup Portfolio
    portfolio = MagicMock(spec=Portfolio)
    portfolio.uid = "12345"
    portfolio.momentum_config = config
    portfolio.signal = MomentumSignal(config)
    
    # Positions: Holding A and B
    portfolio.positions = pd.DataFrame([
        {'symbol': 'A', 'shares': 100, 'entry_price': 100},
        {'symbol': 'B', 'shares': 100, 'entry_price': 100}
    ])

    # Latest History (Real-time snapshot for portfolio assets)
    # In the code, this is usually just the recent window.
    # We'll provide the full window for simplicity as it gets merged.
    portfolio.latest_history = market_data[['A', 'B']].copy()

    # 4. Initialize RiskAnalyzer
    bot = MockBot()
    risk_analyzer = RiskAnalyzer(portfolio, bot)

    # 5. Patch data_access to return our synthetic market data
    # The code calls: data_access().get_all_closes()
    # So we need to patch the class 'plugins.stock_monitor.risk.data_access'
    
    with patch('plugins.stock_monitor.risk.data_access') as MockDAClass:
        mock_da_instance = MockDAClass.return_value
        mock_da_instance.get_all_closes.return_value = market_data
        
        # 6. Run exit_signal_warn
        print("\n--- Executing exit_signal_warn ---")
        await risk_analyzer.exit_signal_warn()
        print("--- Execution Complete ---")

if __name__ == "__main__":
    asyncio.run(run_test())
