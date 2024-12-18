import discord
from discord.ext import commands
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timedelta, timezone
from binance.client import Client
from binance.enums import *
import asyncio
import matplotlib
matplotlib.use('Agg')  # 서버 환경에서 GUI 없이 사용
import sqlite3
import mplfinance as mpf
import pandas as pd
import tempfile
import os
import traceback
import base64
import json
from openai import OpenAI

openai_api_key = ''
openaiclient = OpenAI(api_key=openai_api_key)

# Binance API 설정
api_key = ''
api_secret = ''
client = Client(api_key, api_secret)

# Discord 봇 설정
TOKEN = ''

# Intents 설정
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

webhook_url = ''
webhook_url_alert = ''

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

MAX_ORDER_AGE = 180 # 오래된 주문 기준 시간 (초)
def cancel_old_orders(client: Client, symbol: str):
    global waiting, MAX_ORDER_AGE
    """
    활성화된 오래된 주문 취소 함수
    """
    try:
        # 활성화된 주문 목록 조회
        open_orders = client.futures_get_open_orders(symbol=symbol)
        now_timestamp = datetime.now(timezone.utc)  # 타임존 인식 객체로 변경

        if open_orders == []:
            waiting = False
        else:
            for order in open_orders:
                order_id = order['orderId']
                order_time = datetime.fromtimestamp(order['time'] / 1000, timezone.utc)  # UTC 타임존 설정

                # 오래된 주문 확인
                if (now_timestamp - order_time).total_seconds() > MAX_ORDER_AGE:
                    # 오래된 주문 취소
                    client.futures_cancel_order(symbol=symbol, orderId=order_id)
                    print(f"오래된 주문 취소: 주문 ID {order_id}, 생성 시간: {order_time}")
                    message(f"오래된 주문 취소: 주문 ID {order_id}, 생성 시간: {order_time}")

    except Exception as e:
        print(f"오래된 주문 취소 중 오류 발생: {e}")
        message(f"오래된 주문 취소 중 오류 발생: {e}")

DB_PATH = "data.db"


def create_tendency_chart(candles):
    # 캔들 데이터 준비
    ohlc_data = {
        'Date': [datetime.fromtimestamp(candle[0] / 1000) for candle in candles],
        'Open': [float(candle[1]) for candle in candles],
        'High': [float(candle[2]) for candle in candles],
        'Low': [float(candle[3]) for candle in candles],
        'Close': [float(candle[4]) for candle in candles],
        'Volume': [float(candle[5]) for candle in candles],
    }

    df = pd.DataFrame(ohlc_data)
    df.set_index('Date', inplace=True)

    # 스타일 설정
    mpf_style = mpf.make_mpf_style(base_mpf_style='charles',
                                   y_on_right=False,  # y축을 왼쪽에 배치
                                   rc={'figure.figsize': (12, 8), 'axes.grid': True})

    # 차트 생성
    temp_dir = tempfile.gettempdir()
    file_path = os.path.join(temp_dir, "recent_5min_candles.png")

    mpf.plot(df, 
             type='candle', 
             style=mpf_style, 
             volume=True, 
             ylabel='',  # Price 레이블을 제거
             ylabel_lower='',  # Volume 레이블을 제거
             savefig=dict(fname=file_path, dpi=100, bbox_inches='tight'))

    return file_path



def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            roi REAL NOT NULL,
            realized_profit REAL NOT NULL,
            count_value REAL NOT NULL,
            i_price REAL NOT NULL,
            f_price REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()



# 데이터 저장 함수
def save_to_db(date, roi, realized_profit, count, i_price, f_price):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO data (date, roi, realized_profit, count_value, i_price, f_price) VALUES (?, ?, ?, ?, ?, ?)", (date, roi, realized_profit, count, i_price, f_price))
    conn.commit()
    conn.close()

