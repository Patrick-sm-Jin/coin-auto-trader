import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import itertools

plt.rcParams['font.family'] = 'AppleGothic'
plt.rcParams['axes.unicode_minus'] = False

df = pd.read_csv("btc_1h.csv")
df["close"] = df["close"].astype(float)
df["high"] = df["high"].astype(float)
df["low"] = df["low"].astype(float)
df["volume"] = df["volume"].astype(float)
df["time"] = pd.to_datetime(df["time"])
df = df.sort_values("time").reset_index(drop=True)

# 최근 6개월만 사용
cutoff = df["time"].iloc[-1] - pd.Timedelta(days=180)
df = df[df["time"] >= cutoff].reset_index(drop=True)

print(f"데이터 기간: {df['time'].iloc[0]} ~ {df['time'].iloc[-1]}")
print(f"총 캔들 수: {len(df)}")

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

# RSI
delta = df["close"].diff()
gain = delta.where(delta > 0, 0).rolling(14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
rs = gain / loss
df["RSI"] = 100 - (100 / (1 + rs))

# 고정 설정
LEVERAGE = 5
MAKER_FEE = 0.00018
TAKER_FEE = 0.000495
BASE_POSITION_SIZE = 100
INITIAL_CAPITAL = 1000
STOP_LOSS_PCT = 0.010
MAX_DAILY_LOSSES = 2

def calc_fee(size, fee_type):
    rate = TAKER_FEE if fee_type == "taker" else MAKER_FEE
    return size * LEVERAGE * rate

def run_backtest(TP_PCT, VOL_MULT, RSI_LONG, RSI_SHORT):
    position = None
    entry_price = 0
    stop_price = 0
    tp_price = 0
    remaining_size = BASE_POSITION_SIZE

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
        rsi = df["RSI"].iloc[i]
        current_time = df["time"].iloc[i]

        vol_ok = vol > vol_ma * VOL_MULT
        atr_ok = atr > atr_ma

        long_signal = (
            price > ema50 and slope > 0 and
            hist > 0 and prev_hist <= 0 and
            macd > 0 and vol_ok and atr_ok and
            rsi < RSI_LONG
        )
        short_signal = (
            price < ema50 and slope < 0 and
            hist < 0 and prev_hist >= 0 and
            macd < 0 and vol_ok and atr_ok and
            rsi > RSI_SHORT
        )

        if position == "long":
            if price <= stop_price:
                fee = calc_fee(remaining_size, "taker")
                pnl = (price - entry_price) / entry_price * remaining_size * LEVERAGE - fee
                total_pnl += pnl
                total_fee += fee
                trades.append({"pnl": pnl, "time": current_time})
                daily_losses += 1
                position = None
                remaining_size = BASE_POSITION_SIZE
                if daily_losses >= MAX_DAILY_LOSSES:
                    day_stopped = True
                continue

            if price >= tp_price:
                fee = calc_fee(remaining_size, "maker")
                pnl = (price - entry_price) / entry_price * remaining_size * LEVERAGE - fee
                total_pnl += pnl
                total_fee += fee
                trades.append({"pnl": pnl, "time": current_time})
                reinvest_pool += pnl
                position = None
                remaining_size = BASE_POSITION_SIZE
                continue

        elif position == "short":
            if price >= stop_price:
                fee = calc_fee(remaining_size, "taker")
                pnl = (entry_price - price) / entry_price * remaining_size * LEVERAGE - fee
                total_pnl += pnl
                total_fee += fee
                trades.append({"pnl": pnl, "time": current_time})
                daily_losses += 1
                position = None
                remaining_size = BASE_POSITION_SIZE
                if daily_losses >= MAX_DAILY_LOSSES:
                    day_stopped = True
                continue

            if price <= tp_price:
                fee = calc_fee(remaining_size, "maker")
                pnl = (entry_price - price) / entry_price * remaining_size * LEVERAGE - fee
                total_pnl += pnl
                total_fee += fee
                trades.append({"pnl": pnl, "time": current_time})
                reinvest_pool += pnl
                position = None
                remaining_size = BASE_POSITION_SIZE
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
            tp_price = price * (1 + TP_PCT)
            remaining_size = current_position_size
            print(f"🟢 롱 진입! {price:.1f} | 스탑: {stop_price:.1f} | TP: {tp_price:.1f}")

        elif short_signal and position is None:
            current_position_size = BASE_POSITION_SIZE + reinvest_pool
            reinvest_pool = 0
            fee = calc_fee(current_position_size, "taker")
            total_pnl -= fee
            total_fee += fee
            position = "short"
            entry_price = price
            stop_price = price * (1 + STOP_LOSS_PCT)
            tp_price = price * (1 - TP_PCT)
            remaining_size = current_position_size
            print(f"🔴 숏 진입! {price:.1f} | 스탑: {stop_price:.1f} | TP: {tp_price:.1f}")

    pnl_list = [t["pnl"] for t in trades]
    if not pnl_list:
        return None

    wins = [t for t in pnl_list if t > 0]
    losses = [t for t in pnl_list if t < 0]
    final_capital = INITIAL_CAPITAL + total_pnl
    total_return = (final_capital - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100

    equity_arr = np.array([INITIAL_CAPITAL] + [INITIAL_CAPITAL + sum(pnl_list[:i+1]) for i in range(len(pnl_list))])
    mdd = ((equity_arr - np.maximum.accumulate(equity_arr)) / np.maximum.accumulate(equity_arr)).min() * 100

    total_weeks = (df["time"].iloc[-1] - df["time"].iloc[0]).days / 7
    avg_trades_per_week = round(len(trades) / total_weeks, 1)

    return {
        "TP(%)": round(TP_PCT * 100, 1),
        "VOL배수": VOL_MULT,
        "RSI롱": RSI_LONG,
        "RSI숏": RSI_SHORT,
        "수익률": round(total_return, 2),
        "승률": round(len(wins)/len(pnl_list)*100, 1),
        "MDD": round(mdd, 2),
        "거래수": len(trades),
        "주당거래": avg_trades_per_week,
        "평균수익": round(sum(wins)/len(wins), 2) if wins else 0,
        "평균손실": round(sum(losses)/len(losses), 2) if losses else 0,
    }

# 파라미터 범위
tp_list        = [0.010, 0.015, 0.020, 0.025, 0.030]
vol_list       = [1.2, 1.5, 1.8]
rsi_long_list  = [60, 65, 70]
rsi_short_list = [30, 35, 40]

results = []
total_combos = len(tp_list) * len(vol_list) * len(rsi_long_list) * len(rsi_short_list)
count = 0

print(f"\n총 {total_combos}가지 조합 테스트 시작...")

for tp, vol, rsi_l, rsi_s in itertools.product(tp_list, vol_list, rsi_long_list, rsi_short_list):
    count += 1
    if count % 15 == 0:
        print(f"진행중... {count}/{total_combos}")
    result = run_backtest(tp, vol, rsi_l, rsi_s)
    if result:
        results.append(result)

results_df = pd.DataFrame(results)

# 주당 2~4번 필터링
filtered = results_df[
    (results_df["주당거래"] >= 2) &
    (results_df["주당거래"] <= 4)
]

print(f"\n{'='*90}")
print(f"🏆 TOP 10 (수익률 기준) | 주당 2~4번 | 레버리지 {LEVERAGE}배 | 손절 1%")
print(f"{'='*90}")
if len(filtered) > 0:
    print(filtered.sort_values("수익률", ascending=False).head(10).to_string(index=False))
else:
    print("⚠️ 주당 2~4번 조건 없음 → 전체 결과 (주당거래 기준 정렬)")
    print(results_df.sort_values("주당거래").head(10).to_string(index=False))

print(f"\n{'='*90}")
print(f"🛡️ TOP 10 (MDD 기준) | 주당 2~4번 | 레버리지 {LEVERAGE}배 | 손절 1%")
print(f"{'='*90}")
if len(filtered) > 0:
    print(filtered.sort_values("MDD", ascending=False).head(10).to_string(index=False))
else:
    print(results_df.sort_values("MDD", ascending=False).head(10).to_string(index=False))

print(f"\n📊 주당거래 분포:")
print(results_df["주당거래"].value_counts().sort_index().to_string())