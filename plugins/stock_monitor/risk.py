import nonebot
import numpy as np
from plugins.stock_monitor.data import data_access
from plugins.stock_monitor.portfolio import Portfolio
import pandas as pd
from scipy.stats import norm
import asyncio
from nonebot.adapters.telegram import Bot

class RiskAnalyzer():
    def __init__(self, portfolio: Portfolio, bot: Bot):
        # Doing covered call only
        # Position records symbol, shares, entry_price, strike_price, premium, expiry_date, iv, risk_free = 4.08%
        self.positions = portfolio.positions
        self.uid = portfolio.uid
        self.bot = bot
        self.momentum_config = portfolio.momentum_config
        self.portfolio = portfolio
        self.latest_history = getattr(portfolio, "latest_history", pd.DataFrame())

    
    async def bsm_price(self, S, K, T, r, sigma, option_type='call'):
        from scipy.stats import norm
        from math import log, sqrt, exp

        d1 = (log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt(T))
        d2 = d1 - sigma * sqrt(T)

        if option_type == 'call':
            price = S * norm.cdf(d1) - K * exp(-r * T) * norm.cdf(d2)
        else:
            price = K * exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        return price
    
    @staticmethod
    async def simulate_terminal_price_gbm(S0, mu, sigma, T, n_simulations=10000):
        Z = np.random.randn(n_simulations)
        mu = float(mu)
        sigma = float(sigma)
        T = float(T)
        drift = (mu - 0.5 * sigma ** 2) * T
        diffusion = sigma * np.sqrt(T) * Z
        S_T = S0 * np.exp(drift + diffusion)
        return S_T
    
    async def get_es(self, alpha=0.05, n_simulations=10000, risk_free=0.0408):
        if self.positions.empty:
            return 0.0
        total_losses = []
        for index, position in self.positions.iterrows():
            symbol = position['symbol']
            shares = float(position['shares'])
            entry_price = float(position['entry_price'])
            strike_price = float(position['strike_price'])
            premium = float(position['premium'])
            expiry_date = position['expiry_date']
            iv = float(position['iv'])  
            T = (pd.to_datetime(expiry_date) - pd.to_datetime('today')).days / 365.0
            S0_raw, _ = data_access().get_latest_price(symbol)
            if S0_raw is None:
                continue
            S0 = float(S0_raw)
            S_T = await self.simulate_terminal_price_gbm(S0, mu=0.07, sigma=iv, T=T, n_simulations=n_simulations)
            option_prices = np.maximum(S_T - strike_price, 0)
            portfolio_values = shares * (S_T - option_prices + premium)
            losses = entry_price * shares - portfolio_values
            total_losses.extend(losses)

        total_losses = np.array(total_losses)
        VaR = np.percentile(total_losses, 100 * (1 - alpha))
        es = total_losses[total_losses >= VaR].mean()
        # relative to portfolio value
        portfolio_value = self.portfolio.get_total_value()
        print("DEBUG: Relative ES: ", es / portfolio_value)
        es = es / portfolio_value
        return es
    
    async def risk_attribution(self, alpha=0.05, n_simulations=10000, risk_free=0.0408):
        es_contributions = {}
        total_es = await self.get_es(alpha, n_simulations, risk_free)
        tasks = []
        for index, position in self.positions.iterrows():
            tasks.append(self._es_contribution(position, total_es, alpha, n_simulations, risk_free))
        results = await asyncio.gather(*tasks)
        for symbol, contribution in results:
            es_contributions[symbol] = contribution
        return es_contributions
    
    async def _es_contribution(self, position, total_es, alpha, n_simulations, risk_free=0.0408):
        symbol = position['symbol']
        shares = float(position['shares'])
        entry_price = float(position['entry_price'])
        strike_price = float(position['strike_price'])
        premium = float(position['premium'])
        expiry_date = position['expiry_date']
        iv = float(position['iv'])  
        T = (pd.to_datetime(expiry_date) - pd.to_datetime('today')).days / 365.0
        S0_raw, _ = data_access().get_latest_price(symbol)
        if S0_raw is None:
            return symbol, 0
        S0 = float(S0_raw)
        S_T = await self.simulate_terminal_price_gbm(S0, mu=0.07, sigma=iv, T=T, n_simulations=n_simulations)
        option_prices = np.maximum(S_T - strike_price, 0)
        portfolio_values = shares * (S_T - option_prices + premium)
        losses = entry_price * shares - portfolio_values

        losses = np.array(losses)
        VaR = np.percentile(losses, 100 * (1 - alpha))
        es = losses[losses >= VaR].mean()
        contribution = es / total_es if total_es != 0 else 0
        return symbol, contribution
    
    async def position_risk_adjustment(self, alpha=0.05, n_simulations=10000, risk_free=0.0408):
        es_target = self.momentum_config.es_target
        total_es = await self.get_es(alpha, n_simulations, risk_free)
        adjustment_factor = es_target / total_es if total_es != 0 else 1.
        adjusted_positions = self.positions.copy()
        adjusted_positions['adjusted_shares'] = (adjusted_positions['shares'] * adjustment_factor).astype(int)
        return adjusted_positions

    async def send_es_report(self, alpha=0.05, n_simulations=10000, risk_free=0.0408):
        total_es = await self.get_es(alpha, n_simulations, risk_free)
        attributions = await self.risk_attribution(alpha, n_simulations, risk_free)
        report = f"Expected Shortfall (ES) at {int(alpha*100)}% confidence level: ${total_es:,.2f}\n\nRisk Attribution:\n"
        for symbol, contribution in attributions.items():
            report += f"{symbol}: {contribution*100:.2f}%\n"
        # add adjusted positions
        adjusted_positions = await self.position_risk_adjustment(alpha, n_simulations, risk_free)
        report += "\nAdjusted Positions:\n"
        for index, row in adjusted_positions.iterrows():
            report += f"{row['symbol']}: Original Shares = {row['shares']}, Adjusted Shares = {row['adjusted_shares']}\n"
        await self.bot.send_message(self.uid, report)
    
    async def es_risk_warn(self, alpha=0.05, n_simulations=10000, risk_free=0.0408):
        es_threshold = self.momentum_config.es_target
        total_es = await self.get_es(alpha, n_simulations, risk_free)
        print(es_threshold, total_es)
        if total_es >= es_threshold:
            warning = f"Alert: Expected Shortfall (ES) is ${total_es:,.2f}, which exceeds the threshold of ${es_threshold:,.2f}."
            adjusted_positions = await self.position_risk_adjustment(alpha, n_simulations, risk_free)
            warning += "\nConsider adjusting positions as follows:\n"
            for index, row in adjusted_positions.iterrows():
                warning += f"{row['symbol']}: Original Shares = {row['shares']}, Adjusted Shares = {row['adjusted_shares']}\n"
            if self.bot:
                await self.bot.send_message(self.uid, warning)
    
    async def exit_signal_warn(self):
        signal = getattr(self.portfolio, "signal", None)
        if signal is None or self.latest_history.empty:
            return

        # Use full market data for relative signal calculation to ensure correct z-scores
        market_prices = data_access().get_all_closes()
        
        # Align and merge portfolio's real-time history into market prices
        if not market_prices.empty:
            # Union of indices to include potentially new real-time timestamp
            combined_index = market_prices.index.union(self.latest_history.index).sort_values()
            combined_prices = market_prices.reindex(combined_index)
            
            # Forward fill market data for the new timestamp (assuming unchanged for non-portfolio assets)
            combined_prices = combined_prices.ffill()
            
            # Update held positions with their fresh real-time data
            for col in self.latest_history.columns:
                if col in combined_prices.columns:
                    combined_prices[col].update(self.latest_history[col])
        else:
            # Fallback if market data is missing (shouldn't happen normally)
            combined_prices = self.latest_history

        rel_signals = await signal.relative_signal(combined_prices)
        
        low_percentile = self.momentum_config.low_percentile
        high_percentile = self.momentum_config.high_percentile
        # get low and high from norm ppf
        low = norm.ppf(low_percentile)
        high = norm.ppf(high_percentile)
        
        # Filter signals for current positions
        current_symbols = self.positions['symbol'].tolist()
        # Intersect with available signals
        valid_symbols = [s for s in current_symbols if s in rel_signals.index]
        my_signals = rel_signals[valid_symbols]

        # filter the positions for exit signals using LOW threshold
        exit_signals = my_signals[my_signals < low]
        
        for symbol, rel_val in exit_signals.items():
            warn = f"EXIT: {symbol} has generated an exit signal with relative signal {rel_val:.2f}."
            if self.bot:
                await self.bot.send_message(self.uid, warn)
            # calculate the budget freed
            if symbol in self.positions['symbol'].values:
                shares = self.positions[self.positions['symbol'] == symbol]['shares'].values[0]
                latest_price = (
                    self.latest_history[symbol].iloc[-1] if symbol in self.latest_history.columns else None
                )
                if latest_price is None:
                    continue
                budget_freed = shares * latest_price
                warn += f"Exiting this position will free up approximately ${budget_freed:,.2f} in capital."
                if self.bot:
                    await self.bot.send_message(self.uid, warn)
            # suggest allocation of freed budget
                budget_per_position = self.momentum_config.budget_per_position
                num_new_positions = (budget_freed // budget_per_position)
                if num_new_positions > 0:
                    warn += f"With the freed budget, you can consider opening approximately {num_new_positions} new positions based on your budget per position of ${budget_per_position:,.2f}."
                    if self.bot:
                        await self.bot.send_message(self.uid, warn)
                # check potential entry positions
                # Entry signals should be checked against the HIGH threshold
                entry_signals = rel_signals[rel_signals >= high]
                if not entry_signals.empty:
                    warn += "Potential new entry positions based on current signals:\n"
                    # Limit to top 5 to avoid spam
                    for entry_symbol, entry_signal in entry_signals.sort_values(ascending=False).head(5).items():
                        warn += f"{entry_symbol} with relative signal {entry_signal:.2f}\n"
                    if self.bot:
                        await self.bot.send_message(self.uid, warn)
            
    async def abs_threshold_warn(self):
        abs_threshold = self.momentum_config.abs_threshold
        if self.positions.empty or self.latest_history.empty:
            return
        for symbol in self.positions['symbol']:
            S0 = self.positions[self.positions['symbol'] == symbol]['entry_price'].values[0]
            latest = self.latest_history[symbol].iloc[-1] if symbol in self.latest_history.columns else None
            if latest is None:
                continue
            price_change = abs(latest - S0) / S0
            if price_change >= abs_threshold:
                warning = f"""ABSOLUTE THRESHOLD: {symbol} price changed by {price_change*100:.2f}% which exceeds the absolute threshold of {abs_threshold*100:.2f}%. Entry price was {S0:.2f}. Latest price is {latest:.2f}."""
                if self.bot:
                    await self.bot.send_message(self.uid, warning)
    
    async def option_roll_warn(self):
        today = pd.Timestamp.now().date()
        for index, position in self.positions.iterrows():
            symbol = position['symbol']
            expiry_date = position['expiry_date']
            days_to_expiry = (pd.to_datetime(expiry_date) - pd.to_datetime('today')).days
            if days_to_expiry <= self.momentum_config.roll_min_dtm:
                # Check if we already warned today
                last_warn = self.portfolio.roll_warn_tracker.get(symbol)
                if last_warn == today:
                    continue

                warning = f"OPTION ROLL: {symbol} option is nearing expiry in {days_to_expiry} days. Consider rolling the position."
                if self.bot:
                    await self.bot.send_message(self.uid, warning)
                
                # Update tracker
                self.portfolio.roll_warn_tracker[symbol] = today

    async def price_change_warn(self):
        """Fallback price change check; reuses abs threshold warn."""
        await self.abs_threshold_warn()
