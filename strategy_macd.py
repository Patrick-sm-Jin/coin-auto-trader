import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

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

# 최적 설정
BASE_POSITION_SIZE = 100
LEVERAGE = 10
STOP_LOSS_PCT = 0.008
TP1_PCT = 0.003
TP2_PCT = 0.035
TRAIL_PCT = 0.045
MAKER_FEE = 0.00018
TAKER_FEE = 0.000495
VOL_MULTIPLIER = 1.5
INITIAL_CAPITAL = 1000
MAX_DAILY_LOSSES = 3

def calc_fee(size, fee_type):
    rate = TAKER_FEE if fee_type == "taker" else MAKER_FEE
    return size * LEVERAGE * rate

# 상태 변수
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

# 기록
total_pnl = 0
trades = []
total_fee = 0
reinvest_pool = 0

# 일일 손절 제한
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
                print(f"🏁 롱 트레일링 청산! {price:.1f} | {pnl:.2f} USDT")
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
            print(f"🛑 롱 스탑! {price:.1f} | {pnl:.2f} USDT ({daily_losses}/{MAX_DAILY_LOSSES})")
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
            print(f"🟡 롱 1차 익절! {price:.1f} | {pnl:.2f} USDT | 풀: {reinvest_pool:.2f}")
            continue

        if tp1_hit and not trailing_active and price <= stop_price:
            fee = calc_fee(remaining_size, "taker")
            pnl = (price - entry_price) / entry_price * remaining_size * LEVERAGE - fee
            total_pnl += pnl
            total_fee += fee
            trades.append({"pnl": pnl, "time": current_time})
            print(f"🛑 롱 본전 스탑! {price:.1f} | {pnl:.2f} USDT")
            position = None
            tp1_hit = False
            remaining_size = BASE_POSITION_SIZE
            continue

        if tp1_hit and not trailing_active and price >= tp2_price:
            trailing_active = True
            highest_price = price
            trailing_stop = price * (1 - TRAIL_PCT)
            print(f"🚀 롱 트레일링 시작! {price:.1f} | 트레일 스탑: {trailing_stop:.1f}")
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
                print(f"🏁 숏 트레일링 청산! {price:.1f} | {pnl:.2f} USDT")
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
            print(f"🛑 숏 스탑! {price:.1f} | {pnl:.2f} USDT ({daily_losses}/{MAX_DAILY_LOSSES})")
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
            print(f"🟡 숏 1차 익절! {price:.1f} | {pnl:.2f} USDT | 풀: {reinvest_pool:.2f}")
            continue

        if tp1_hit and not trailing_active and price >= stop_price:
            fee = calc_fee(remaining_size, "taker")
            pnl = (entry_price - price) / entry_price * remaining_size * LEVERAGE - fee
            total_pnl += pnl
            total_fee += fee
            trades.append({"pnl": pnl, "time": current_time})
            print(f"🛑 숏 본전 스탑! {price:.1f} | {pnl:.2f} USDT")
            position = None
            tp1_hit = False
            remaining_size = BASE_POSITION_SIZE
            continue

        if tp1_hit and not trailing_active and price <= tp2_price:
            trailing_active = True
            lowest_price = price
            trailing_stop = price * (1 + TRAIL_PCT)
            print(f"🚀 숏 트레일링 시작! {price:.1f} | 트레일 스탑: {trailing_stop:.1f}")
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
        print(f"🟢 롱 진입! {price:.1f} | 사이즈: {current_position_size:.1f} | 스탑: {stop_price:.1f} | TP1: {tp1_price:.1f} | TP2: {tp2_price:.1f}")

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
        print(f"🔴 숏 진입! {price:.1f} | 사이즈: {current_position_size:.1f} | 스탑: {stop_price:.1f} | TP1: {tp1_price:.1f} | TP2: {tp2_price:.1f}")

# 결과
pnl_list = [t["pnl"] for t in trades]
wins = [t for t in pnl_list if t > 0]
losses = [t for t in pnl_list if t < 0]

