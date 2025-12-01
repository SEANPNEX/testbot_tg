import asyncio
import pandas as pd
import numpy as np
import os
from unittest.mock import MagicMock, patch
import nonebot

# Set dummy API key for testing before nonebot init if not present
if "ALPHAVANTAGE_API_KEY" not in os.environ:
    os.environ["ALPHAVANTAGE_API_KEY"] = "test_key"

# Initialize nonebot
nonebot.init()

# Explicitly inject API key into nonebot config for the test
driver = nonebot.get_driver()
if not hasattr(driver.config, "alphavantage_api_key"):
    setattr(driver.config, "alphavantage_api_key", os.environ.get("ALPHAVANTAGE_API_KEY", "test_key"))

from plugins.stock_monitor.risk import RiskAnalyzer
from plugins.stock_monitor.portfolio import Portfolio
from fintech_utils.momentum.config import MomentumConfig

# Mock Bot
class MockBot:
    def __init__(self):
        self.sent_messages = []

    async def send_message(self, uid, text):
        print(f"[MOCK BOT] To {uid}: {text}")
        self.sent_messages.append(text)

async def run_tests():
    print("--- Starting Risk Warnings Tests ---")

    # Setup Common Config
    config = MomentumConfig(
        es_target=1000.0, # Threshold for ES warning
        abs_threshold=0.15, # 15% absolute change triggers warning
        roll_min_dtm=7, # Warn if expiry is within 7 days
    )

    # Setup Portfolio Mock
    portfolio = MagicMock(spec=Portfolio)
    portfolio.uid = "12345"
    portfolio.momentum_config = config
    portfolio.roll_warn_tracker = {}
    
    # Mock positions
    # Position 1: AAPL, Entry 150, Shares 100. Expiry far away.
    # Position 2: TSLA, Entry 200, Shares 50. Expiry soon (Roll Warn).
    portfolio.positions = pd.DataFrame([
        {
            'symbol': 'AAPL', 'shares': 100, 'entry_price': 150.0, 
            'strike_price': 160, 'premium': 5.0, 'expiry_date': '2025-12-30', 
            'iv': 0.2, 'risk_free': 0.04
        },
        {
            'symbol': 'TSLA', 'shares': 50, 'entry_price': 200.0, 
            'strike_price': 210, 'premium': 10.0, 'expiry_date': pd.Timestamp.now().date() + pd.Timedelta(days=5), # 5 days away
            'iv': 0.5, 'risk_free': 0.04
        }
    ])
    portfolio.get_total_value.return_value = 25000.0 # Approx value

    # Mock Latest History for Abs Threshold
    # AAPL: 150 -> 180 (20% increase, should trigger Abs Warn)
    # TSLA: 200 -> 205 (2.5% increase, no warn)
    portfolio.latest_history = pd.DataFrame({
        'AAPL': [150.0, 160.0, 180.0],
        'TSLA': [200.0, 202.0, 205.0]
    })

    bot = MockBot()
    risk_analyzer = RiskAnalyzer(portfolio, bot)

    # --- Test 1: Option Roll Warn ---
    print("\n[Test 1] Option Roll Warn")
    await risk_analyzer.option_roll_warn()
    
    # Verify TSLA warning sent
    tsla_warn = any("TSLA option is nearing expiry" in msg for msg in bot.sent_messages)
    print(f"TSLA Roll Warning Sent: {tsla_warn}")
    
    # Verify Tracker Updated
    print(f"Tracker State: {portfolio.roll_warn_tracker}")
    
    # Run again to verify suppression
    bot.sent_messages = [] # Clear messages
    await risk_analyzer.option_roll_warn()
    tsla_warn_2 = any("TSLA option is nearing expiry" in msg for msg in bot.sent_messages)
    print(f"TSLA Roll Warning Sent (2nd time): {tsla_warn_2} (Should be False)")


    # --- Test 2: Absolute Threshold Warn ---
    print("\n[Test 2] Absolute Threshold Warn")
    bot.sent_messages = []
    await risk_analyzer.abs_threshold_warn()
    
    # Verify AAPL warning sent (180 vs 150 is 20% > 15%)
    aapl_warn = any("AAPL price changed by 20.00%" in msg for msg in bot.sent_messages)
    print(f"AAPL Abs Threshold Warning Sent: {aapl_warn}")


    # --- Test 3: ES Risk Warn ---
    print("\n[Test 3] ES Risk Warn")
    bot.sent_messages = []
    
    # Mock get_es to return a value higher than es_target (1000)
    # We patch the method on the instance or class. Since it's async, we need a future.
    # However, get_es logic is complex (simulation). Let's just patch the return value of get_es method directly.
    
    with patch.object(RiskAnalyzer, 'get_es', new_callable=MagicMock) as mock_get_es:
        # Mock async return
        f = asyncio.Future()
        f.set_result(1500.0) # ES = 1500 > 1000
        mock_get_es.return_value = f
        
        # Also need to mock position_risk_adjustment since es_risk_warn calls it
        with patch.object(RiskAnalyzer, 'position_risk_adjustment', new_callable=MagicMock) as mock_adj:
            f_adj = asyncio.Future()
            # Return positions with 'adjusted_shares' column
            adj_positions = portfolio.positions.copy()
            adj_positions['adjusted_shares'] = adj_positions['shares'] # No adjustment for test
            f_adj.set_result(adj_positions) 
            mock_adj.return_value = f_adj
            
            await risk_analyzer.es_risk_warn()
            
            es_warn = any("Expected Shortfall (ES) is $1,500.00" in msg for msg in bot.sent_messages)
            print(f"ES Warning Sent: {es_warn}")

    print("\n--- Tests Complete ---")

if __name__ == "__main__":
    asyncio.run(run_tests())
