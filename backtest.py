import pandas as pd
from pybit.unified_trading import HTTP

session = HTTP()

candles = session.get_kline(
    category="linear",
    symbol="BTCUSDT",
    interval="15",
    limit=2000
)

df = pd.DataFrame(candles["result"]["list"],
    columns=["time", "open", "high", "low", "close", "volume", "turnover"])
df["close"] = df["close"].astype(float)
df["time"] = pd.to_datetime(df["time"].astype(float), unit="ms")
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

POSITION_SIZE = 100  # 100 USDT
LEVERAGE = 10
STOP_LOSS_PCT = 0.005    # 10배 기준 5%
TP1_PCT = 0.01           # 1차 익절: 10배 기준 10%
TP2_PCT = 0.02           # 2차 익절: 10배 기준 20%

position = None
entry_price = 0
stop_price = 0
tp1_price = 0
tp2_price = 0
tp1_hit = False          # 1차 익절 완료 여부
remaining_size = POSITION_SIZE  # 남은 포지션 크기

total_pnl = 0
trades = []
daily_losses = 0
MAX_DAILY_LOSSES = 3
current_day = None
day_stopped = False

for i in range(1, len(df)):
    row_day = df["time"].iloc[i].date()

    if row_day != current_day:
        current_day = row_day
        daily_losses = 0
        day_stopped = False

    if day_stopped:
        continue

    ema_bull = df["EMA7"].iloc[i] > df["EMA25"].iloc[i]
    ema_bear = df["EMA7"].iloc[i] < df["EMA25"].iloc[i]
    rsi = df["RSI"].iloc[i]
    price = df["close"].iloc[i]

    if position == "long":
        # 스탑로스
        if price <= stop_price:
            pnl = (price - entry_price) / entry_price * remaining_size * LEVERAGE
            total_pnl += pnl
            trades.append(pnl)
            daily_losses += 1
            print(f"🛑 롱 스탑로스! 가격: {price} | 손익: {pnl:.2f} USDT (손절 {daily_losses}/{MAX_DAILY_LOSSES})")
            position = None
            tp1_hit = False
            remaining_size = POSITION_SIZE
            if daily_losses >= MAX_DAILY_LOSSES:
                day_stopped = True
            continue

        # 1차 익절 (50%)
        if not tp1_hit and price >= tp1_price:
            pnl = (price - entry_price) / entry_price * (POSITION_SIZE * 0.5) * LEVERAGE
            total_pnl += pnl
            trades.append(pnl)
            remaining_size = POSITION_SIZE * 0.5
            stop_price = entry_price  # 스탑을 본전으로 올리기
            tp1_hit = True
            print(f"🟡 롱 1차 익절 (50%)! 가격: {price} | 손익: {pnl:.2f} USDT | 스탑 → 본전")
            continue

        # 2차 익절 (나머지 50%)
        if tp1_hit and price >= tp2_price:
            pnl = (price - entry_price) / entry_price * remaining_size * LEVERAGE
            total_pnl += pnl
            trades.append(pnl)
            print(f"✅ 롱 2차 익절 (50%)! 가격: {price} | 손익: {pnl:.2f} USDT")
            position = None
            tp1_hit = False
            remaining_size = POSITION_SIZE
            continue

    elif position == "short":
        # 스탑로스
        if price >= stop_price:
            pnl = (entry_price - price) / entry_price * remaining_size * LEVERAGE
            total_pnl += pnl
            trades.append(pnl)
            daily_losses += 1
            print(f"🛑 숏 스탑로스! 가격: {price} | 손익: {pnl:.2f} USDT (손절 {daily_losses}/{MAX_DAILY_LOSSES})")
            position = None
            tp1_hit = False
            remaining_size = POSITION_SIZE
            if daily_losses >= MAX_DAILY_LOSSES:
                day_stopped = True
            continue

        # 1차 익절 (50%)
        if not tp1_hit and price <= tp1_price:
            pnl = (entry_price - price) / entry_price * (POSITION_SIZE * 0.5) * LEVERAGE
            total_pnl += pnl
            trades.append(pnl)
            remaining_size = POSITION_SIZE * 0.5
            stop_price = entry_price  # 스탑을 본전으로 올리기
            tp1_hit = True
            print(f"🟡 숏 1차 익절 (50%)! 가격: {price} | 손익: {pnl:.2f} USDT | 스탑 → 본전")
            continue

        # 2차 익절 (나머지 50%)
        if tp1_hit and price <= tp2_price:
            pnl = (entry_price - price) / entry_price * remaining_size * LEVERAGE
            total_pnl += pnl
            trades.append(pnl)
            print(f"✅ 숏 2차 익절 (50%)! 가격: {price} | 손익: {pnl:.2f} USDT")
            position = None
            tp1_hit = False
            remaining_size = POSITION_SIZE
            continue

    # 진입 신호
    if ema_bull and rsi >= 50 and position is None:
        position = "long"
        entry_price = price
        stop_price = price * (1 - STOP_LOSS_PCT)
        tp1_price = price * (1 + TP1_PCT)
        tp2_price = price * (1 + TP2_PCT)
        remaining_size = POSITION_SIZE
        tp1_hit = False
        print(f"🟢 롱 진입! 가격: {price} | 스탑: {stop_price:.1f} | 1차TP: {tp1_price:.1f} | 2차TP: {tp2_price:.1f}")

    elif ema_bear and rsi <= 50 and position is None:
        position = "short"
        entry_price = price
        stop_price = price * (1 + STOP_LOSS_PCT)
        tp1_price = price * (1 - TP1_PCT)
        tp2_price = price * (1 - TP2_PCT)
        remaining_size = POSITION_SIZE
        tp1_hit = False
        print(f"🔴 숏 진입! 가격: {price} | 스탑: {stop_price:.1f} | 1차TP: {tp1_price:.1f} | 2차TP: {tp2_price:.1f}")

wins = [t for t in trades if t > 0]
losses = [t for t in trades if t < 0]

print(f"\n{'='*40}")
print(f"테스트 기간: 약 20일 (15분봉 2000개)")
print(f"스탑: 10배 5% | 1차TP: 10배 10% | 2차TP: 10배 20%")
print(f"총 거래 횟수: {len(trades)}")
print(f"승리: {len(wins)} | 패배: {len(losses)}")
if trades:
    print(f"승률: {len(wins)/len(trades)*100:.1f}%")
    print(f"평균 수익: {sum(wins)/len(wins):.2f} USDT" if wins else "평균 수익: 없음")
    print(f"평균 손실: {sum(losses)/len(losses):.2f} USDT" if losses else "평균 손실: 없음")
    print(f"최대 단일 수익: {max(trades):.2f} USDT")
    print(f"최대 단일 손실: {min(trades):.2f} USDT")
print(f"총 손익: {total_pnl:.2f} USDT")
print(f"{'='*40}")