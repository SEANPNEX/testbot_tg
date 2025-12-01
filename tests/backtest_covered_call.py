import pandas as pd
import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq
from pathlib import Path

# --- 1. BSM Model & Helpers ---
def bsm_d1(S, K, T, r, sigma):
    return (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))

def bsm_d2(S, K, T, r, sigma):
    return bsm_d1(S, K, T, r, sigma) - sigma * np.sqrt(T)

def bsm_call_price(S, K, T, r, sigma):
    if T <= 0:
        return max(0, S - K)
    d1 = bsm_d1(S, K, T, r, sigma)
    d2 = bsm_d2(S, K, T, r, sigma)
    return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)

def bsm_call_delta(S, K, T, r, sigma):
    if T <= 0:
        return 1.0 if S > K else 0.0
    d1 = bsm_d1(S, K, T, r, sigma)
    return norm.cdf(d1)

def bsm_call_gamma(S, K, T, r, sigma):
    if T <= 0:
        return 0.0
    d1 = bsm_d1(S, K, T, r, sigma)
    return norm.pdf(d1) / (S * sigma * np.sqrt(T))

def find_strike_for_delta(S, T, r, sigma, target_delta):
    """Find Strike K that gives the target delta."""
    def objective(K):
        return bsm_call_delta(S, K, T, r, sigma) - target_delta
    
    # Search range: 50% to 150% of Spot
    try:
        return brentq(objective, S * 0.5, S * 1.5)
    except ValueError:
        return S * 1.05 # Fallback

# --- 2. Data Loading ---
def get_all_closes(data_dir="sp500_data", start_date="2020-01-01", end_date="2025-12-01"):
    data_path = Path(data_dir)
    if not data_path.exists():
        raise FileNotFoundError(f"{data_dir} directory not found.")
    
    series_list = []
    print("Loading data...")
    for file in data_path.iterdir():
        if file.suffix.lower() != ".csv":
            continue
        symbol = file.stem
        try:
            df = pd.read_csv(file, parse_dates=["date"], index_col="date")
            df.index = pd.to_datetime(df.index)
            s = df["4. close"].astype(float)
            s = s[s.index >= pd.Timestamp(start_date)]
            s = s[s.index <= pd.Timestamp(end_date)]
            s.name = symbol
            series_list.append(s)
        except Exception:
            pass
            
    if not series_list:
        return pd.DataFrame()
    
    combined = pd.concat(series_list, axis=1)
    nan_ratio = combined.isna().mean()
    cols_to_keep = nan_ratio[nan_ratio <= 0.10].index
    combined = combined[cols_to_keep]
    combined = combined.dropna(how="all").sort_index().ffill()
    return combined

# --- 3. Signal Calculation ---
from fintech_utils.momentum.signal import MomentumSignal
from fintech_utils.momentum.config import MomentumConfig
import asyncio
import inspect

async def calculate_momentum_zscores(prices, window=30):
    # Use the library's MomentumSignal
    config = MomentumConfig(momentum_window=window)
    signal_gen = MomentumSignal(config)
    # Use internal method _zscore_rolling to get full history for backtest
    # relative_signal only returns the latest slice
    zscores = signal_gen._zscore_rolling(prices)
    if inspect.isawaitable(zscores):
        zscores = await zscores
    return zscores

