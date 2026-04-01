import streamlit as st
import pandas as pd
import requests

# ==========================================
# 1. 介面設定
# ==========================================
st.set_page_config(page_title="量化選股器", layout="wide")
st.title("MACD 為主 & SMA 為輔 量化選股器")

st.sidebar.header("1. 技術面篩選")
filter_macd = st.sidebar.checkbox("MACD: 黃金交叉 或 即將交叉")
filter_sma = st.sidebar.checkbox("SMA: 多頭排列 或 即將交叉 (20, 50, 200)")

st.sidebar.header("2. 市值級距篩選 (美金)")
cap_1 = st.sidebar.checkbox("1億美金以下 (< 0.1B)")
cap_2 = st.sidebar.checkbox("1億到250億 (0.1B - 25B)")
cap_3 = st.sidebar.checkbox("250億到1000億 (25B - 100B)")
cap_4 = st.sidebar.checkbox("1000億到5000億 (100B - 500B)")
cap_5 = st.sidebar.checkbox("5000億以上 (> 500B)")

st.sidebar.header("3. 流動性篩選")
liq_high = st.sidebar.checkbox("流動性足夠 (成交量 > 100萬)")
liq_low = st.sidebar.checkbox("流動性低 (成交量 < 50萬)")

TICKERS = ["AAPL", "NVDA", "TSM", "ASML", "WULF", "ETN", "SMH", "GOOG"]

# ==========================================
# ⚠️ 請在這裡貼上你剛註冊好的 FMP API KEY
# ==========================================
API_KEY = "lEwPy0dM1t9jhuMF4BJjk4oHNK17HYFU"

