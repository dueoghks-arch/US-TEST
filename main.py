import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import datetime
import yfinance as yf
import pandas as pd
import time
import requests

# 위키피디아 크롤링 차단(403 Forbidden) 방지용 사용자 에이전트 설정
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# 1. S&P 500, 나스닥 100, S&P 400 티커 리스트 실시간 수집 및 병합
print("각 지수별 전 종목 리스트를 가져오는 중...")
ticker_set = set()

try:
    # S&P 500
    html_500 = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", headers=headers).text
    ticker_set.update(pd.read_html(html_500)[0]['Symbol'].tolist())
    
    # Nasdaq 100
    html_ndx = requests.get("https://en.wikipedia.org/wiki/Nasdaq-100", headers=headers).text
    nasdaq_tables = pd.read_html(html_ndx)
    for t in nasdaq_tables:
        col = [c for c in t.columns if c in ['Ticker', 'Symbol']]
        if col:
            ticker_set.update(t[col[0]].tolist())
            break
            
    # S&P MidCap 400
    html_400 = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_400_companies", headers=headers).text
    df_400 = pd.read_html(html_400)[0]
    col_400 = [c for c in df_400.columns if 'Ticker' in c or 'Symbol' in c][0]
    ticker_set.update(df_400[col_400].tolist())
except Exception as e:
    print(f"지수 리스트 수집 중 일부 오류 발생: {e}")

TICKERS = [str(t).replace('.', '-').strip() for t in ticker_set if pd.notna(t)]
print(f"➔ 중복 제거 후 총 {len(TICKERS)}개 종목 수집 완료.")

# 티커 수집 실패 시 방어 로직 (No objects to concatenate 에러 방지)
if len(TICKERS) == 0:
    print("수집된 티커가 없어 분석을 종료합니다.")
    exit()

# 2. 통째로 한번에 다운로드 (서버 차단 방지 및 속도 극대화)
print("모든 종목의 5년치 주봉 데이터 일괄 다운로드 중 (잠시만 기다려주세요)...")
all_data = yf.download(TICKERS, period="5y", interval="1wk", group_by='ticker', progress=False)
print("데이터 다운로드 완료. 조건 분석을 시작합니다.")

selected_stocks = []

# 3. 개별 종목 조건 검사 시행
for ticker in TICKERS:
    try:
        df = all_data[ticker].dropna(subset=['Close'])
        
        if len(df) < 100:
            continue
            
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA30'] = df['Close'].rolling(window=30).mean()
        df['MA100'] = df['Close'].rolling(window=100).mean()
        
        if len(df) >= 200:
            df['MA_LONG'] = df['Close'].rolling(window=200).mean()
            used_ma_name = "200주"
        else:
            df['MA_LONG'] = df['MA100']
            used_ma_name = "100주(대체)"
            
        latest = df.iloc[-1]
        current_price = latest['Close']
        ma5 = latest['MA5']
        ma30 = latest['MA30']
        ma_long = latest['MA_LONG']
        
        # [조건 1] 정배열 (5주 > 30주 > 장기이평선)
        is_aligned = (ma5 > ma30) and (ma30 > ma_long)
        
        # [조건 2] 각 이평선 간의 간격이 현재가의 10% 이하인지 확인 (초압축 상태)
        gap_5_30 = (ma5 - ma30) <= (current_price * 0.1)
        gap_30_long = (ma30 - ma_long) <= (current_price * 0.1)
        gap_total = (ma5 - ma_long) <= (current_price * 0.1)
        
        if is_aligned and gap_5_30 and gap_30_long and gap_total:
            selected_stocks.append({
                'ticker': ticker,
                'ma_type': used_ma_name
            })
            
    except KeyError:
        pass
    except Exception as e:
        pass 

# 4. 조건을 만족한 정예 종목에 대해서만 시총/종목명 전수 조사
print(f"조건 충족 종목 {len(selected_stocks)}개 발견. 상세 정보 수집 중...")
final_list = []

