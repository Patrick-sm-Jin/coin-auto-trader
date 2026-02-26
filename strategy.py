import pandas as pd
from pybit.unified_trading import HTTP

session = HTTP()
candles = session.get_kline(
    category="linear",
    symbol="BTCUSDT",
    interval="15",
    limit=200
)

df = pd.DataFrame(candles["result"]["list"],
    columns=["time", "open", "high", "low", "close", "volume", "turnover"])
df["close"] = df["close"].astype(float)
df = df.iloc[::-1].reset_index(drop=True)

df["EMA7"] = df["close"].ewm(span=7).mean()
df["EMA25"] = df["close"].ewm(span=25).mean()

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

df["RSI"] = calculate_rsi(df["close"])

# 포지션 + 손익 추적
position = None
entry_price = 0
total_pnl = 0
trades = []

# 하루 손절 카운터
daily_losses = 0
MAX_DAILY_LOSSES = 3
trading_stopped = False

for i in range(1, len(df)):
    if trading_stopped:
        print("🚫 오늘 손절 3회 초과 — 매매 중단!")
        break

    ema_bull = df["EMA7"].iloc[i] > df["EMA25"].iloc[i]
    ema_bear = df["EMA7"].iloc[i] < df["EMA25"].iloc[i]
    rsi = df["RSI"].iloc[i]
    price = df["close"].iloc[i]

    if ema_bull and rsi >= 55 and position != "long":
        if position == "short":
            pnl = entry_price - price
            total_pnl += pnl
            trades.append(pnl)
            if pnl < 0:
                daily_losses += 1
                print(f"🔵 숏 청산! 가격: {price} | 손익: {pnl:.1f} USDT ❌ (오늘 손절 {daily_losses}/{MAX_DAILY_LOSSES})")
                if daily_losses >= MAX_DAILY_LOSSES:
                    trading_stopped = True
                    continue
            else:
                print(f"🔵 숏 청산! 가격: {price} | 손익: {pnl:.1f} USDT ✅")
        print(f"🟢 롱 진입! 가격: {price} | RSI: {rsi:.1f}")
        position = "long"
        entry_price = price

    elif ema_bear and rsi <= 45 and position != "short":
        if position == "long":
            pnl = price - entry_price
            total_pnl += pnl
            trades.append(pnl)
            if pnl < 0:
                daily_losses += 1
                print(f"🔵 롱 청산! 가격: {price} | 손익: {pnl:.1f} USDT ❌ (오늘 손절 {daily_losses}/{MAX_DAILY_LOSSES})")
                if daily_losses >= MAX_DAILY_LOSSES:
                    trading_stopped = True
                    continue
            else:
                print(f"🔵 롱 청산! 가격: {price} | 손익: {pnl:.1f} USDT ✅")
        print(f"🔴 숏 진입! 가격: {price} | RSI: {rsi:.1f}")
        position = "short"
        entry_price = price

print(f"\n{'='*40}")
print(f"총 거래 횟수: {len(trades)}")
print(f"승리 횟수: {len([t for t in trades if t > 0])}")
print(f"패배 횟수: {len([t for t in trades if t < 0])}")
print(f"총 손익: {total_pnl:.1f} USDT")
if trades:
    winrate = len([t for t in trades if t > 0]) / len(trades) * 100
    print(f"승률: {winrate:.1f}%")