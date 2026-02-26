from binance.client import Client
import pandas as pd

client = Client()
symbol = "BTCUSDT"

def save_klines(interval, filename):

    klines = client.get_historical_klines(symbol, interval, "1 Jan 2023")

    df = pd.DataFrame(klines, columns=[
        'time','open','high','low','close','volume',
        'close_time','qav','num_trades',
        'taker_base_vol','taker_quote_vol','ignore'
    ])

    df['time'] = pd.to_datetime(df['time'], unit='ms')

    df[['time','open','high','low','close','volume']].to_csv(filename, index=False)
    print(filename, "저장 완료")

save_klines(Client.KLINE_INTERVAL_15MINUTE, "btc_15m.csv")
save_klines(Client.KLINE_INTERVAL_1HOUR, "btc_1h.csv")
save_klines(Client.KLINE_INTERVAL_4HOUR, "btc_4h.csv")