for item in selected_stocks:
    ticker = item['ticker']
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        company_name = info.get('longName', ticker)
        market_cap = info.get('marketCap', 0)
        
        if market_cap >= 1e12:
            market_cap_str = f"${market_cap / 1e12:.2f}T (조)"
        elif market_cap >= 1e9:
            market_cap_str = f"${market_cap / 1e9:.2f}B (십억)"
        elif market_cap > 0:
            market_cap_str = f"${market_cap:,.0f}"
        else:
            market_cap_str = "N/A"
            
        final_list.append({
            'ticker': ticker,
            'name': company_name,
            'market_cap': market_cap,
            'market_cap_str': market_cap_str,
            'ma_type': item['ma_type']
        })
        time.sleep(0.2)
    except Exception:
        final_list.append({
            'ticker': ticker,
            'name': ticker,
            'market_cap': 0,
            'market_cap_str': "N/A",
            'ma_type': item['ma_type']
        })

# 5. 이메일 발송 로직
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
EMAIL_RECEIVER = "dueoghks@gmail.com"

if final_list:
    final_list.sort(key=lambda x: x['market_cap'], reverse=True)
    
    table_rows = ""
    for item in final_list:
        table_rows += f"""
        <tr style="border-bottom: 1px solid #dddddd;">
            <td style="padding: 12px; text-align: right; background-color: #fafafa;">{item['market_cap_str']}</td>
            <td style="padding: 12px; text-align: center; font-weight: bold; color: #1a73e8;">{item['ticker']}</td>
            <td style="padding: 12px; text-align: left;">{item['name']} <span style="font-size: 11px; color: #ff9800; border: 1px solid #ff9800; padding: 1px 3px; border-radius: 3px; margin-left: 5px;">{item['ma_type']}</span></td>
        </tr>
        """
    
    body = f"""
    <div style="font-family: 'Malgun Gothic', sans-serif; max-width: 750px; margin: 0 auto;">
        <h3 style="color: #333333; border-bottom: 2px solid #4CAF50; padding-bottom: 8px;">
            📊 주요 지수 통합 조건 선별 주식 리스트 ({datetime.date.today()})
        </h3>
        <p style="font-size: 13px; color: #666666; margin-bottom: 15px;">
            <strong>조사 대상:</strong> S&P 500, 나스닥 100, S&P MidCap 400 전 종목 (차단 방지 로직 적용)<br>
            <strong>선별 조건:</strong> 5주 > 30주 > 장기이평선(200주 또는 100주) 정배열 & 각 이평선 간격이 현재가의 10% 이하로 초압축된 종목
        </p>
        
        <table style="border-collapse: collapse; width: 100%; box-shadow: 0 1px 3px rgba(0,0,0,0.1); font-size: 14px;">
            <thead>
                <tr style="background-color: #4CAF50; color: white;">
                    <th style="padding: 12px; text-align: center; width: 30%;">시가총액</th>
                    <th style="padding: 12px; text-align: center; width: 20%;">티커</th>
                    <th style="padding: 12px; text-align: center; width: 50%;">종목명 (장기기준)</th>
                </tr>
            </thead>
            <tbody>
                {table_rows}
            </tbody>
        </table>
        <p style="font-size: 11px; color: #999999; margin-top: 20px; text-align: right;">
            본 메일은 안정화 시스템에 의해 자동으로 발송되었습니다.
        </p>
    </div>
    """
else:
    body = "<h3>조건을 충족하는 종목이 해당 지수 내에 없습니다 (초압축 정배열 조건 미달).</h3>"

msg = MIMEMultipart()
msg['From'] = str(EMAIL_USER)
msg['To'] = EMAIL_RECEIVER
msg['Subject'] = f"[{datetime.date.today()}] 초압축 정배열 선별 주식 알림"
msg.attach(MIMEText(body, 'html'))

try:
    if not EMAIL_USER or not EMAIL_PASS:
        raise ValueError("환경변수 설정 오류: EMAIL_USER 또는 EMAIL_PASS가 설정되지 않았습니다.")
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(EMAIL_USER, EMAIL_PASS)
    server.sendmail(EMAIL_USER, EMAIL_RECEIVER, msg.as_string())
    server.quit()
    print("이메일 발송 완료!")
except Exception as e:
    print(f"이메일 발송 실패: {e}")
