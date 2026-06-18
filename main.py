import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import datetime
import yfinance as yf
import pandas as pd
import time

# 1. S&P 500, 나스닥 100, S&P 400 티커 리스트 실시간 수집 및 병합
print("각 지수별 전 종목 리스트를 가져오는 중...")
ticker_set = set()

try:
    ticker_set.update(pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]['Symbol'].tolist())
    
    nasdaq_tables = pd.read_html("https://en.wikipedia.org/wiki/Nasdaq-100")
    for t in nasdaq_tables:
        col = [c for c in t.columns if c in ['Ticker', 'Symbol']]
        if col:
            ticker_set.update(t[col[0]].tolist())
            break
            
    df_400 = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_400_companies")[0]
    col_400 = [c for c in df_400.columns if 'Ticker' in c or 'Symbol' in c][0]
    ticker_set.update(df_400[col_400].tolist())
except Exception as e:
    print(f"지수 리스트 수집 중 일부 오류 발생: {e}")

TICKERS = [str(t).replace('.', '-').strip() for t in ticker_set if pd.notna(t)]
print(f"➔ 중복 제거 후 총 {len(TICKERS)}개 종목 수집 완료.")

# 2. 통째로 한번에 다운로드 (서버 차단 방지 및 속도 극대화)
print("모든 종목의 5년치 주봉 데이터 일괄 다운로드 중 (잠시만 기다려주세요)...")
all_data = yf.download(TICKERS, period="5y", interval="1wk", group_by='ticker', progress=False)
print("데이터 다운로드 완료. 조건 분석을 시작합니다.")

selected_stocks = []

# 3. 개별 종목 조건 검사 시행
for ticker in TICKERS:
    try:
        # 안전한 데이터 추출 방식 적용 (KeyError 발생 시 자연스럽게 패스)
        df = all_data[ticker].dropna(subset=['Close'])
        
        # 최소 100주 이상의 데이터도 없으면 상장한 지 너무 안 된 것이므로 패스
        if len(df) < 100:
            continue
            
        # 기본 이평선 계산
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA30'] = df['Close'].rolling(window=30).mean()
        df['MA100'] = df['Close'].rolling(window=100).mean()
        
        # 200주 데이터 존재 여부에 따른 동적 분기
        if len(df) >= 200:
            df['MA_LONG'] = df['Close'].rolling(window=200).mean()
            used_ma_name = "200주"
        else:
            df['MA_LONG'] = df['MA100']  # 200주가 없으면 100주로 대체
            used_ma_name = "100주(대체)"
            
        latest = df.iloc[-1]
        current_price = latest['Close']
        ma5 = latest['MA5']
        ma30 = latest['MA30']
        ma_long = latest['MA_LONG']
        
        # 조건 1: 정배열 (5주 > 30주 > 장기이평선)
        is_aligned = (ma5 > ma30) and (ma30 > ma_long)
        
        # 조건 2: 5주와 장기이평선 간격이 현재가의 50% 이하
        is_gap_valid = (ma5 - ma_long) <= (current_price * 0.5)
        
        if is_aligned and is_gap_valid:
            selected_stocks.append({
                'ticker': ticker,
                'ma_type': used_ma_name
            })
            
    except KeyError:
        # yf.download 결과에 해당 티커 데이터가 없는 경우
        pass
    except Exception as e:
        pass # 기타 연산 중 에러 발생 시 부드럽게 패스

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
        # info API 연속 호출로 인한 일시적 차단 방지
        time.sleep(0.2)
    except Exception:
        # 만약 info에서 에러가 나면 기본 정보로 채워서 표에 포함시킴
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
    # 시가총액 내림차순 정렬
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
            <strong>선별 조건:</strong> 5주 > 30주 > 장기이평선(200주 또는 100주) 정배열 & 5주와 장기이평선 간격이 현재가의 50% 이하
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
    body = "<h3>조건을 충족하는 종목이 해당 지수 내에 없습니다.</h3>"

msg = MIMEMultipart()
msg['From'] = str(EMAIL_USER)
msg['To'] = EMAIL_RECEIVER
msg['Subject'] = f"[{datetime.date.today()}] 주요 지수 통합 대량 선별 알림"
msg.attach(MIMEText(body, 'html'))

try:
    if not EMAIL_USER or not EMAIL_PASS:
        raise ValueError("환경변수 설정 오류")
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(EMAIL_USER, EMAIL_PASS)
    server.sendmail(EMAIL_USER, EMAIL_RECEIVER, msg.as_string())
    server.quit()
    print("이메일 발송 완료!")
except Exception as e:
    print(f"이메일 발송 실패: {e}")
