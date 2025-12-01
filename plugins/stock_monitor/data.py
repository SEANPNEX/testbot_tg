import os
from pathlib import Path
import requests
import pandas as pd
import nonebot


config = nonebot.get_driver().config
# nonebot config is attribute-style; fall back to upper-case env key if provided
api_key = getattr(config, "alphavantage_api_key", None) or getattr(config, "ALPHAVANTAGE_API_KEY", None)


class data_access:
    def __init__(self):
        if not api_key:
            raise RuntimeError("ALPHAVANTAGE_API_KEY is not configured in NoneBot config.")

    def fetch_initial_data(self):
        if not os.path.exists('sp500_data'):
            os.makedirs('sp500_data')
        sp500_df = pd.read_csv('sp500.csv')
        symbols = sp500_df['Symbol'].tolist()
        for symbol in symbols:
            self.fetch_and_store_data(symbol)

    def fetch_and_store_data(self, symbol):
        url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol={symbol}&apikey={api_key}&outputsize=full"
        response = requests.get(url)
        timeseries = response.json().get("Time Series (Daily)", {})
        if timeseries:
            df = pd.DataFrame.from_dict(timeseries, orient='index')
            df.index = pd.to_datetime(df.index)
            df.index.name = 'date'
            df = df.sort_index()
            df.to_csv(f'sp500_data/{symbol}.csv')
            print(f"Data for {symbol} saved.")
    
    def update_data(self):
        sp500_df = pd.read_csv('sp500.csv')
        symbols = sp500_df['Symbol'].tolist()
        for symbol in symbols:
            self.update_symbol_data(symbol)

    def get_all_closes(self) -> pd.DataFrame:
        """
        Read all CSVs under sp500_data and combine the '4. close' series into a single DataFrame.
        - Keep data from 2020-01-01 onward.
        - Drop columns with NaN ratio > 10% after alignment.
        - Drop rows/columns that are entirely NaN.
        """
        data_path = Path("sp500_data")
        if not data_path.exists() or not data_path.is_dir():
            raise FileNotFoundError("sp500_data directory not found.")
        series_list = []
        for file in data_path.iterdir():
            if file.suffix.lower() != ".csv":
                continue
            symbol = file.stem
            try:
                df = pd.read_csv(file, parse_dates=["date"], index_col="date")
                s = df["4. close"].astype(float)
                s = s[s.index >= pd.Timestamp("2020-01-01")]
                s.name = symbol
                series_list.append(s)
            except Exception as e:
                nonebot.logger.warning(f"Skipping {file} for closes aggregation: {e}")
        if not series_list:
            return pd.DataFrame()
        combined = pd.concat(series_list, axis=1)
        combined = combined.dropna(how="all").dropna(axis=1, how="all")
        if combined.empty:
            return combined
        nan_ratio = combined.isna().mean()
        cols_to_keep = nan_ratio[nan_ratio <= 0.10].index
        combined = combined[cols_to_keep]
        combined = combined.dropna(how="all")
        combined = combined.sort_index()
        return combined
            

    def update_symbol_data(self, symbol):
        file_path = f'sp500_data/{symbol}.csv'
        if not os.path.exists(file_path):
            print(f"No existing data for {symbol}, fetching initial data.")
            self.fetch_and_store_data(symbol)
            return
        
        existing_df = pd.read_csv(file_path, parse_dates=['date'], index_col='date')
        last_date = existing_df.index.max().strftime('%Y-%m-%d')

        url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol={symbol}&apikey={api_key}&outputsize=compact"
        response = requests.get(url)
        timeseries = response.json().get("Time Series (Daily)", {})
        
        new_data = {date: data for date, data in timeseries.items() if date > last_date}
        if new_data:
            new_df = pd.DataFrame.from_dict(new_data, orient='index')
            new_df.index = pd.to_datetime(new_df.index)
            new_df.index.name = 'date'
            new_df = new_df.sort_index()
            updated_df = pd.concat([existing_df, new_df])
            updated_df.to_csv(file_path)
            print(f"Data for {symbol} updated with {len(new_data)} new records.")
        else:
            print(f"No new data for {symbol}.")
    
    def get_latest_price(self, symbol):
        url = f'https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol={symbol}&interval=1min&apikey={api_key}'
        res = requests.get(url)
        data = res.json()
        time_series = data.get('Time Series (1min)', {})
        if not time_series:
            print(f"No intraday data available for {symbol}.")
            return None, None
        latest_time = max(time_series.keys())
        latest_data = time_series[latest_time]
        latest_price = float(latest_data['4. close'])
        print(f"Latest price for {symbol} at {latest_time} is {latest_price}.")
        return latest_price, latest_time

    def get_historical_data(self, symbol, start_date, end_date):
        file_path = f'sp500_data/{symbol}.csv'
        if not os.path.exists(file_path):
            print(f"No data available for {symbol}.")
            return None
        df = pd.read_csv(file_path, parse_dates=['date'], index_col='date')
        mask = (df.index >= pd.to_datetime(start_date)) & (df.index <= pd.to_datetime(end_date))
        filtered_df = df.loc[mask]
        filtered_df = filtered_df['4. close'].astype(float)
        latest_price, latest_time = self.get_latest_price(symbol)
        if latest_price is not None and not filtered_df.empty:
            last_date = filtered_df.index[-1]
            latest_date = pd.to_datetime(latest_time)
            if latest_date.date() == last_date.date():
                filtered_df.iloc[-1] = latest_price
            elif latest_date > last_date:
                filtered_df.loc[latest_date] = latest_price
        return filtered_df
    
    async def get_option_chain(self, symbol):
        url = f"https://www.alphavantage.co/query?function=HISTORICAL_OPTIONS&symbol={symbol}&require_greeks=true&apikey={api_key}"
        response = requests.get(url)
        data = response.json().get("data", [])
        options = pd.DataFrame(data)
        return options