def fetch_from_db(limit=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if limit:
        cursor.execute("SELECT date, roi, realized_profit, count_value, i_price, f_price FROM data ORDER BY id DESC LIMIT ?", (limit,))
    else:
        cursor.execute("SELECT date, roi, realized_profit, count_value, i_price, f_price FROM data ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows





def get_5min_candles(symbol, interval='5m', lookback='500 minutes ago UTC'):
    klines = client.get_historical_klines(symbol, interval, lookback)
    return klines[-100:]  # 마지막 100개의 5분봉 데이터를 반환

def get_1hour_candles(symbol, interval='1h', lookback='100 hours ago UTC'):
    klines = client.get_historical_klines(symbol, interval, lookback)
    return klines[-100:]  


# 지갑 잔액 체크 함수 정의
def get_futures_asset_balance(symbol='USDT'):
    try:
        balance_info = client.futures_account_balance()
        for balance in balance_info:
            if balance['asset'] == symbol:
                return float(balance['availableBalance'])
        return 0.0
    except Exception as e:
        print(f"An error occurred: {e}")
        return 0.0

# 코인 잔액 체크 함수 정의
def get_asset_balance(symbol):
    try:
        positions = client.futures_position_information()
        for position in positions:
            if position['symbol'] == symbol:
                return float(position['isolatedMargin'])
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return 0.0

# 레버리지 설정 함수 정의
def set_leverage(symbol, leverage):
    try:
        response = client.futures_change_leverage(symbol=symbol, leverage=leverage)
        print(f"Leverage set: {response}")
    except Exception as e:
        print(f"An error occurred while setting leverage: {e}")

# 지정가 롱 포지션 매수주문 함수 정의
def place_limit_long_order(symbol, price, quantity, leverage):
    set_leverage(symbol, leverage)
    price = round_price_to_tick_size(price,symbol)
    try:
        order = client.futures_create_order(
            symbol=symbol,
            side='BUY',
            type='LIMIT',
            timeInForce='GTC',  # Good Till Cancelled
            price=price,
            quantity=quantity
        )
        print(f"Order placed: {order}")
        return order
    except Exception as e:
        print(f"An error occurred: {e}")

def calculate_order_quantity(percentage):
    usdt_balance = get_futures_asset_balance()
    buy_quantity = usdt_balance * percentage / 100
    return round(buy_quantity, 3)

# 주문 실행 함수 : 종목, 지정가격, 퍼센트(자산), 레버리지
def execute_limit_long_order(symbol, price, percentage, leverage): # 현재 잔액에서 퍼센트만큼 매수하는 함수
    quantity = calculate_order_quantity(percentage)
    price = round_price_to_tick_size(price,symbol)
    if quantity > 0:
        size = round(quantity / price * leverage, 3)
        o = place_limit_long_order(symbol, price, size, leverage)
        return o
    else:
        print("Insufficient balance or invalid quantity.")

# close 함수 정의
def close(symbol):
    try:
        # 현재 오픈된 포지션 정보 가져오기
        positions = client.futures_position_information(symbol=symbol)
        for position in positions:
            if float(position['positionAmt']) != 0:
                # 포지션 청산
                side = 'SELL' if float(position['positionAmt']) > 0 else 'BUY'
                quantity = abs(float(position['positionAmt']))

                order = client.futures_create_order(
                    symbol=symbol,
                    side=side,
                    type='MARKET',
                    quantity=quantity,
                    reduceOnly=True
                )
                print(f"Position for {symbol} closed: {order}")
                return order
        print(f"No open position for {symbol}.")
    except Exception as e:
        print(f"An error occurred: {e}")

# 포지션 정보 가져오기 함수 정의
def get_futures_position_info(symbol):
    try:
        positions = client.futures_position_information()
        for position in positions:
            if position['symbol'] == symbol:
                return position
        return {
            'unRealizedProfit': 0,
            'positionAmt': 0,
            'entryPrice': 0,
            'liquidationPrice': 0
        }
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

# 디코 웹훅 메세지 보내기 함수 정의
def message(message):
    data = {
        "content": message,
        "username": "Webhook Bot"  # Optional: 설정하지 않으면 기본 웹훅 이름이 사용됩니다.
    }

    result = requests.post(webhook_url, json=data)
    try:
        result.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print(f"Error: {err}")
    else:
        print(f"Payload delivered successfully, code {result.status_code}.")

def message_alert(message):
    data = {
        "content": message,
        "username": "Webhook Bot"  # Optional: 설정하지 않으면 기본 웹훅 이름이 사용됩니다.
    }

    result = requests.post(webhook_url_alert, json=data)
    try:
        result.raise_for_status()
    except requests.exceptions.HTTPError as err:
        print(f"Error: {err}")
    else:
        print(f"Payload delivered successfully, code {result.status_code}.")

# 주문 상태 확인 함수 정의
def check_order_status(symbol, order_id):
    try:
        order = client.futures_get_order(symbol=symbol, orderId=order_id)
        return order
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

# 틱 사이즈 확인 함수 정의
def get_tick_size(symbol):
    exchange_info = client.futures_exchange_info()
    for s in exchange_info['symbols']:
        if s['symbol'] == symbol:
            for f in s['filters']:
                if f['filterType'] == 'PRICE_FILTER':
                    return float(f['tickSize'])
    return None

# 틱 사이즈로 반올림 함수 정의
def round_price_to_tick_size(price, tick_size):
    return round(price / tick_size) * tick_size

def get_latest_order(symbol):
    try:
        # 모든 주문 정보 가져오기
        orders = client.get_all_orders(symbol=symbol, limit=10)

        # 주문이 없는 경우 처리
        if not orders:
            return None

        # 가장 최근 주문 정보 반환
        latest_order = orders[-1]
        return latest_order
    except Exception as e:
        print(f"An error occurred: {e}")
        return None
    

def openai_response(symbol,msg_system,msg_user,base64_image): # symbol, system 메세지, user메세지 입력

    base64_image = encode_image(file_path)
    candles = get_5min_candles(symbol, lookback='1000 minutes ago UTC') 
    file_path = create_tendency_chart(candles)

    response = openaiclient.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
            "role": "system",
            "content": [
                {
                "type": "text",
                "text": f"{msg_system}"
                }
            ]
            },
            {
            "role": "user",
            "content": [
                {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}"
                }
                },
                {
                "type": "text",
                "text": f"{msg_user}"
                }
            ]
            }
        ],
        temperature=0.5,
        max_tokens=500,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0,
        response_format={
            "type": "json_object"
        }
        )
    
    return response

