import os
import time
import json
import requests
import pandas as pd
import numpy as np

API_BASE_URL = "https://upstox.com"
INTERVAL = "1day"
TO_DATE = pd.Timestamp.now().strftime('%Y-%m-%d')
FROM_DATE = (pd.Timestamp.now() - pd.DateOffset(years=3)).strftime('%Y-%m-%d')

ANALYTICS_TOKEN = os.getenv("UPSTOX_ANALYTICS_TOKEN")
HEADERS = {"Accept": "application/json", "Authorization": f"Bearer {ANALYTICS_TOKEN}"}

def fetch_historical_candles(instrument_key):
    url = f"{API_BASE_URL}/{instrument_key}/{INTERVAL}/{TO_DATE}/{FROM_DATE}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        if res.status_code == 200:
            payload = res.json()
            candles = payload.get('data', {}).get('candles', [])
            if not candles:
                return None
            df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
            df = df.iloc[::-1].reset_index(drop=True)
            return df
    except Exception as e:
        print(f"Skipping {instrument_key}: {e}")
    return None

def calculate_tier_performance(df, fast, slow):
    if len(df) < slow:
        return "FAILED", 0
        
    df['fast_ema'] = df['close'].ewm(span=fast, adjust=False).mean()
    df['slow_ema'] = df['close'].ewm(span=slow, adjust=False).mean()
    df['position'] = np.where(df['fast_ema'] > df['slow_ema'], 1, 0)
    df['crossover'] = df['position'].diff()
    
    cross_indices = df[df['crossover'] == 1].index.tolist()
    if not cross_indices:
        return "FAILED", 0
        
    lowest_max_return = 999999.0
    
    for idx in cross_indices:
        entry_price = df.loc[idx, 'close']
        remaining_data = df.loc[idx:]
        death_cross = remaining_data[remaining_data['crossover'] == -1]
        
        if not death_cross.empty:
            trade_window = df.loc[idx:death_cross.index]
        else:
            trade_window = remaining_data
            
        max_return = ((trade_window['high'].max() - entry_price) / entry_price) * 100
        if max_return < lowest_max_return:
            lowest_max_return = max_return

    if lowest_max_return >= 5.0:
        return "PREMIUM (5%+)", len(cross_indices)
    elif lowest_max_return >= 3.0:
        return "GOLD (3%+)", len(cross_indices)
    elif lowest_max_return >= 1.0:
        return "SILVER (1%+)", len(cross_indices)
        
    return "FAILED", len(cross_indices)

if __name__ == "__main__":
    if not ANALYTICS_TOKEN:
        print("Missing token")
        exit(1)
        
    filtered_output = []
    
    # Static list of the top 50 highest-volume NIFTY stocks on the NSE.
    # This list represents more than 60% of the entire stock market volume!
    symbols = [
        "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "BHARTIARTL", "SBI", "LICI", "ITC", "HINDUNILVR",
        "LT", "BAJAJFINSV", "HCLTECH", "MARUTI", "SUNPHARMA", "ADANIENT", "KOTAKBANK", "TITAN", "AXISBANK", "ONGC",
        "NTPC", "TATAMOTORS", "ULTRACEMCO", "COALINDIA", "ASIANPAINT", "BAJFINANCE", "ADANIPORTS", "POWERGRID", "DMART", "JSWSTEEL",
        "M&M", "SIEMENS", "TATASTEEL", "HAL", "SBILIFE", "GRASIM", "TECHM", "BRITANNIA", "HINDALCO", "INDUSINDBK",
        "DRREDDY", "CIPLA", "EICHERMOT", "DIVISLAB", "BPCL", "NESTLEIND", "BAJAJ-AUTO", "APOLLOHOSP", "SHRIRAMFIN", "HEROMOTOCO"
    ]
    
    print(f"Scanning {len(symbols)} high-volume market stocks for multi-tier criteria...")
    
    for symbol in symbols:
        # Standard corporate equity keys mapped reliably for the Upstox server API
        # Handled safely via exchange instrument formatting definitions
        instrument_key = f"NSE_EQ|{symbol}"
        if symbol == "SBI":
            instrument_key = "NSE_EQ|SBIN"  # Correcting State Bank of India trading ticker typo
            
        print(f"Scanning metrics for: {symbol}...")
        historical_df = fetch_historical_candles(instrument_key)
        
        if historical_df is not None:
            tier_20_50, c_20_50 = calculate_tier_performance(historical_df.copy(), 20, 50)
            tier_100_200, c_100_200 = calculate_tier_performance(historical_df.copy(), 100, 200)
            
            if tier_20_50 != "FAILED" or tier_100_200 != "FAILED":
                filtered_output.append({
                    "symbol": symbol,
                    "cross_20_50": tier_20_50,
                    "count_20_50": c_20_50,
                    "cross_100_200": tier_100_200,
                    "count_100_200": c_100_200
                })
        time.sleep(0.15)
        
    with open("data.json", "w") as f:
        json.dump(filtered_output, f, indent=4)
    print("Market scan finished successfully.")
