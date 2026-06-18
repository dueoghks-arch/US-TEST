import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import datetime
import yfinance as yf
import pandas as pd

# 1. 대상 티커 리스트 가져오기 (예시: S&P500의 일부 및 주요 지수 ETF)
# 실제 전 종목을 하려면 위키피디아 등에서 티커 리스트를 크롤링하는 로직이 추가됩니다.
TICKERS = ['SPY', 'QQQ', 'DIA', 'IJH', 'AAPL', 'MSFT', 'GOOGL', 'AMZN'] # 예시 티커들

selected_stocks = []

print("주식 데이터 분석 시작...")

for ticker in TICKERS:
    try:
        # 주봉(Weekly) 데이터 최근 1년치 다운로드
        stock = yf.Ticker(ticker)
        df = stock.history(period="1y", interval="1wk")
        
        if len(df) < 35:
            continue
            
        # 30주 이동평균선 계산
        df['MA30'] = df['Close'].rolling(window=30).mean()
        
        # 최근 4주 데이터 추출
        recent_4weeks = df.tail(4)
        
        # 최근 4주 내에 종가가 30주 이평선을 상향 돌파(Cross-over)한 적이 있는지 확인
        is_breakout = False
        for i in range(1, len(recent_4weeks)):
            # 전주에는 종가가 이평선 아래였는데, 이번주에는 이평선 위로 올라간 경우
            prev_idx = df.index.get_loc(recent_4weeks.index[i-1])
            curr_idx = df.index.get_loc(recent_4weeks.index[i])
            
            if df['Close'].iloc[prev_idx] <= df['MA30'].iloc[prev_idx] and df['Close'].iloc[curr_idx] > df['MA30'].iloc[curr_idx]:
                is_breakout = True
                break
                
        if is_breakout:
            selected_stocks.append(ticker)
            
    except Exception as e:
        print(f"{ticker} 분석 중 오류 발생: {e}")

# 2. 이메일 발송 로직
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD") # 구글 앱 비밀번호
EMAIL_RECEIVER = "dueoghks@gmail.com"

if selected_stocks:
    body = f"<h3>최근 4주 내 30주봉 돌파 종목 리스트</h3><p>{', '.join(selected_stocks)}</p>"
else:
    body = "<h3>최근 4주 내 30주봉을 돌파한 종목이 없습니다.</h3>"

msg = MIMEMultipart()
msg['From'] = EMAIL_SENDER
msg['To'] = EMAIL_RECEIVER
msg['Subject'] = f"[{datetime.date.today()}] 조건 선별 주식 리프트 알림"
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