final_capital = INITIAL_CAPITAL + total_pnl
total_return = (final_capital - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100

equity_curve = [INITIAL_CAPITAL]
cap = INITIAL_CAPITAL
for t in pnl_list:
    cap += t
    equity_curve.append(cap)
equity_arr = np.array(equity_curve)
mdd = ((equity_arr - np.maximum.accumulate(equity_arr)) / np.maximum.accumulate(equity_arr)).min() * 100

print(f"\n{'='*40}")
print(f"전략: MACD + EMA50 + 거래량 + ATR + 트레일링 + 복리")
print(f"STOP: {STOP_LOSS_PCT*100}% | TP1: {TP1_PCT*100}% | TP2: {TP2_PCT*100}% | TRAIL: {TRAIL_PCT*100}%")
print(f"총 거래 횟수: {len(trades)}")
print(f"승리: {len(wins)} | 패배: {len(losses)}")
if trades:
    print(f"승률: {len(wins)/len(trades)*100:.1f}%")
    print(f"평균 수익: {sum(wins)/len(wins):.2f} USDT" if wins else "평균 수익: 없음")
    print(f"평균 손실: {sum(losses)/len(losses):.2f} USDT" if losses else "평균 손실: 없음")
    print(f"최대 단일 수익: {max(pnl_list):.2f} USDT")
    print(f"최대 단일 손실: {min(pnl_list):.2f} USDT")
print(f"총 수수료: {total_fee:.2f} USDT")
print(f"총 손익 (수수료 포함): {total_pnl:.2f} USDT")
print(f"초기 시드: {INITIAL_CAPITAL} USDT")
print(f"최종 시드: {final_capital:.2f} USDT")
print(f"총 수익률: {total_return:.2f}%")
print(f"MDD: {mdd:.2f}%")
print(f"{'='*40}")

# 기간별 성과
print(f"\n{'='*40}")
print(f"📅 기간별 성과 분석")
print(f"{'='*40}")

end_date = df["time"].iloc[-1]
periods = {
    "1개월":  30,
    "3개월":  90,
    "6개월":  180,
    "9개월":  270,
    "12개월": 365
}

for label, days in periods.items():
    start_date = end_date - pd.Timedelta(days=days)
    period_trades = [t["pnl"] for t in trades if t["time"] >= start_date]

    if not period_trades:
        print(f"\n📌 {label}: 거래 없음")
        continue

    p_wins = [t for t in period_trades if t > 0]
    p_losses = [t for t in period_trades if t < 0]
    p_pnl = sum(period_trades)
    p_return = p_pnl / INITIAL_CAPITAL * 100
    p_wr = len(p_wins) / len(period_trades) * 100

    p_equity = [INITIAL_CAPITAL]
    c = INITIAL_CAPITAL
    for t in period_trades:
        c += t
        p_equity.append(c)
    p_arr = np.array(p_equity)
    p_mdd = ((p_arr - np.maximum.accumulate(p_arr)) / np.maximum.accumulate(p_arr)).min() * 100

    print(f"\n📌 {label} ({start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')})")
    print(f"  거래: {len(period_trades)}번 | 승률: {p_wr:.1f}%")
    print(f"  평균 수익: {sum(p_wins)/len(p_wins):.2f} USDT" if p_wins else "  평균 수익: 없음")
    print(f"  평균 손실: {sum(p_losses)/len(p_losses):.2f} USDT" if p_losses else "  평균 손실: 없음")
    print(f"  손익: {p_pnl:.2f} USDT | 수익률: {p_return:.2f}% | MDD: {p_mdd:.2f}%")

# 차트
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 12))

cumulative = []
total = 0
for t in pnl_list:
    total += t
    cumulative.append(total)

ax1.plot(cumulative, color="cyan", linewidth=1.5)
ax1.axhline(0, color="red", linestyle="--", alpha=0.5)
ax1.fill_between(range(len(cumulative)), cumulative, 0,
    where=[c > 0 for c in cumulative], color="green", alpha=0.3)
ax1.fill_between(range(len(cumulative)), cumulative, 0,
    where=[c < 0 for c in cumulative], color="red", alpha=0.3)
ax1.set_title("누적 손익 곡선")
ax1.set_ylabel("USDT")
ax1.grid(True, alpha=0.3)

ax2.plot(equity_curve, color="gold", linewidth=1.5)
ax2.axhline(INITIAL_CAPITAL, color="white", linestyle="--", alpha=0.5)
ax2.set_title(f"자산 곡선 (초기: {INITIAL_CAPITAL} → 최종: {final_capital:.0f} USDT | 수익률: {total_return:.1f}% | MDD: {mdd:.1f}%)")
ax2.set_ylabel("USDT")
ax2.grid(True, alpha=0.3)

colors = ["green" if t > 0 else "red" for t in pnl_list]
ax3.bar(range(len(pnl_list)), pnl_list, color=colors, alpha=0.7, width=1)
ax3.axhline(0, color="white", linestyle="--", alpha=0.5)
ax3.set_title(f"거래별 손익 (총 {len(trades)}번 | 승률 {len(wins)/len(trades)*100:.1f}%)" if trades else "거래 없음")
ax3.set_ylabel("USDT")
ax3.grid(True, alpha=0.3)

plt.tight_layout()
plt.show()