# --- 4. Backtest Engine (Covered Call) ---
def run_covered_call_backtest(prices, zscores):
    # Assumptions
    BUDGET_PER_POS = 250000.0
    MAX_POSITIONS = 20
    R_FREE = 0.04
    SIGMA = 0.30 # Assumed IV
    
    # Strategy Params
    ENTRY_PERCENTILE = 0.70
    ENTRY_THRESHOLD = norm.ppf(ENTRY_PERCENTILE)
    
    TARGET_DELTA = 0.325 # Midpoint of (0.25, 0.4)
    DTM_ENTRY = 30
    DTM_MIN = 15
    
    GAMMA_MIN = 0.001
    GAMMA_MAX = 0.015
    
    print(f"Starting Backtest: Threshold Z={ENTRY_THRESHOLD:.2f}, Budget/Pos=${BUDGET_PER_POS:,.0f}")
    
    print(f"Prices shape: {prices.shape}")
    print(f"Zscores shape: {zscores.shape}")
    
    # Align dates and columns
    common_dates = prices.index.intersection(zscores.index)
    common_symbols = prices.columns.intersection(zscores.columns)
    
    print(f"Common dates: {len(common_dates)}")
    print(f"Common symbols: {len(common_symbols)}")
    
    if len(common_dates) == 0:
        print("Error: No overlapping dates between prices and zscores.")
        return pd.DataFrame()

    prices = prices.loc[common_dates, common_symbols]
    zscores = zscores.loc[common_dates, common_symbols]
    
    active_positions = {} # symbol -> {shares, entry_price, option: {strike, entry_premium, open_date, expiry_date}}
    closed_trades = []
    
    dates = prices.index
    
    for i, date in enumerate(dates):
            
        daily_scores = zscores.loc[date]
        daily_prices = prices.loc[date]
        
        # 1. Manage Existing Positions (Exit or Roll)
        symbols_to_exit = []
        
        for symbol, pos in active_positions.items():
            current_price = daily_prices.get(symbol)
            if pd.isna(current_price): continue
            
            score = daily_scores.get(symbol, -999)
            
            # Check Option Status
            opt = pos['option']
            days_to_expiry = (opt['expiry_date'] - date).days
            
            # EXIT SIGNAL: Momentum drops below threshold
            if score < ENTRY_THRESHOLD:
                # Close Position (Sell Stock, Buy Back Option)
                # Option Value
                T_remain = max(0, days_to_expiry / 365.0)
                opt_curr_price = bsm_call_price(current_price, opt['strike'], T_remain, R_FREE, SIGMA)
                
                # PnL Calculation
                stock_pnl = (current_price - pos['entry_price']) * pos['shares']
                option_pnl = (opt['entry_premium'] - opt_curr_price) * pos['shares'] # Short call: Profit if price drops
                total_pnl = stock_pnl + option_pnl
                
                closed_trades.append({
                    'Symbol': symbol,
                    'Entry Date': pos['entry_date'],
                    'Exit Date': date,
                    'Entry Price': pos['entry_price'],
                    'Exit Price': current_price,
                    'Stock PnL': stock_pnl,
                    'Option PnL': option_pnl,
                    'Total PnL': total_pnl,
                    'Return': total_pnl / (pos['entry_price'] * pos['shares']),
                    'Reason': 'Signal Exit'
                })
                symbols_to_exit.append(symbol)
                
            # ROLL SIGNAL: DTM <= 15 (and no exit signal)
            elif days_to_expiry <= DTM_MIN:
                # Roll Option: Buy back current, Sell new
                T_remain = max(0, days_to_expiry / 365.0)
                buy_back_price = bsm_call_price(current_price, opt['strike'], T_remain, R_FREE, SIGMA)
                
                prev_opt_pnl = (opt['entry_premium'] - buy_back_price) * pos['shares']
                
                # Sell New Option
                T_new = DTM_ENTRY / 365.0
                new_strike = find_strike_for_delta(current_price, T_new, R_FREE, SIGMA, TARGET_DELTA)
                new_premium = bsm_call_price(current_price, new_strike, T_new, R_FREE, SIGMA)
                new_expiry = date + pd.Timedelta(days=DTM_ENTRY)
                
                # Record the "realized" pnl from the rolled option leg?
                # Usually we track total pnl. Let's just update the option leg tracking.
                # We can treat the roll as realizing the option PnL and reducing cost basis?
                # For simplicity, let's accumulate realized option PnL in the position object
                pos['realized_option_pnl'] = pos.get('realized_option_pnl', 0) + prev_opt_pnl
                
                # Update Position with new option
                pos['option'] = {
                    'strike': new_strike,
                    'entry_premium': new_premium,
                    'open_date': date,
                    'expiry_date': new_expiry
                }
                # print(f"Rolled {symbol} on {date.date()}. PnL on leg: {prev_opt_pnl:.2f}")

        # Remove exited positions
        for s in symbols_to_exit:
            del active_positions[s]
            
        # 2. Open New Positions
        if len(active_positions) < MAX_POSITIONS:
            candidates = daily_scores[daily_scores > ENTRY_THRESHOLD].sort_values(ascending=False).index
            
            for symbol in candidates:
                if len(active_positions) >= MAX_POSITIONS:
                    break
                if symbol in active_positions:
                    continue
                
                price = daily_prices.get(symbol)
                if pd.isna(price): continue
                
                # Option Selection
                T = DTM_ENTRY / 365.0
                strike = find_strike_for_delta(price, T, R_FREE, SIGMA, TARGET_DELTA)
                
                # Gamma Check
                gamma = bsm_call_gamma(price, strike, T, R_FREE, SIGMA)
                if not (GAMMA_MIN <= gamma <= GAMMA_MAX):
                    continue # Skip if gamma not in range
                
                premium = bsm_call_price(price, strike, T, R_FREE, SIGMA)
                
                shares = int(BUDGET_PER_POS // price)
                if shares == 0: continue
                
                active_positions[symbol] = {
                    'shares': shares,
                    'entry_price': price,
                    'entry_date': date,
                    'realized_option_pnl': 0.0,
                    'option': {
                        'strike': strike,
                        'entry_premium': premium,
                        'open_date': date,
                        'expiry_date': date + pd.Timedelta(days=DTM_ENTRY)
                    }
                }
    
    # Close remaining at end
    last_date = dates[-1]
    last_prices = prices.loc[last_date]
    for symbol, pos in active_positions.items():
        curr_price = last_prices.get(symbol, pos['entry_price'])
        opt = pos['option']
        days_to_expiry = (opt['expiry_date'] - last_date).days
        T_remain = max(0, days_to_expiry / 365.0)
        opt_curr_price = bsm_call_price(curr_price, opt['strike'], T_remain, R_FREE, SIGMA)
        
        stock_pnl = (curr_price - pos['entry_price']) * pos['shares']
        option_pnl = (opt['entry_premium'] - opt_curr_price) * pos['shares']
        total_pnl = stock_pnl + option_pnl + pos.get('realized_option_pnl', 0)
        
        closed_trades.append({
            'Symbol': symbol,
            'Entry Date': pos['entry_date'],
            'Exit Date': last_date,
            'Entry Price': pos['entry_price'],
            'Exit Price': curr_price,
            'Stock PnL': stock_pnl,
            'Option PnL': option_pnl + pos.get('realized_option_pnl', 0),
            'Total PnL': total_pnl,
            'Return': total_pnl / (pos['entry_price'] * pos['shares']),
            'Reason': 'End of Backtest'
        })

    return pd.DataFrame(closed_trades)

# --- Execution ---
async def main():
    prices = get_all_closes(data_dir="../sp500_data", start_date="2025-06-01", end_date="2025-12-01")
    if not prices.empty:
        zscores = await calculate_momentum_zscores(prices, window=30) # Window 30 from assumptions
        results = run_covered_call_backtest(prices, zscores)
        
        print(f"\nTotal Trades: {len(results)}")
        if not results.empty:
            print(f"Avg PnL: ${results['Total PnL'].mean():,.2f}")
            print(f"Avg Return: {results['Return'].mean()*100:.2f}%")
            print(f"Win Rate: {(results['Total PnL'] > 0).mean()*100:.2f}%")
            print(results.head())
            results.to_csv("covered_call_backtest_results.csv", index=False)
    else:
        print("No data.")

if __name__ == "__main__":
    asyncio.run(main())
