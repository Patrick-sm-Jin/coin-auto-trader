# 🤖 코인 자동매매 봇 (BTC/USDT)

> 트레이딩뷰 웹훅 신호를 받아 Bybit에 자동으로 주문을 넣는 파이썬 자동매매 시스템

---

## 📊 백테스트 결과 (3년, 1시간봉)

| 항목 | 결과 |
|------|------|
| 총 수익률 | **+82.54%** |
| MDD | **-4.87%** |
| 승률 | 49.0% |
| 손익비 | 1:2.25 |
| 총 거래수 | 247번 |
| 연평균 수익률 | ~22% |

---

## 🏗️ 시스템 구조
```
트레이딩뷰 Alert (웹훅 신호)
        ↓
Flask 웹훅 서버 (신호 수신 + 파싱)
        ↓
Bybit 자동 주문 (진입 + SL + TP1 + TP2)
```

---

## 📈 전략 설명

### MACD + EMA50 전략
- **진입 조건**: MACD 골든크로스 + EMA50 방향 + 거래량 1.5배 + ATR 필터
- **청산 구조**: 1차 익절(0.3%) → 본전 스탑 → 2차 익절(3.5%) → 트레일링(4.5%)
- **리스크 관리**: 손절 0.8%, 일일 최대 손절 3회, 레버리지 10배

---

## ⚙️ 파일 구조
```
coin-auto-trader/
├── webhook_server.py     # 웹훅 서버 + Bybit 자동주문 (핵심)
├── strategy_macd.py      # MACD 전략 백테스트
├── parameter_test.py     # 파라미터 최적화 (그리드 서치)
├── Daytrading.py         # 데이터 분석
├── download_data.py      # Binance 데이터 수집
├── config.py             # API 키 (git 제외)
└── .gitignore
```

---

## 🚀 설치 및 실행

### 1. 패키지 설치
```bash
pip3 install flask pybit pandas numpy matplotlib
```

### 2. API 키 설정
```python
# config.py 생성
API_KEY = "your_bybit_api_key"
API_SECRET = "your_bybit_api_secret"
```

### 3. 서버 실행
```bash
python3 webhook_server.py
```

### 4. ngrok으로 외부 접근
```bash
ngrok http --domain=dodie-dichromic-sheryll.ngrok-free.dev 8080
```

### 5. 트레이딩뷰 Alert 설정
- Webhook URL: `https://dodie-dichromic-sheryll.ngrok-free.dev/webhook`
- Message: `{{alert_message}}`

---

## 🛡️ 리스크 관리

- 일일 최대 손절 횟수 제한
- 반대 신호 시 기존 포지션 자동 청산
- SL/TP 자동 설정
- API 키 분리 관리 (config.py)

---

## 🛠️ 기술 스택

![Python](https://img.shields.io/badge/Python-3.12-blue)
![Flask](https://img.shields.io/badge/Flask-3.0-green)
![Bybit](https://img.shields.io/badge/Bybit-API-orange)
![TradingView](https://img.shields.io/badge/TradingView-Webhook-purple)

---

## ⚠️ 면책 조항

이 프로젝트는 학습 및 포트폴리오 목적으로 제작되었습니다.
실제 투자에 사용 시 발생하는 손실에 대한 책임은 본인에게 있습니다.
