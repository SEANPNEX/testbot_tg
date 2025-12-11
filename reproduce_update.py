import sys
from unittest.mock import MagicMock, AsyncMock
import asyncio
import os
import pandas as pd

# Mock nonebot
mock_nonebot = MagicMock()
mock_config = MagicMock()
mock_config.alphavantage_api_key = "test_key"
mock_nonebot.get_driver.return_value.config = mock_config
sys.modules["nonebot"] = mock_nonebot

# Create dummy sp500.csv and sp500_data directory
with open("sp500.csv", "w") as f:
    f.write("Symbol\nAAPL\nGOOG\nMSFT\n")

if not os.path.exists("sp500_data"):
    os.makedirs("sp500_data")

# Create dummy existing data
for symbol in ["AAPL", "GOOG", "MSFT"]:
    with open(f"sp500_data/{symbol}.csv", "w") as f:
        f.write("date,4. close\n2023-01-01,100.0\n")

# Import data_access after mocking
# We need to add the current directory to sys.path to import plugins
sys.path.append(os.getcwd())
from plugins.stock_monitor.data import data_access

async def test_update_data():
    da = data_access()
    
    # Mock httpx.AsyncClient
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "Time Series (Daily)": {
            "2023-01-02": {"4. close": "101.0"},
            "2023-01-03": {"4. close": "102.0"}
        }
    }
    mock_response.raise_for_status.return_value = None
    mock_client.get.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    # Patch httpx.AsyncClient in data module is hard because we import it inside the method or at top level
    # But we can patch it via sys.modules or unittest.mock.patch
    # Let's use unittest.mock.patch
    from unittest.mock import patch
    
    print("Starting update_data...")
    with patch("httpx.AsyncClient", return_value=mock_client):
        await da.update_data()
    
    print("update_data finished.")
    
    # Verify calls
    # We expect 3 calls (one for each symbol)
    print(f"Call count: {mock_client.get.call_count}")
    assert mock_client.get.call_count == 3
    
    # Verify data updated
    for symbol in ["AAPL", "GOOG", "MSFT"]:
        df = pd.read_csv(f"sp500_data/{symbol}.csv", index_col="date")
        print(f"{symbol} latest date: {df.index.max()}")
        assert "2023-01-03" in df.index

if __name__ == "__main__":
    asyncio.run(test_update_data())
