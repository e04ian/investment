import streamlit as st
import yfinance as yf
import pandas as pd
import time
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

# 預設觀察清單
TICKERS = ["AAPL", "NVDA", "TSM", "ASML", "WULF", "ETN", "SMH", "GOOG"]

# ==========================================
# 2. 掃描與計算邏輯
# ==========================================
if st.sidebar.button("開始掃描市場", type="primary"):
    # 提醒使用者現在速度會稍微放慢
    with st.spinner('正在獲取數據並計算指標... (為避免被 Yahoo 阻擋，系統會自動放慢抓取速度，請稍候)'):
        results = []
        errors = []

        # 建立一個偽裝成一般瀏覽器的 Session，降低被阻擋的機率
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

        for ticker in TICKERS:
            try:
                # 使用帶有偽裝的 session 來抓取資料
                stock = yf.Ticker(ticker, session=session)
                df = stock.history(period="1y")
                
                if df.empty or len(df) < 200:
                    errors.append(f"[{ticker}] 歷史數據不足或抓取失敗")
                    continue

                # --- 原生計算 SMA ---
                close_series = df['Close'].squeeze()
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

                # --- MACD 邏輯 ---
                macd_line = latest['MACD_Line']
                macd_signal = latest['MACD_Signal']
                macd_hist = latest['MACD_Hist']
                prev_macd_line = previous['MACD_Line']
                prev_macd_signal = previous['MACD_Signal']
                prev_macd_hist = previous['MACD_Hist']

                is_macd_golden = (macd_line > macd_signal) and (prev_macd_line <= prev_macd_signal)
                is_macd_nearing = (macd_line < macd_signal) and (macd_hist > prev_macd_hist) and (macd_hist > -0.5)
                macd_pass = is_macd_golden or is_macd_nearing

                # --- SMA 邏輯 ---
                sma20 = latest['SMA_20']
                sma50 = latest['SMA_50']
                sma200 = latest['SMA_200']
                close_price = latest['Close'].item() if hasattr(latest['Close'], 'item') else latest['Close']

                is_sma_aligned = (close_price > sma20) and (sma20 > sma50) and (sma50 > sma200)
                is_sma_nearing = (close_price > sma20) and (sma20 < sma50) and (abs(sma20 - sma50) / sma50 < 0.02)
                sma_pass = is_sma_aligned or is_sma_nearing

                # --- 基本面邏輯 (最容易觸發限制的地方) ---
                info = stock.info
                market_cap_b = info.get('marketCap', 0) / 1_000_000_000
                volume = info.get('regularMarketVolume', df['Volume'].iloc[-1])

                # 過濾器檢查
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

                # ==========================================
                # 3. 最終篩選
                # ==========================================
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
            
            # 【關鍵反阻擋機制】：每抓完一檔股票，強迫程式休息 1.5 秒
            time.sleep(1.5)

        # ==========================================
        # 4. 渲染表格與錯誤報告
        # ==========================================
        if len(results) > 0:
            st.success(f"掃描完成！找到 {len(results)} 檔符合條件的股票。")
            df_results = pd.DataFrame(results)
            st.dataframe(df_results, use_container_width=True)
        else:
            st.warning("目前沒有符合所有過濾條件的股票。")
            
        if len(errors) > 0:
            with st.expander("⚠️ 部分股票抓取失敗 (點擊查看原因)"):
                for err in errors:
                    st.error(err)
