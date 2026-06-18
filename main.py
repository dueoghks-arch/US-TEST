import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import datetime
import yfinance as yf
import pandas as pd

# 1. 대상 티커 리스트 가져오기
TICKERS = ['SPY', 'QQQ', 'DIA', 'IJH', 'AAPL', 'MSFT', 'GOOGL', 'AMZN']

selected_stocks = []
print("주식 데이터 분석 시작...")

for ticker in TICKERS:
    try:
        # 200주 이평선을 계산하려면 최소 4년 이상의 데이터가 필요하므로 5년(5y)치 다운로드
        stock = yf.Ticker(ticker)
        df = stock.history(period="5y", interval="1wk")
        
        # 200주 데이터가 안 되면 패스 (상장된 지 4년이 안 된 종목 등)
        if len(df) < 200:
            continue
            
        # 5주, 30주, 200주 이동평균선 계산
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA30'] = df['Close'].rolling(window=30).mean()
        df['MA200'] = df['Close'].rolling(window=200).mean()
        
        # 가장 최근 주(이번 주)의 데이터 추출
        latest = df.iloc[-1]
        
        current_price = latest['Close']
        ma5 = latest['MA5']
        ma30 = latest['MA30']
        ma200 = latest['MA200']
        
        # 조건 1: 5주, 30주, 200주 이평선 정배열 (MA5 > MA30 > MA200)
        is_aligned = (ma5 > ma30) and (ma30 > ma200)
        
        # 조건 2: 5주와 200주 이평선의 간격이 현재가의 50% 이하
        # (정배열 상태이므로 ma5가 ma200보다 무조건 크기 때문에 절댓값 처리는 생략 가능)
        is_gap_valid = (ma5 - ma200) <= (current_price * 0.5)
        
        if is_aligned and is_gap_valid:
            selected_stocks.append(ticker)
            
    except Exception as e:
        print(f"{ticker} 분석 중 오류 발생: {e}")

# 2. 이메일 발송 로직
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
EMAIL_RECEIVER = "dueoghks@gmail.com"

# 환경변수 누락 확인
if not EMAIL_USER or not EMAIL_PASS:
    print("경고: 환경변수(EMAIL_USER, EMAIL_PASS)가 설정되지 않았습니다.")

if selected_stocks:
    body = f"<h3>정배열 및 이격도 조건 충족 종목 리스트</h3><p>{', '.join(selected_stocks)}</p>"
else:
    body = "<h3>조건을 충족하는 종목이 없습니다.</h3>"

msg = MIMEMultipart()
msg['From'] = str(EMAIL_USER)
msg['To'] = EMAIL_RECEIVER
msg['Subject'] = f"[{datetime.date.today()}] 조건 선별 주식 리스트 알림"
msg.attach(MIMEText(body, 'html'))

try:
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(EMAIL_USER, EMAIL_PASS)
    server.sendmail(EMAIL_USER, EMAIL_RECEIVER, msg.as_string())
    server.quit()
    print("이메일 발송 완료!")
except Exception as e:
    print(f"이메일 발송 실패: {e}")
