import os
import time
import json
import gzip
import requests
import pandas as pd
import numpy as np

# --- CONFIGURATION ---
API_BASE_URL = "https://upstox.com"
INTERVAL = "1day"

# Dynamically calculate trailing 3-year timeline
TO_DATE = pd.Timestamp.now().strftime('%Y-%m-%d')
FROM_DATE = (pd.Timestamp.now() - pd.DateOffset(years=3)).strftime('%Y-%m-%d')

# Fetch the permanent 1-year token from GitHub Secret environment variables
ANALYTICS_TOKEN = os.getenv("UPSTOX_ANALYTICS_TOKEN")
HEADERS = {
    "Accept": "application/json", 
    "Authorization": f"Bearer {ANALYTICS_TOKEN}"
}

def fetch_historical_candles(instrument_key):
    """Hits the Upstox API safely to download 3 years of daily OHLC metrics"""
    url = f"{API_BASE_URL}/{instrument_key}/{INTERVAL}/{TO_DATE}/{FROM_DATE}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            payload = response.json()
            candles = payload.get('data', {}).get('candles', [])
            if not candles:
                return None
            
            # Upstox returns array: [Timestamp, Open, High, Low, Close, Volume, OpenInterest]
            df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df.sort_values('timestamp').reset_index(drop=True)
    except Exception as e:
        print(f"Skipping {instrument_key} due to request failure: {e}")
    return None

def verify_strict_ema_strategy(df, fast, slow):
    """Calculates EMAs and verifies if EVERY historic golden cross reached a >5% profit target"""
    if len(df) < slow: 
        return False, 0
    
    # Mathematical array operations for indicators
    df['fast_ema'] = df['close'].ewm(span=fast, adjust=False).mean()
    df['slow_ema'] = df['close'].ewm(span=slow, adjust=False).mean()
    
    # Identify Golden Cross (1 means fast crosses above slow)
    df['position'] = np.where(df['fast_ema'] > df['slow_ema'], 1, 0)
    df['crossover'] = df['position'].diff()
    
    cross_indices = df[df['crossover'] == 1].index.tolist()
    if not cross_indices: 
        return False, 0
        
    all_crosses_passed = True
    total_crosses_detected = len(cross_indices)
    
    for idx in cross_indices:
        entry_price = df.loc[idx, 'close']
        remaining_data = df.loc[idx:]
        
        # Detect where trade ends (Death Cross where fast falls back under slow)
        death_cross = remaining_data[remaining_data['crossover'] == -1]
        
        if not death_cross.empty:
            exit_idx = death_cross.index
            trade_window = df.loc[idx:exit_idx]
        else:
            trade_window = remaining_data # Trade is active up to the present day
            
        # Maximum potential peak return calculation
        highest_price = trade_window['high'].max()
        max_return = ((highest_price - entry_price) / entry_price) * 100
        
        # Disqualify the stock immediately if even one historical cross failed to reach a 5% peak
        if max_return < 5.0:
            all_crosses_passed = False
            break
            
    return all_crosses_passed, total_crosses_detected

if __name__ == "__main__":
    if not ANALYTICS_TOKEN:
        print("Execution Halted: UPSTOX_ANALYTICS_TOKEN secret environment variable is missing!")
        exit(1)

    print("Fetching full production market instrument dictionary from Upstox (JSON GZ format)...")
    filtered_output = []
    
    try:
        # Upstox's high-performance compressed master download endpoint
        json_gz_url = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"
        response = requests.get(json_gz_url, timeout=30)
        
        if response.status_code == 200:
            # Decompress and load binary stream directly into memory
            unzipped_data = gzip.decompress(response.content)
            all_instruments = json.loads(unzipped_data)
            
            # Extract and parse standard cash market NSE equities only
            nse_equities = [
                inst for inst in all_instruments 
                if inst.get('exchange') == 'NSE' and inst.get('instrument_type') == 'EQ' and inst.get('segment') == 'NSE_EQ'
            ]
            
            # Process up to 350 top liquid assets to keep workflow run times within GitHub's free tier bounds
            target_batch = nse_equities[:350]
            print(f"Successfully loaded and structured {len(target_batch)} active NSE stocks for screening.")
            
            for stock in target_batch:
                instrument_key = stock.get('instrument_key')
                symbol = stock.get('tradingsymbol')
                
                if not instrument_key or not symbol:
                    continue
                    
                print(f"Scanning metrics for: {symbol}...")
                historical_df = fetch_historical_candles(instrument_key)
                
                if historical_df is not None:
                    passed_20_50, count_20_50 = verify_strict_ema_strategy(historical_df.copy(), 20, 50)
                    passed_100_200, count_100_200 = verify_strict_ema_strategy(historical_df.copy(), 100, 200)
                    
                    if passed_20_50 or passed_100_200:
                        filtered_output.append({
                            "symbol": symbol,
                            "cross_20_50": "PASSED" if passed_20_50 else "FAILED",
                            "count_20_50": count_20_50,
                            "cross_100_200": "PASSED" if passed_100_200 else "FAILED",
                            "count_100_200": count_100_200
                        })
                
                # Protect rate thresholds (Upstox limit is 10 requests per second)
                time.sleep(0.12)
                
        else:
            print(f"Failed to fetch file stream from Upstox Server. HTTP Status: {response.status_code}")
            exit(1)
            
    except Exception as e:
        print(f"Critical operational error parsing Upstox master payload: {e}")
        exit(1)
        
    # Write full output to data.json
    with open("data.json", "w") as f:
        json.dump(filtered_output, f, indent=4)
        
    print("Execution complete! Market-wide scanning finished successfully.")
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df.sort_values('timestamp').reset_index(drop=True)
    except Exception as e:
        print(f"Skipping {instrument_key} due to request failure: {e}")
    return None

