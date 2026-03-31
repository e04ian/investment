import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta

# ==========================================
# 1. 介面設定 (全中文 Checkbox)
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

# 預設觀察清單
TICKERS = ["AAPL", "NVDA", "TSM", "ASML", "q", "ETN", "SMH", "GOOG"]

# ==========================================
# 2. 掃描與計算邏輯
# ==========================================
if st.sidebar.button("開始掃描市場", type="primary"):
    with st.spinner('正在獲取數據並計算指標...'):
        results = []

        for ticker in TICKERS:
            try:
                # 下載歷史數據
                df = yf.download(ticker, period="1y", interval="1d", progress=False)
                if df.empty or len(df) < 200:
                    continue

                # 計算指標
                df.ta.macd(close='Close', fast=12, slow=26, signal=9, append=True)
                df.ta.sma(length=20, append=True)
                df.ta.sma(length=50, append=True)
                df.ta.sma(length=200, append=True)

                latest = df.iloc[-1]
                previous = df.iloc[-2]

                # --- MACD 邏輯 ---
                macd_line = latest['MACD_12_26_9']
                macd_signal = latest['MACDs_12_26_9']
                macd_hist = latest['MACDh_12_26_9']
                prev_macd_line = previous['MACD_12_26_9']
                prev_macd_signal = previous['MACDs_12_26_9']
                prev_macd_hist = previous['MACDh_12_26_9']

                # 條件 A：已經黃金交叉
                is_macd_golden = (macd_line > macd_signal) and (prev_macd_line <= prev_macd_signal)
                
                # 條件 B：即將交叉 (柱狀圖為負但正在向上收斂)
                is_macd_nearing = (macd_line < macd_signal) and (macd_hist > prev_macd_hist) and (macd_hist > -0.5)

                macd_pass = is_macd_golden or is_macd_nearing

                # --- SMA 邏輯 ---
                sma20 = latest['SMA_20']
                sma50 = latest['SMA_50']
                sma200 = latest['SMA_200']
                close_price = latest['Close']

                # 條件 A：多頭排列
                is_sma_aligned = (close_price > sma20) and (sma20 > sma50) and (sma50 > sma200)

                # 條件 B：即將交叉 (價格在20T之上，且20T與50T差距小於2%)
                is_sma_nearing = (close_price > sma20) and (sma20 < sma50) and (abs(sma20 - sma50) / sma50 < 0.02)

                sma_pass = is_sma_aligned or is_sma_nearing

                # --- 基本面邏輯 ---
                info = yf.Ticker(ticker).info
                market_cap_b = info.get('marketCap', 0) / 1_000_000_000
                volume = info.get('regularMarketVolume', 0)

                # 市值級距檢查
                cap_pass = False
                if not (cap_1 or cap_2 or cap_3 or cap_4 or cap_5):
                    cap_pass = True 
                else:
                    if cap_1 and market_cap_b < 0.1: cap_pass = True
                    if cap_2 and 0.1 <= market_cap_b < 25: cap_pass = True
                    if cap_3 and 25 <= market_cap_b < 100: cap_pass = True
                    if cap_4 and 100 <= market_cap_b < 500: cap_pass = True
                    if cap_5 and market_cap_b >= 500: cap_pass = True

                # 流動性檢查
                liq_pass = False
                if not (liq_high or liq_low):
                    liq_pass = True
                else:
                    if liq_high and volume > 1000000: liq_pass = True
                    if liq_low and volume < 500000: liq_pass = True

                # ==========================================
                # 3. 最終篩選
                # ==========================================
                if filter_macd and not macd_pass: continue
                if filter_sma and not sma_pass: continue
                if not cap_pass: continue
                if not liq_pass: continue

                # 決定顯示狀態
                if is_macd_golden: macd_status = "黃金交叉"
                elif is_macd_nearing: macd_status = "即將交叉"
                else: macd_status = "一般"

                if is_sma_aligned: sma_status = "多頭排列"
                elif is_sma_nearing: sma_status = "即將交叉 (< 2% 差距)"
                else: sma_status = "一般"

                results.append({
                    "股票代號": ticker,
                    "市值 ($B)": round(market_cap_b, 2),
                    "成交量": f"{volume/1000000:.2f}M",
                    "MACD 狀態": macd_status,
                    "SMA 狀態": sma_status
                })

            except Exception as e:
                pass # 略過數據缺失或發生錯誤的股票

        # ==========================================
        # 4. 渲染表格
        # ==========================================
        if len(results) > 0:
            st.success(f"掃描完成！找到 {len(results)} 檔符合條件的股票。")
            df_results = pd.DataFrame(results)
            st.dataframe(df_results, use_container_width=True)
        else:
            st.warning("目前沒有符合所有過濾條件的股票。")
