import pandas as pd
import matplotlib.pyplot as plt
from pybit.unified_trading import HTTP

# 데이터 불러오기
session = HTTP()
candles = session.get_kline(
    category="linear",
    symbol="BTCUSDT",
    interval="60",
    limit=200
)

# 데이터프레임 만들기
df = pd.DataFrame(candles["result"]["list"],
    columns=["time", "open", "high", "low", "close", "volume", "turnover"])
df["close"] = df["close"].astype(float)

# 이동평균선
df["MA7"] = df["close"].rolling(7).mean()
df["MA25"] = df["close"].rolling(25).mean()

# RSI
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

df["RSI"] = calculate_rsi(df["close"])

# 차트
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

ax1.plot(df["close"], label="BTC 가격", color="white", linewidth=1)
ax1.plot(df["MA7"], label="MA7", color="orange", linewidth=1.5)
ax1.plot(df["MA25"], label="MA25", color="cyan", linewidth=1.5)
ax1.set_title("BTC/USDT 가격 + 이동평균선")
ax1.legend()
ax1.grid(True, alpha=0.3)

ax2.plot(df["RSI"], label="RSI", color="purple")
ax2.axhline(70, color="red", linestyle="--", label="과매수(70)")
ax2.axhline(30, color="green", linestyle="--", label="과매도(30)")
ax2.set_title("RSI 지표")
ax2.legend()
ax2.grid(True, alpha=0.3)

plt.tight_layout()
plt.show()