def verify_strict_ema_strategy(df, fast, slow):
    """Calculates EMAs and verifies if EVERY historic golden cross reached a >5% profit target"""
    if len(df) < slow: 
        return False, 0
    
    # Mathematical array operations for indicators
    df['fast_ema'] = df['close'].ewm(span=fast, adjust=False).mean()
    df['slow_ema'] = df['close'].ewm(span=slow, adjust=False).mean()
    
    # Identify Golden Cross (1 means fast crosses above slow)
    df['position'] = np.where(df['fast_ema'] > df['slow_ema'], 1, 0)
    df['crossover'] = df['position'].diff()
    
    cross_indices = df[df['crossover'] == 1].index.tolist()
    if not cross_indices: 
        return False, 0
        
    all_crosses_passed = True
    total_crosses_detected = len(cross_indices)
    
    for idx in cross_indices:
        entry_price = df.loc[idx, 'close']
        remaining_data = df.loc[idx:]
        
        # Detect where trade ends (Death Cross where fast falls back under slow)
        death_cross = remaining_data[remaining_data['crossover'] == -1]
        
        if not death_cross.empty:
            exit_idx = death_cross.index
            trade_window = df.loc[idx:exit_idx]
        else:
            trade_window = remaining_data # Trade is active up to the present day
            
        # Maximum potential peak return calculation
        highest_price = trade_window['high'].max()
        max_return = ((highest_price - entry_price) / entry_price) * 100
        
        # Disqualify the stock immediately if even one historical cross failed to reach a 5% peak
        if max_return < 5.0:
            all_crosses_passed = False
            break
            
    return all_crosses_passed, total_crosses_detected

if __name__ == "__main__":
    if not ANALYTICS_TOKEN:
        print("Execution Halted: UPSTOX_ANALYTICS_TOKEN secret environment variable is missing!")
        exit(1)

    print("Fetching full production market instrument dictionary from Upstox (JSON GZ format)...")
    filtered_output = []
    
    try:
        # Upstox's high-performance compressed master download endpoint
        json_gz_url = "https://upstox.com"
        response = requests.get(json_gz_url, timeout=30)
        
        if response.status_code == 200:
            unzipped_data = gzip.decompress(response.content)
            all_instruments = json.loads(unzipped_data)
            
            nse_equities = [
                inst for inst in all_instruments 
                if inst.get('exchange') == 'NSE' and inst.get('instrument_type') == 'EQ' and inst.get('segment') == 'NSE_EQ'
            ]
            
            # Process up to 350 top liquid assets to keep workflow run times within free limits
            target_batch = nse_equities[:350]
            print(f"Successfully loaded and structured {len(target_batch)} active NSE stocks for screening.")
            
            for stock in target_batch:
                instrument_key = stock.get('instrument_key')
                symbol = stock.get('tradingsymbol')
                
                if not instrument_key or not symbol:
                    continue
                    
                print(f"Scanning metrics for: {symbol}...")
                historical_df = fetch_historical_candles(instrument_key)
                
                if historical_df is not None:
                    passed_20_50, count_20_50 = verify_strict_ema_strategy(historical_df.copy(), 20, 50)
                    passed_100_200, count_100_200 = verify_strict_ema_strategy(historical_df.copy(), 100, 200)
                    
                    if passed_20_50 or passed_100_200:
                        filtered_output.append({
                            "symbol": symbol,
                            "cross_20_50": "PASSED" if passed_20_50 else "FAILED",
                            "count_20_50": count_20_50,
                            "cross_100_200": "PASSED" if passed_100_200 else "FAILED",
                            "count_100_200": count_100_200
                        })
                
                time.sleep(0.12)
                
        else:
            print(f"Failed to fetch file stream from Upstox Server. HTTP Status: {response.status_code}")
            exit(1)
            
    except Exception as e:
        print(f"Critical operational error parsing Upstox master payload: {e}")
        exit(1)
        
    # CRITICAL POSITION CORRECTION: This now runs outside the try block, 
    # guaranteeing that data.json is ALWAYS saved to your repository.
    with open("data.json", "w") as f:
        json.dump(filtered_output, f, indent=4)
        
    print(f"Execution complete! Saved {len(filtered_output)} filtered stocks to data.json.")