def openai_response_warn(symbol,msg_system,msg_user,base64_image1,base64_image2): # symbol, system 메세지, user메세지 입력

    base64_image = encode_image(file_path)
    candles = get_5min_candles(symbol, lookback='1000 minutes ago UTC') 
    file_path = create_tendency_chart(candles)

    response = openaiclient.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
            "role": "system",
            "content": [
                {
                "type": "text",
                "text": f"{msg_system}"
                }
            ]
            },
            {
            "role": "user",
            "content": [
                {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image1}"
                }
                },
                {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image2}"
                }
                },
                {
                "type": "text",
                "text": f"{msg_user}"
                }
            ]
            }
        ],
        temperature=0.5,
        max_tokens=500,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0,
        response_format={
            "type": "json_object"
        }
        )
    
    return response

def plummet(symbol, N):
    try:
        # 과거 거래 내역 가져오기
        trades = client.get_my_trades(symbol=symbol)

        # 매수(BUY)만 필터링
        buy_orders = [trade for trade in trades if trade['isBuyer']]

        # 최근 두 매수 기록 시간 차 계산
        if len(buy_orders) >= 2:
            latest_time = datetime.datetime.fromtimestamp(buy_orders[-1]['time'] / 1000)
            previous_time = datetime.datetime.fromtimestamp(buy_orders[-2]['time'] / 1000)
            time_diff = (latest_time - previous_time).total_seconds() / 60  # 시간 차를 분 단위로 변환
            if time_diff >= N:
                return True

        # 최근 5분봉 데이터 가져오기
        klines = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_5MINUTE, limit=10)
        for kline in klines:
            open_price = float(kline[1])
            close_price = float(kline[4])
            change_percent = ((close_price - open_price) / open_price) * 100
            if change_percent <= -1.0:  # 1% 이상 하락한 봉 확인
                return True

        return False

    except Exception as e:
        print(f"Error in plument function: {e}")
        return False