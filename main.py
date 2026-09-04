import yfinance as yf
import pandas as pd
import requests
import time
import json
import os
from datetime import datetime, timedelta

# הגדרות טלגרם
TELEGRAM_TOKEN = "8579173089:AAFfb_5fdxOCOW8fkQLQ_K33LkfsdNdiV94"
CHAT_ID = "816211801"

# רשימות מעקב לפי סקטורים
WATCHLISTS = {
    "mag7": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"],
    "growth": ["PLTR", "SOFI", "ADBE", "MU"],
    "chips": ["AMD", "INTC", "TSM", "AVGO", "QCOM", "ARM"],
    "aviation": ["BA", "DAL", "UAL", "LUV", "AAL"],
    "energy": ["XOM", "CVX", "COP", "SLB"],
    "health": ["JNJ", "UNH", "PFE", "ABBV", "LLY"]
}

def send_telegram_message(text, parse_mode="Markdown"):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": parse_mode}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"שגיאת טלגרם: {e}")

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_latest_news(ticker_obj):
    try:
        news = ticker_obj.news
        if news and len(news) > 0:
            return {"title": news[0]['title'], "link": news[0]['link']}
    except:
        pass
    return None

def check_upcoming_earnings(ticker_obj):
    try:
        calendar = ticker_obj.calendar
        if calendar and 'Earnings Date' in calendar:
            earnings_dates = calendar['Earnings Date']
            if len(earnings_dates) > 0:
                next_date = earnings_dates[0].date()
                if (next_date - datetime.now().date()).days <= 14:
                    return str(next_date)
    except:
        pass
    return None

def analyze_stock(ticker, is_mag7=False):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1y")
        if len(hist) < 200:
            return None
            
        close = hist['Close']
        hist['MA50'] = close.rolling(50).mean()
        hist['MA200'] = close.rolling(200).mean()
        hist['RSI'] = calculate_rsi(close)
        
        # MACD
        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        hist['MACD'] = exp1 - exp2
        hist['Signal_Line'] = hist['MACD'].ewm(span=9, adjust=False).mean()
        
        # Volume
        avg_vol = hist['Volume'].rolling(20).mean().iloc[-1]
        current_vol = hist['Volume'].iloc[-1]
        is_high_volume = current_vol > (avg_vol * 1.5)
        
        current_price = close.iloc[-1]
        ma50 = hist['MA50'].iloc[-1]
        ma200 = hist['MA200'].iloc[-1]
        rsi = hist['RSI'].iloc[-1]
        macd = hist['MACD'].iloc[-1]
        
        data = {
            "ticker": ticker,
            "price": round(float(current_price), 2),
            "ma50": round(float(ma50), 2),
            "ma200": round(float(ma200), 2),
            "rsi": round(float(rsi), 2),
            "macd": round(float(macd), 2),
            "high_volume": bool(is_high_volume),
            "signal": "None",
            "entry_point": "N/A"
        }
        
        data["news"] = get_latest_news(stock)
        data["upcoming_earnings"] = check_upcoming_earnings(stock)

        if not is_mag7:
            # לוגיקת איתותים (דוגמה)
            if current_price > ma200 and rsi < 40 and current_price <= ma50 * 1.02:
                data["signal"] = "Pullback"
                data["entry_point"] = f"${round(ma50, 2)} - ${round(ma50 * 1.01, 2)}"
            elif current_price > hist['Close'].rolling(20).max().iloc[-2] and is_high_volume:
                data["signal"] = "Breakout"
                data["entry_point"] = "כניסה מיידית"
            
            if data["signal"] != "None":
                msg = f"*{ticker}*\nתבנית: {data['signal']}\nמחיר: ${data['price']}\nאזור כניסה: {data['entry_point']}\nRSI: {data['rsi']}"
                if is_high_volume:
                    msg += "\n🔥 ווליום חריג!"
                if data["upcoming_earnings"]:
                    msg += f"\n⚠️ דוח קרוב: {data['upcoming_earnings']}"
                send_telegram_message(msg)
                return data
            return None
        else:
            return data
            
    except Exception as e:
        print(f"Error analyzing {ticker}: {e}")
        return None

def run_scan():
    print("מתחיל סריקה...")
    results = {}
    mag7_results = []
    
    for ticker in WATCHLISTS["mag7"]:
        res = analyze_stock(ticker, is_mag7=True)
        if res:
            mag7_results.append(res)
            
    for category, tickers in WATCHLISTS.items():
        if category == "mag7": continue
        results[category] = []
        for ticker in tickers:
            res = analyze_stock(ticker)
            if res:
                results[category].append(res)
                
    save_data(results, mag7_results)
    print("הסריקה הסתיימה בהצלחה!")

def save_data(signals, mag7):
    # שומר את הקובץ בדיוק באותה תיקייה שבה רץ הסקריפט
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, "data.js")
    
    database = {
        "mag7": mag7,
        "signals": signals
    }
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(f"const STOCK_DATABASE = {json.dumps(database, ensure_ascii=False, indent=4)};\n")

if __name__ == "__main__":
    send_telegram_message("🤖 הבוט הופעל וממתין לשעות המסחר...")
    while True:
        now = datetime.now()
        # מריץ בכל שעה עגולה מ-16:30 עד 22:30 בימי חול
        if now.weekday() < 5 and now.hour in range(16, 23) and now.minute == 30:
            run_scan()
            time.sleep(60) # מונע הרצה כפולה באותה דקה
        time.sleep(30)
