import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import itertools

# 맥 한글 폰트
plt.rcParams['font.family'] = 'AppleGothic'
plt.rcParams['axes.unicode_minus'] = False

# 데이터 로드
df = pd.read_csv("btc_1h.csv")
df["close"] = df["close"].astype(float)
df["high"] = df["high"].astype(float)
df["low"] = df["low"].astype(float)
df["volume"] = df["volume"].astype(float)
df["time"] = pd.to_datetime(df["time"])
df = df.sort_values("time").reset_index(drop=True)

# 지표 계산
df["EMA50"] = df["close"].ewm(span=50).mean()
df["EMA50_slope"] = df["EMA50"].diff()

ema12 = df["close"].ewm(span=12).mean()
ema26 = df["close"].ewm(span=26).mean()
df["MACD"] = ema12 - ema26
df["SIGNAL"] = df["MACD"].ewm(span=9).mean()
df["HIST"] = df["MACD"] - df["SIGNAL"]

tr = pd.concat([
    df["high"] - df["low"],
    (df["high"] - df["close"].shift()).abs(),
    (df["low"] - df["close"].shift()).abs()
], axis=1).max(axis=1)
df["ATR"] = tr.rolling(14).mean()
df["ATR_MA"] = df["ATR"].rolling(30).mean()
df["VOL_MA"] = df["volume"].rolling(20).mean()

# 고정 설정
LEVERAGE = 10
MAKER_FEE = 0.00018
TAKER_FEE = 0.000495
VOL_MULTIPLIER = 1.5
BASE_POSITION_SIZE = 100
INITIAL_CAPITAL = 1000
MAX_DAILY_LOSSES = 3

def calc_fee(size, fee_type):
    rate = TAKER_FEE if fee_type == "taker" else MAKER_FEE
    return size * LEVERAGE * rate

