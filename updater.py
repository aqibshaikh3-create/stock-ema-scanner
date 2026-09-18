import os
import time
import json
import gzip
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

def verify_strict_ema_strategy(df, fast, slow):
    if len(df) < slow:
        return False, 0
    df['fast_ema'] = df['close'].ewm(span=fast, adjust=False).mean()
    df['slow_ema'] = df['close'].ewm(span=slow, adjust=False).mean()
    df['position'] = np.where(df['fast_ema'] > df['slow_ema'], 1, 0)
    df['crossover'] = df['position'].diff()
    cross_indices = df[df['crossover'] == 1].index.tolist()
    if not cross_indices:
        return False, 0
    all_crosses_passed = True
    for idx in cross_indices:
        entry_price = df.loc[idx, 'close']
        remaining_data = df.loc[idx:]
        death_cross = remaining_data[remaining_data['crossover'] == -1]
        if not death_cross.empty:
            trade_window = df.loc[idx:death_cross.index]
        else:
            trade_window = remaining_data
        max_return = ((trade_window['high'].max() - entry_price) / entry_price) * 100
        if max_return < 5.0:
            all_crosses_passed = False
            break
    return all_crosses_passed, len(cross_indices)

if __name__ == "__main__":
    if not ANALYTICS_TOKEN:
        print("Missing token")
        exit(1)
        
    filtered_output = []
    try:
        json_gz_url = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
        
        # We supply custom headers so Upstox doesn't reject the virtual script as an unrecognized bot
        browser_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        response = requests.get(json_gz_url, headers=browser_headers, timeout=30)
        
        if response.status_code == 200:
            all_instruments = json.loads(gzip.decompress(response.content))
            nse_equities = [i for i in all_instruments if i.get('exchange') == 'NSE' and i.get('instrument_type') == 'EQ' and i.get('segment') == 'NSE_EQ']
            
            # Select up to 200 key assets to fit cleanly within free workflow execution boundaries
            target_batch = nse_equities[:200]
            print(f"Scanning {len(target_batch)} active stocks...")
            
            for stock in target_batch:
                key = stock.get('instrument_key')
                sym = stock.get('tradingsymbol')
                if not key or not sym:
                    continue
                historical_df = fetch_historical_candles(key)
                if historical_df is not None:
                    p_20_50, c_20_50 = verify_strict_ema_strategy(historical_df.copy(), 20, 50)
                    p_100_200, c_100_200 = verify_strict_ema_strategy(historical_df.copy(), 100, 200)
                    if p_20_50 or p_100_200:
                        filtered_output.append({
                            "symbol": sym,
                            "cross_20_50": "PASSED" if p_20_50 else "FAILED",
                            "count_20_50": c_20_50,
                            "cross_100_200": "PASSED" if p_100_200 else "FAILED",
                            "count_100_200": c_100_200
                        })
                time.sleep(0.12)
        else:
            print(f"Failed to fetch file stream from Upstox Server. HTTP Status: {response.status_code}")
            exit(1)
            
    except Exception as e:
        print(f"Error during network extraction sequence: {e}")
        exit(1)
        
    with open("data.json", "w") as f:
        json.dump(filtered_output, f, indent=4)
    print("Market scan finished successfully.")
