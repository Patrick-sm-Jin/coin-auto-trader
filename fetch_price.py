from pybit.unified_trading import HTTP

session = HTTP()  # API 키 없이도 시세 조회 가능!

result = session.get_tickers(
    category="linear",
    symbol="BTCUSDT"
)

price = result["result"]["list"][0]["lastPrice"]
print(f"현재 BTC 가격: {price} USDT")

# 캔들 데이터 불러오기
candles = session.get_kline(
    category="linear",
    symbol="BTCUSDT",
    interval="60",  # 1시간봉
    limit=5         # 최근 5개
)

for candle in candles["result"]["list"]:
    time = candle[0]
    open_price = candle[1]
    high = candle[2]
    low = candle[3]
    close = candle[4]
    volume = candle[5]
    print(f"시가:{open_price} 고가:{high} 저가:{low} 종가:{close}")

    import csv

# CSV로 저장
with open("btc_candles.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["시가", "고가", "저가", "종가", "거래량"])
    for candle in candles["result"]["list"]:
        writer.writerow([candle[1], candle[2], candle[3], candle[4], candle[5]])

print("CSV 저장 완료!")

git add .
git commit -m "Week2: 캔들 데이터 수집 완료"
git push