def run_backtest(STOP_LOSS_PCT, TP1_PCT, TP2_PCT, TRAIL_PCT):
    position = None
    entry_price = 0
    stop_price = 0
    tp1_price = 0
    tp2_price = 0
    tp1_hit = False
    remaining_size = BASE_POSITION_SIZE
    trailing_active = False
    trailing_stop = 0
    highest_price = 0
    lowest_price = 0

    total_pnl = 0
    trades = []
    total_fee = 0
    reinvest_pool = 0

    daily_losses = 0
    current_day = None
    day_stopped = False

    for i in range(50, len(df)):
        row_day = df["time"].iloc[i].date()

        if row_day != current_day:
            current_day = row_day
            daily_losses = 0
            day_stopped = False

        if day_stopped:
            continue

        price = df["close"].iloc[i]
        macd = df["MACD"].iloc[i]
        hist = df["HIST"].iloc[i]
        prev_hist = df["HIST"].iloc[i-1]
        ema50 = df["EMA50"].iloc[i]
        slope = df["EMA50_slope"].iloc[i]
        atr = df["ATR"].iloc[i]
        atr_ma = df["ATR_MA"].iloc[i]
        vol = df["volume"].iloc[i]
        vol_ma = df["VOL_MA"].iloc[i]
        current_time = df["time"].iloc[i]

        vol_ok = vol > vol_ma * VOL_MULTIPLIER
        atr_ok = atr > atr_ma

        long_signal = (
            price > ema50 and slope > 0 and
            hist > 0 and prev_hist <= 0 and
            macd > 0 and vol_ok and atr_ok
        )
        short_signal = (
            price < ema50 and slope < 0 and
            hist < 0 and prev_hist >= 0 and
            macd < 0 and vol_ok and atr_ok
        )

        if position == "long":
            if trailing_active:
                if price > highest_price:
                    highest_price = price
                    trailing_stop = price * (1 - TRAIL_PCT)
                if price <= trailing_stop:
                    fee = calc_fee(remaining_size, "taker")
                    pnl = (price - entry_price) / entry_price * remaining_size * LEVERAGE - fee
                    total_pnl += pnl
                    total_fee += fee
                    trades.append({"pnl": pnl, "time": current_time})
                    position = None
                    tp1_hit = False
                    trailing_active = False
                    remaining_size = BASE_POSITION_SIZE
                    continue

            if not trailing_active and price <= stop_price:
                fee = calc_fee(remaining_size, "taker")
                pnl = (price - entry_price) / entry_price * remaining_size * LEVERAGE - fee
                total_pnl += pnl
                total_fee += fee
                trades.append({"pnl": pnl, "time": current_time})
                daily_losses += 1
                position = None
                tp1_hit = False
                remaining_size = BASE_POSITION_SIZE
                if daily_losses >= MAX_DAILY_LOSSES:
                    day_stopped = True
                continue

            if not tp1_hit and price >= tp1_price:
                half = remaining_size * 0.5
                fee = calc_fee(half, "maker")
                pnl = (price - entry_price) / entry_price * half * LEVERAGE - fee
                total_pnl += pnl
                total_fee += fee
                trades.append({"pnl": pnl, "time": current_time})
                reinvest_pool += pnl
                remaining_size = half
                stop_price = entry_price
                tp1_hit = True
                continue

            if tp1_hit and not trailing_active and price <= stop_price:
                fee = calc_fee(remaining_size, "taker")
                pnl = (price - entry_price) / entry_price * remaining_size * LEVERAGE - fee
                total_pnl += pnl
                total_fee += fee
                trades.append({"pnl": pnl, "time": current_time})
                position = None
                tp1_hit = False
                remaining_size = BASE_POSITION_SIZE
                continue

            if tp1_hit and not trailing_active and price >= tp2_price:
                trailing_active = True
                highest_price = price
                trailing_stop = price * (1 - TRAIL_PCT)
                continue

        elif position == "short":
            if trailing_active:
                if price < lowest_price:
                    lowest_price = price
                    trailing_stop = price * (1 + TRAIL_PCT)
                if price >= trailing_stop:
                    fee = calc_fee(remaining_size, "taker")
                    pnl = (entry_price - price) / entry_price * remaining_size * LEVERAGE - fee
                    total_pnl += pnl
                    total_fee += fee
                    trades.append({"pnl": pnl, "time": current_time})
                    position = None
                    tp1_hit = False
                    trailing_active = False
                    remaining_size = BASE_POSITION_SIZE
                    continue

            if not trailing_active and price >= stop_price:
                fee = calc_fee(remaining_size, "taker")
                pnl = (entry_price - price) / entry_price * remaining_size * LEVERAGE - fee
                total_pnl += pnl
                total_fee += fee
                trades.append({"pnl": pnl, "time": current_time})
                daily_losses += 1
                position = None
                tp1_hit = False
                remaining_size = BASE_POSITION_SIZE
                if daily_losses >= MAX_DAILY_LOSSES:
                    day_stopped = True
                continue

            if not tp1_hit and price <= tp1_price:
                half = remaining_size * 0.5
                fee = calc_fee(half, "maker")
                pnl = (entry_price - price) / entry_price * half * LEVERAGE - fee
                total_pnl += pnl
                total_fee += fee
                trades.append({"pnl": pnl, "time": current_time})
                reinvest_pool += pnl
                remaining_size = half
                stop_price = entry_price
                tp1_hit = True
                continue

            if tp1_hit and not trailing_active and price >= stop_price:
                fee = calc_fee(remaining_size, "taker")
                pnl = (entry_price - price) / entry_price * remaining_size * LEVERAGE - fee
                total_pnl += pnl
                total_fee += fee
                trades.append({"pnl": pnl, "time": current_time})
                position = None
                tp1_hit = False
                remaining_size = BASE_POSITION_SIZE
                continue

            if tp1_hit and not trailing_active and price <= tp2_price:
                trailing_active = True
                lowest_price = price
                trailing_stop = price * (1 + TRAIL_PCT)
                continue

        if long_signal and position is None:
            current_position_size = BASE_POSITION_SIZE + reinvest_pool
            reinvest_pool = 0
            fee = calc_fee(current_position_size, "taker")
            total_pnl -= fee
            total_fee += fee
            position = "long"
            entry_price = price
            stop_price = price * (1 - STOP_LOSS_PCT)
            tp1_price = price * (1 + TP1_PCT)
            tp2_price = price * (1 + TP2_PCT)
            remaining_size = current_position_size
            tp1_hit = False
            trailing_active = False

        elif short_signal and position is None:
            current_position_size = BASE_POSITION_SIZE + reinvest_pool
            reinvest_pool = 0
            fee = calc_fee(current_position_size, "taker")
            total_pnl -= fee
            total_fee += fee
            position = "short"
            entry_price = price
            stop_price = price * (1 + STOP_LOSS_PCT)
            tp1_price = price * (1 - TP1_PCT)
            tp2_price = price * (1 - TP2_PCT)
            remaining_size = current_position_size
            tp1_hit = False
            trailing_active = False

    pnl_list = [t["pnl"] for t in trades]
    if not pnl_list:
        return None

    wins = [t for t in pnl_list if t > 0]
    losses = [t for t in pnl_list if t < 0]
    final_capital = INITIAL_CAPITAL + total_pnl
    total_return = (final_capital - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100

    equity_arr = np.array([INITIAL_CAPITAL] + [INITIAL_CAPITAL + sum(pnl_list[:i+1]) for i in range(len(pnl_list))])
    mdd = ((equity_arr - np.maximum.accumulate(equity_arr)) / np.maximum.accumulate(equity_arr)).min() * 100

    return {
        "STOP": STOP_LOSS_PCT,
        "TP1": TP1_PCT,
        "TP2": TP2_PCT,
        "TRAIL": TRAIL_PCT,
        "수익률": round(total_return, 2),
        "승률": round(len(wins)/len(pnl_list)*100, 1),
        "MDD": round(mdd, 2),
        "거래수": len(trades),
        "평균수익": round(sum(wins)/len(wins), 2) if wins else 0,
        "평균손실": round(sum(losses)/len(losses), 2) if losses else 0,
    }

# 파라미터 조합 테스트
stop_list  = [0.006, 0.008, 0.010, 0.012]
tp1_list   = [0.010, 0.015, 0.020, 0.025, 0.003]
tp2_list   = [0.025, 0.030, 0.035, 0.040, 0.045]
trail_list = [0.020, 0.025, 0.030, 0.035, 0.040, 0.045, 0.050, 0.055, 0.060]

results = []
total = len(stop_list) * len(tp1_list) * len(tp2_list) * len(trail_list)
count = 0

for stop, tp1, tp2, trail in itertools.product(stop_list, tp1_list, tp2_list, trail_list):
    if tp1 >= tp2:
        continue
    count += 1
    if count % 10 == 0:
        print(f"진행중... {count}/{total}")
    result = run_backtest(stop, tp1, tp2, trail)
    if result:
        results.append(result)

# 결과 출력
results_df = pd.DataFrame(results)
results_df = results_df.sort_values("수익률", ascending=False)

print(f"\n{'='*70}")
print(f"🏆 TOP 10 파라미터 조합 (수익률 기준)")
print(f"{'='*70}")
print(results_df.head(10).to_string(index=False))

print(f"\n{'='*70}")
print(f"🛡️ TOP 10 파라미터 조합 (MDD 기준 - 안정성)")
print(f"{'='*70}")
print(results_df.sort_values("MDD", ascending=False).head(10).to_string(index=False))