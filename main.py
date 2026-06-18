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
        # 주봉(Weekly) 데이터 최근 1년치 다운로드
        stock = yf.Ticker(ticker)
        df = stock.history(period="1y", interval="1wk")
        
        # 30주(약 7~8개월) 데이터가 안 되면 패스
        if len(df) < 35:
            continue
            
        # 30주 이동평균선 계산
        df['MA30'] = df['Close'].rolling(window=30).mean()
        
        # 전주 종가 및 이평선 데이터 시프트(이동)
        df['Prev_Close'] = df['Close'].shift(1)
        df['Prev_MA30'] = df['MA30'].shift(1)
        
        # 상향 돌파 조건: (전주 종가 <= 전주 MA30) AND (이번주 종가 > 이번주 MA30)
        df['Breakout'] = (df['Prev_Close'] <= df['Prev_MA30']) & (df['Close'] > df['MA30'])
        
        # 최근 4주 데이터 내에 돌파가 발생한 적이 있는지 확인 (벡터화 연산)
        recent_4weeks = df.tail(4)
        if recent_4weeks['Breakout'].any():
            selected_stocks.append(ticker)
            
    except Exception as e:
        print(f"{ticker} 분석 중 오류 발생: {e}")

# 2. 이메일 발송 로직
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD") # 구글 앱 비밀번호
EMAIL_RECEIVER = "dueoghks@gmail.com"

# 환경변수 누락 확인
if not EMAIL_SENDER or not EMAIL_PASSWORD:
    print("경고: 환경변수(EMAIL_SENDER, EMAIL_PASSWORD)가 설정되지 않았습니다.")

if selected_stocks:
    body = f"<h3>최근 4주 내 30주봉 돌파 종목 리스트</h3><p>{', '.join(selected_stocks)}</p>"
else:
    body = "<h3>최근 4주 내 30주봉을 돌파한 종목이 없습니다.</h3>"

msg = MIMEMultipart()
msg['From'] = str(EMAIL_SENDER)
msg['To'] = EMAIL_RECEIVER
msg['Subject'] = f"[{datetime.date.today()}] 조건 선별 주식 리스트 알림"
msg.attach(MIMEText(body, 'html'))

try:
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(EMAIL_SENDER, EMAIL_PASSWORD)
    server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
    server.quit()
    print("이메일 발송 완료!")
except Exception as e:
    print(f"이메일 발송 실패: {e}")