# ==========================================
# 2. 掃描與計算邏輯 (使用 FMP 最新 Stable API)
# ==========================================
if st.sidebar.button("開始掃描市場", type="primary"):
    if API_KEY == "請把你的鑰匙貼在這裡" or API_KEY == "":
        st.error("❌ 錯誤：你還沒有在程式碼中填入 API Key！")
    else:
        with st.spinner('正在透過 FMP 最新 API 獲取數據...'):
            results = []
            errors = []

            for ticker in TICKERS:
                try:
                    # 1. 抓取基本面 (切換至最新的 stable 網址)
                    quote_url = f"https://financialmodelingprep.com/stable/quote?symbol={ticker}&apikey={API_KEY}"
                    quote_res = requests.get(quote_url).json()
                    
                    if isinstance(quote_res, dict) and "Error Message" in quote_res:
                        errors.append(f"[{ticker}] API 拒絕連線: {quote_res['Error Message']}")
                        continue
                    elif isinstance(quote_res, dict) and "message" in quote_res:
                        errors.append(f"[{ticker}] API 異常: {quote_res['message']}")
                        continue
                    elif not quote_res or len(quote_res) == 0:
                        errors.append(f"[{ticker}] 找不到該股票報價")
                        continue
                    
                    # 容錯處理：取第一筆資料
                    quote_data = quote_res[0] if isinstance(quote_res, list) else quote_res
                    market_cap_b = quote_data.get('marketCap', 0) / 1_000_000_000
                    volume = quote_data.get('volume', 0)

                    # 2. 抓取歷史 K 線 (切換至最新的 stable 網址)
                    hist_url = f"https://financialmodelingprep.com/stable/historical-price-eod/full?symbol={ticker}&apikey={API_KEY}"
                    hist_res = requests.get(hist_url).json()
                    
                    if isinstance(hist_res, dict) and "Error Message" in hist_res:
                        errors.append(f"[{ticker}] API 拒絕歷史數據: {hist_res['Error Message']}")
                        continue
                    
                    # 判斷資料格式以相容新版 API
                    if isinstance(hist_res, dict) and 'historical' in hist_res:
                        hist_data = hist_res['historical']
                    elif isinstance(hist_res, list):
                        hist_data = hist_res
                    else:
                        hist_data = []

                    if len(hist_data) < 200:
                        errors.append(f"[{ticker}] 歷史數據不足 200 天")
                        continue

                    # 轉換成 DataFrame 並確保依照日期由舊到新排列
                    df = pd.DataFrame(hist_data)
                    if 'date' in df.columns:
                        df['date'] = pd.to_datetime(df['date'])
                        df = df.sort_values('date').reset_index(drop=True)
                    else:
                        df = df.iloc[::-1].reset_index(drop=True)

                    # 只取最後 250 天來計算，節省效能
                    df = df.tail(250).reset_index(drop=True)

                    # --- 原生計算 SMA ---
                    close_series = df['close']
                    df['SMA_20'] = close_series.rolling(window=20).mean()
                    df['SMA_50'] = close_series.rolling(window=50).mean()
                    df['SMA_200'] = close_series.rolling(window=200).mean()

                    # --- 原生計算 MACD ---
                    ema_12 = close_series.ewm(span=12, adjust=False).mean()
                    ema_26 = close_series.ewm(span=26, adjust=False).mean()
                    df['MACD_Line'] = ema_12 - ema_26
                    df['MACD_Signal'] = df['MACD_Line'].ewm(span=9, adjust=False).mean()
                    df['MACD_Hist'] = df['MACD_Line'] - df['MACD_Signal']

                    latest = df.iloc[-1]
                    previous = df.iloc[-2]

                    macd_line, macd_signal, macd_hist = latest['MACD_Line'], latest['MACD_Signal'], latest['MACD_Hist']
                    prev_macd_line, prev_macd_signal, prev_macd_hist = previous['MACD_Line'], previous['MACD_Signal'], previous['MACD_Hist']

                    is_macd_golden = (macd_line > macd_signal) and (prev_macd_line <= prev_macd_signal)
                    is_macd_nearing = (macd_line < macd_signal) and (macd_hist > prev_macd_hist) and (macd_hist > -0.5)
                    macd_pass = is_macd_golden or is_macd_nearing

                    sma20, sma50, sma200, close_price = latest['SMA_20'], latest['SMA_50'], latest['SMA_200'], latest['close']

                    is_sma_aligned = (close_price > sma20) and (sma20 > sma50) and (sma50 > sma200)
                    is_sma_nearing = (close_price > sma20) and (sma20 < sma50) and (abs(sma20 - sma50) / sma50 < 0.02)
                    sma_pass = is_sma_aligned or is_sma_nearing

                    cap_pass = False
                    if not (cap_1 or cap_2 or cap_3 or cap_4 or cap_5):
                        cap_pass = True 
                    else:
                        if cap_1 and market_cap_b < 0.1: cap_pass = True
                        if cap_2 and 0.1 <= market_cap_b < 25: cap_pass = True
                        if cap_3 and 25 <= market_cap_b < 100: cap_pass = True
                        if cap_4 and 100 <= market_cap_b < 500: cap_pass = True
                        if cap_5 and market_cap_b >= 500: cap_pass = True

                    liq_pass = False
                    if not (liq_high or liq_low):
                        liq_pass = True
                    else:
                        if liq_high and volume > 1000000: liq_pass = True
                        if liq_low and volume < 500000: liq_pass = True

                    if filter_macd and not macd_pass: continue
                    if filter_sma and not sma_pass: continue
                    if not cap_pass: continue
                    if not liq_pass: continue

                    if is_macd_golden: macd_status = "黃金交叉"
                    elif is_macd_nearing: macd_status = "即將交叉"
                    else: macd_status = "一般"

                    if is_sma_aligned: sma_status = "多頭排列"
                    elif is_sma_nearing: sma_status = "即將交叉 (< 2% 差距)"
                    else: sma_status = "一般"

                    results.append({
                        "股票代號": ticker,
                        "市值 ($B)": round(market_cap_b, 2) if market_cap_b > 0 else "N/A",
                        "成交量": f"{volume/1000000:.2f}M",
                        "MACD 狀態": macd_status,
                        "SMA 狀態": sma_status
                    })

                except Exception as e:
                    errors.append(f"[{ticker}] 運算錯誤: {str(e)}")

            if len(results) > 0:
                st.success(f"掃描完成！找到 {len(results)} 檔符合條件的股票。")
                df_results = pd.DataFrame(results)
                st.dataframe(df_results, use_container_width=True)
            else:
                st.warning("目前沒有符合所有過濾條件的股票。")
                
            if len(errors) > 0:
                with st.expander("⚠️ 點擊查看略過的股票或錯誤原因"):
                    for err in errors:
                        st.error(err)
