import pandas as pd
results = pd.read_csv('covered_call_backtest_results.csv')
print(f"Avg PnL: ${results['Total PnL'].mean():,.2f}")
print(f"Avg Return: {results['Return'].mean()*100:.2f}%")
print(f"Win Rate: {(results['Total PnL'] > 0).mean()*100:.2f}%")
print(f"Total PnL: ${results['Total PnL'].sum():,.2f}")
print(f"Max Return: {results['Return'].max()*100:.2f}%")
print(f'Total Return: {results["Return"].sum()*100:.2f}%')
print(f"Expected Return: {results['Return'].mean()/results['Return'].std():.2f}")
print(f"Max PnL: ${results['Total PnL'].max():,.2f}")
print(f"Min PnL (Max Loss): ${results['Total PnL'].min():,.2f}")
print(f"Std Dev PnL: ${results['Total PnL'].std():,.2f}")
print(f"Number of Trades: {len(results)}")
rf = 3.75 / 100  # 4.08% annual risk-free rate
print(f"Sharpe Ratio: {(results['Return'].mean() - rf/12) / results['Return'].std():.2f}")  # Monthly Sharpe

import matplotlib.pyplot as plt

fig = plt.figure(figsize=(12, 6))
# plot the cumsum PNL
plt.plot(results['Return'].cumsum())
plt.title('Cumulative Return')
plt.xlabel('Trade')
plt.ylabel('PNL')
plt.show()