from binance.client import Client
import pandas as pd

client = Client()

klines = client.get_historical_klines(
    "BTCUSDT",
    Client.KLINE_INTERVAL_1HOUR,
    "1 Jan, 2022"
)

df = pd.DataFrame(klines, columns=[
    "time", "open", "high", "low", "close",
    "volume", "close_time", "quote_volume",
    "trades", "taker_buy_base", "taker_buy_quote", "ignore"
])

df["close"] = df["close"].astype(float)
df["time"] = pd.to_datetime(df["time"], unit="ms")
df = df[["time", "open", "high", "low", "close"]]
df.to_csv("btc_1h.csv", index=False)

print(f"데이터 기간: {df['time'].iloc[0]} ~ {df['time'].iloc[-1]}")
print(f"총 캔들 수: {len(df)}")