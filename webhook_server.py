from flask import Flask, request, jsonify
from pybit.unified_trading import HTTP
import json
import re
from datetime import datetime

app = Flask(__name__)

# Bybit API 설정
from config import API_KEY, API_SECRET

session = HTTP(
    testnet=False,
    api_key=API_KEY,
    api_secret=API_SECRET
)

SYMBOL = "BTCUSDT"
LEVERAGE = 5

# 레버리지 설정
def set_leverage():
    try:
        session.set_leverage(
            category="linear",
            symbol=SYMBOL,
            buyLeverage=str(LEVERAGE),
            sellLeverage=str(LEVERAGE)
        )
        print(f"✅ 레버리지 {LEVERAGE}배 설정 완료")
    except Exception as e:
        print(f"레버리지 설정 에러 (이미 설정됨): {e}")

# 현재 포지션 확인
def get_position():
    try:
        res = session.get_positions(
            category="linear",
            symbol=SYMBOL
        )
        pos = res["result"]["list"][0]
        size = float(pos["size"])
        side = pos["side"]  # Buy or Sell
        return size, side
    except:
        return 0, None

# 포지션 청산
def close_position(side, size):
    try:
        close_side = "Sell" if side == "Buy" else "Buy"
        res = session.place_order(
            category="linear",
            symbol=SYMBOL,
            side=close_side,
            orderType="Market",
            qty=str(size),
            reduceOnly=True
        )
        print(f"✅ 포지션 청산 완료: {res}")
        return True
    except Exception as e:
        print(f"❌ 청산 에러: {e}")
        return False

# 주문 실행
def place_order(side, qty, sl_price, tp1_price, tp2_price=None):
    try:
        # 메인 주문
        res = session.place_order(
            category="linear",
            symbol=SYMBOL,
            side=side,           # "Buy" or "Sell"
            orderType="Market",
            qty=str(qty),
            stopLoss=str(sl_price),
            slTriggerBy="MarkPrice", 
            positionIdx=0
        )
        print(f"✅ 주문 완료: {side} {qty} | SL: {sl_price}")

        # TP1 주문 (절반)
        half_qty = round(qty / 2, 3)
        tp_side = "Sell" if side == "Buy" else "Buy"
        session.place_order(
            category="linear",
            symbol=SYMBOL,
            side=tp_side,
            orderType="Limit",
            qty=str(half_qty),
            price=str(tp1_price),
            reduceOnly=True, 
            positionIdx=0
        )
        print(f"✅ TP1 주문: {tp1_price}")

        # TP2 주문 (나머지 절반)
        if tp2_price:
            session.place_order(
                category="linear",
                symbol=SYMBOL,
                side=tp_side,
                orderType="Limit",
                qty=str(half_qty),
                price=str(tp2_price),
                reduceOnly=True, 
                positionIdx=0
            )
            print(f"✅ TP2 주문: {tp2_price}")

        return True
    except Exception as e:
        print(f"❌ 주문 에러: {e}")
        return False

# 주문 수량 계산 (USDT 기준)
def calc_qty(usdt_amount):
    try:
        res = session.get_tickers(
            category="linear",
            symbol=SYMBOL
        )
        price = float(res["result"]["list"][0]["lastPrice"])
        qty = round(usdt_amount * LEVERAGE / price, 3)
        return qty, price
    except Exception as e:
        print(f"수량 계산 에러: {e}")
        return None, None

# 웹훅 메시지 파싱
# 메시지 형식:
# BTCUSDT(15m): 웅덩이 탈출@ 95000.0
#     SL: 94050.0(R: 2.00%/Lev: 5x)
#     TP1: 96900.0(P: 2.00%)
#     TP2: 98800.0(P: 4.00%)
def parse_signal(message):
    try:
        print(f"\n📩 수신 메시지:\n{message}")

        # 롱/숏 판단
        if "웅덩이 탈출" in message and "역 웅덩이" not in message:
            side = "Buy"
        elif "역 웅덩이 탈출" in message:
            side = "Sell"
        else:
            return None

        # 진입가
        entry_match = re.search(r'탈출@\s*([\d.]+)', message)
        entry_price = float(entry_match.group(1)) if entry_match else None

        # 손절가
        sl_match = re.search(r'SL:\s*([\d.]+)', message)
        sl_price = float(sl_match.group(1)) if sl_match else None

        # TP1
        tp1_match = re.search(r'TP1:\s*([\d.]+)', message)
        tp1_price = float(tp1_match.group(1)) if tp1_match else None

        # TP2
        tp2_match = re.search(r'TP2:\s*([\d.]+)', message)
        tp2_price = float(tp2_match.group(1)) if tp2_match else None

        return {
            "side": side,
            "entry": entry_price,
            "sl": sl_price,
            "tp1": tp1_price,
            "tp2": tp2_price
        }
    except Exception as e:
        print(f"파싱 에러: {e}")
        return None

# 웹훅 엔드포인트
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        # 메시지 수신
        data = request.get_data(as_text=True)
        print(f"\n{'='*40}")
        print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📩 Raw 데이터: {data}")

        # JSON이면 파싱
        try:
            json_data = json.loads(data)
            message = json_data.get("message", data)
        except:
            message = data

        # 신호 파싱
        signal = parse_signal(message)
        if not signal:
            print("⚠️ 유효한 신호 없음")
            return jsonify({"status": "ignored"}), 200

        print(f"✅ 파싱 완료: {signal}")

        # 기존 포지션 확인
        size, current_side = get_position()
        if size > 0:
            # 반대 신호면 청산 후 재진입
            if (signal["side"] == "Buy" and current_side == "Sell") or \
               (signal["side"] == "Sell" and current_side == "Buy"):
                print(f"🔄 반대 신호 → 기존 포지션 청산")
                close_position(current_side, size)
            else:
                print(f"⚠️ 이미 같은 방향 포지션 있음 → 스킵")
                return jsonify({"status": "skipped"}), 200

        # 주문 수량 계산 (100 USDT 기준)
        TRADE_AMOUNT = 100  # USDT
        qty, current_price = calc_qty(TRADE_AMOUNT)
        if not qty:
            return jsonify({"status": "error"}), 500

        print(f"💰 주문 수량: {qty} BTC (현재가: {current_price})")

        # 주문 실행
        success = place_order(
            side=signal["side"],
            qty=qty,
            sl_price=signal["sl"],
            tp1_price=signal["tp1"],
            tp2_price=signal["tp2"]
        )

        if success:
            return jsonify({"status": "success", "signal": signal}), 200
        else:
            return jsonify({"status": "error"}), 500

    except Exception as e:
        print(f"❌ 웹훅 에러: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# 헬스체크
@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "running", "time": str(datetime.now())}), 200

if __name__ == '__main__':
    print("🚀 웹훅 서버 시작!")
    set_leverage()
    app.run(host='0.0.0.0', port=8080, debug=False)