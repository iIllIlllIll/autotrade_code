import discord
from discord.ext import commands
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timedelta
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

# Binance API 설정
api_key = ''
api_secret = ''
client = Client(api_key, api_secret)

# Discord 봇 설정
TOKEN = 'YOUR_DISCORD_BOT_TOKEN'

# Intents 설정
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

webhook_url = ''

# 초기설정
initial_leverage = 20
leverage = 20
symbol = "BTCUSDT"
sell_price = 0  # 마지막 판매 가격
n = 4  # 100/2^n

date_diff_setting = 3

mpp = 50
addp = 25
mpdown = 10
int_mpdown = 10
bp = 1

# 전략 실행 상태
is_running = False
infprofit = False

# 최고 수익률 기록
max_pnl = 0



DB_PATH = "data.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            roi REAL NOT NULL,
            realized_profit REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()

# 데이터 저장 함수
def save_to_db(date, roi, realized_profit):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO data (date, roi, realized_profit) VALUES (?, ?, ?)", (date, roi, realized_profit))
    conn.commit()
    conn.close()

# 데이터 불러오기 함수
def fetch_from_db(limit=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if limit:
        cursor.execute("SELECT content, timestamp FROM data ORDER BY id DESC LIMIT ?", (limit,))
    else:
        cursor.execute("SELECT content, timestamp FROM data ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows





def get_5min_candles(symbol, interval='5m', lookback='500 minutes ago UTC'):
    klines = client.get_historical_klines(symbol, interval, lookback)
    return klines[-100:]  # 마지막 100개의 5분봉 데이터를 반환


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
    tick_size = get_tick_size(symbol)
    buy_quantity = usdt_balance * percentage / 100
    return round_price_to_tick_size(buy_quantity, tick_size)

# 주문 실행 함수 : 종목, 지정가격, 퍼센트(자산), 레버리지
def execute_limit_long_order(symbol, price, percentage, leverage):
    quantity = calculate_order_quantity(percentage)
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
        return None
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
            print(f"No orders found for {symbol}.")
            return None

        # 가장 최근 주문 정보 반환
        latest_order = orders[-1]
        return latest_order
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

def get_1min_candles(symbol, interval='1m', lookback='1 hour ago UTC'):
    klines = client.get_historical_klines(symbol, interval, lookback)
    return klines

def calculate_decline_rate(symbol):
    candles = get_1min_candles(symbol)
    
    decline_count = 0
    total_count = len(candles)
    total_decline = 0
    max_decline_percent = 0
    total_decline_percent = 0

    for candle in candles:
        open_price = float(candle[1])
        close_price = float(candle[4])
        
        if close_price < open_price:
            decline_count += 1
            decline_amount = open_price - close_price
            decline_percent = (decline_amount / open_price) * 100
            total_decline += decline_amount
            total_decline_percent += decline_percent
            
            if decline_percent > max_decline_percent:
                max_decline_percent = decline_percent

    decline_rate = (decline_count / total_count) * 100 if total_count > 0 else 0
    average_decline = total_decline / decline_count if decline_count > 0 else 0
    average_decline_percent = total_decline_percent / decline_count if decline_count > 0 else 0
    
    return {
        'decline_rate': decline_rate,
        'total_decline': total_decline,
        'total_decline_percent': total_decline_percent,
        'average_decline': average_decline,
        'max_decline_percent': max_decline_percent,
        'average_decline_percent': average_decline_percent,
        'decline_count': decline_count,
        'total_count': total_count
    }



# 전략 실행 함수
async def start_trading_strategy():
    global is_running, sell_price, sell_date, buying, count, waiting, order, leverage, max_pnl
    
    sell_date = datetime.today()
    sell_price = 0

    buying = False  # 매수상태일때 True
    count = 0
    waiting = False  # 주문 대기상태일 때 True
    order = None
    max_pnl = 0  # 최고 수익률 초기화

    print("Trading strategy started")
    message("자동매매를 시작합니다")
    set_leverage(symbol,initial_leverage)

    while is_running:
        try:
            # 매수상태인지 체크
            position_info = get_futures_position_info(symbol)
            order = get_latest_order(symbol)
            if float(position_info['positionAmt']) != 0:
                buying = True
                if order is not None:
                    order_id = order['orderId']
                    order_status = check_order_status(symbol, order_id)
                    if order_status and order_status['status'] == 'FILLED':
                        message(f"{order_id}\n주문이 체결되었습니다.")
                        waiting = False
                        order = None
                    else:
                        waiting = True
            else:
                buying = False

            current_price_info = client.get_symbol_ticker(symbol=f"{symbol}")
            current_price = float(current_price_info['price'])
            position_info = get_futures_position_info(symbol)
            unrealizedProfit = float(position_info['unRealizedProfit'])
            positionAmt = float(position_info['positionAmt'])  # 포지션 수량
            entryprice = float(position_info['entryPrice'])  # 진입가격
            # inv_amount = entryprice * positionAmt / leverage  # 투입금액
            inv_amount = abs(positionAmt) * entryprice / leverage

            if inv_amount != 0:
                pnl = unrealizedProfit / inv_amount * 100  # PNL
            else:
                pnl = 0
            liquidation_price = position_info['liquidationPrice']

            tick_size = get_tick_size(symbol)

            today_date = datetime.today()
            date_diff = today_date - sell_date
            minute_diff = date_diff.total_seconds() / 60

            if infprofit == True:
                if pnl <= 40:
                    mpdown = 15
                elif pnl >= 40:
                    mpdown = max_pnl/4
            else:
                mpdown = int_mpdown

            if buying is False and order is None:
                if sell_price != 0:
                    if (current_price - sell_price) / sell_price < -bp/100:
                        percentage = 100 / (2 ** n)
                        order = execute_limit_long_order(symbol, current_price, percentage, leverage)
                        iquantity = calculate_order_quantity(percentage)
                        message(f"매수주문완료\n현재가격 : {current_price}\n매수금액 : {iquantity}")
                    elif 1440 * date_diff_setting + 10 >= minute_diff >= 1440 * date_diff_setting:
                        sell_price = current_price
                        sell_date = datetime.today()
            if buying is True and order is None:
                # 추가매수 -50퍼일때
                if pnl <= -addp:
                    if count >= n - 1:
                        leverage = 1
                        set_leverage(symbol,leverage)
                    order_price = round_price_to_tick_size(current_price, tick_size)
                    inv_size = round(inv_amount / current_price * leverage, 3)
                    order = place_limit_long_order(symbol, order_price, inv_size, leverage)
                    count += 1
                    message(f"추가매수주문완료\n현재가격 : {current_price}\n추가매수횟수 : {count}\n매수금액 : {inv_amount}\n레버리지 : {leverage}")

                # 최고 수익률 갱신 및 10% 하락 시 매도
                if pnl > max_pnl:
                    max_pnl = pnl
                elif max_pnl >= 25 and pnl <= max_pnl - mpdown:
                    order = close(symbol)
                    message(f"매도완료\n최고 PNL: {max_pnl}%\n현재 PNL: {pnl}%\nRealizedProfit : {unrealizedProfit}")
                    save_to_db(datetime.today(),pnl,unrealizedProfit)
                    sell_price = current_price
                    percentage = 100 / 2 ** n
                    count = 0
                    leverage = 20  # 초기 레버리지로 리셋
                    max_pnl = 0  # 최고 수익률 초기화
                    sell_date = datetime.today()
                    
                    

                # 총액 매도 30퍼 이득
                if infprofit == False and pnl >= mpp and order is None:
                    order = close(symbol)
                    message(f"매도완료\nPNL : {pnl}\nRealizedProfit : {unrealizedProfit}")
                    save_to_db(datetime.today(),pnl,unrealizedProfit)
                    sell_price = current_price
                    percentage = 100 / 2 ** n
                    count = 0
                    leverage = 20  # 초기 레버리지로 리셋
                    max_pnl = 0  # 최고 수익률 초기화
                    sell_date = datetime.today()

            now = datetime.now()
            if now.minute == 0:  # 정시(00분)인지 확인
                if buying is False:
                    status = '매수 대기중'
                else:
                    status = '매수중'
                blnc = get_futures_asset_balance()
                buy_price = sell_price * 0.99
                msg = f'''
                ╔═══━━━───  STATUS  ───━━━═══╗
                현재 상태 : {status}
                현재 가격 : {current_price}
                현재 pnl : {pnl}
                잔액 : {blnc}
                매수금액 : {inv_amount}
                현재금액 : {inv_amount + unrealizedProfit}
                추가매수횟수 : {count}
                마지막판매금액 : {sell_price}
                매수예정금액 : {buy_price}
                판매후지난시간(분) : {minute_diff}
                주문 상태 : {order}
                레버리지 : {leverage}
                Infinte Profit Mode : {infprofit}
                '''
                message(msg)
                await asyncio.sleep(60)

            await asyncio.sleep(10)
        except Exception as e:
            message(f"오류가 발생했습니다: {e}")

# 봇 명령어 정의
@bot.command(name='status')
async def get_status(ctx):
    global is_running, sell_price, sell_date, buying, count, waiting, order, leverage, max_pnl, n, infprofit
    current_price_info = client.get_symbol_ticker(symbol=f"{symbol}")
    current_price = float(current_price_info['price'])
    position_info = get_futures_position_info(symbol)
    unrealizedProfit = float(position_info['unRealizedProfit'])
    positionAmt = float(position_info['positionAmt'])  # 포지션 수량
    entryprice = float(position_info['entryPrice'])  # 진입가격
    inv_amount = entryprice * positionAmt / leverage  # 투입금액
    if inv_amount != 0:
        pnl = unrealizedProfit / inv_amount * 100  # PNL
    else:
        pnl = 0
    liquidation_price = position_info['liquidationPrice']

    blnc = get_futures_asset_balance()
    buy_price = sell_price * 0.99

    embed = discord.Embed(title="Trading Bot Status", color=discord.Color.blue())
    embed.add_field(name="현재 상태", value='매수중' if positionAmt != 0 else '매수 대기중', inline=False)
    embed.add_field(name="현재 가격", value=f"{current_price}", inline=False)
    embed.add_field(name="현재 PNL", value=f"{pnl}%", inline=False)
    embed.add_field(name="잔액", value=f"{blnc} USDT", inline=False)
    embed.add_field(name="매수 금액", value=f"{inv_amount}", inline=False)
    embed.add_field(name="현재 금액", value=f"{inv_amount + unrealizedProfit}", inline=False)
    embed.add_field(name="추가 매수 횟수", value=f"{count}", inline=False)
    embed.add_field(name="마지막 판매 금액", value=f"{sell_price}", inline=False)
    embed.add_field(name="매수 예정 금액", value=f"{buy_price}", inline=False)
    embed.add_field(name="주문 상태", value=f"{order}", inline=False)
    embed.add_field(name="판매 가격", value=f"{sell_price}", inline=False)
    embed.add_field(name="레버리지", value=f"{leverage}", inline=False)
    embed.add_field(name="n값", value=f"{n}", inline=False)
    embed.add_field(name="Infinte Profit Mode", value=f"{infprofit}", inline=False)

    await ctx.send(embed=embed)

@bot.command(name='decline')
async def decline(ctx):
    decline_data = calculate_decline_rate(symbol)
    embed = discord.Embed(title="Decline Rate in the Last Hour", color=discord.Color.red())
    embed.add_field(name="하락 비율", value=f"{decline_data['decline_rate']}%", inline=False)
    embed.add_field(name="총 하락", value=f"{decline_data['total_decline']}", inline=False)
    embed.add_field(name="총 하락 퍼센트", value=f"{decline_data['total_decline_percent']}%", inline=False)
    embed.add_field(name="평균 하락", value=f"{decline_data['average_decline']}", inline=False)
    embed.add_field(name="최대 하락 퍼센트", value=f"{decline_data['max_decline_percent']}%", inline=False)
    embed.add_field(name="평균 하락 퍼센트", value=f"{decline_data['average_decline_percent']}%", inline=False)
    embed.add_field(name="하락 개수", value=f"{decline_data['decline_count']}", inline=False)
    embed.add_field(name="전체 개수", value=f"{decline_data['total_count']}", inline=False)
    await ctx.send(embed=embed)

@bot.command(name='tendency')
async def tendency(ctx):
    candles = get_5min_candles(symbol, lookback='1000 minutes ago UTC')  # 필요한 경우 조정 가능
    file_path = create_tendency_chart(candles)
    
    # 이미지 파일을 디스코드에 전송
    await ctx.send(file=discord.File(file_path))
    
    # 사용 후 이미지 파일 삭제
    os.remove(file_path)

@bot.command(name='start')
async def start(ctx):
    global is_running
    if not is_running:
        is_running = True
        await ctx.send("자동매매를 시작합니다")
        bot.loop.create_task(start_trading_strategy())
    else:
        await ctx.send("자동매매가 이미 실행 중입니다")

@bot.command(name='stop')
async def stop(ctx):
    global is_running
    if is_running:
        is_running = False
        await ctx.send("자동매매가 중단되었습니다")
    else:
        await ctx.send("자동매매가 실행 중이 아닙니다")

@bot.command(name='close')
async def close_positions(ctx):
    await ctx.send("정말 하시겠습니까? [Y/n]")

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ['y', 'n']

    try:
        msg = await bot.wait_for('message', check=check, timeout=30.0)
        if msg.content.lower() == 'y':
            global is_running
            is_running = False
            close(symbol)
            await ctx.send(f"{symbol} 포지션이 모두 청산되었습니다.")
        else:
            await ctx.send("포지션 청산이 취소되었습니다.")
    except asyncio.TimeoutError:
        await ctx.send("시간 초과로 포지션 청산이 취소되었습니다.")

@bot.command(name='set_sellprice')
async def set_sellprice(ctx, price: float):
    global sell_price
    sell_price = price
    await ctx.send(f"판매 가격이 {sell_price}로 설정되었습니다.")

@bot.command(name='set_n')
async def set_n(ctx, value: int):
    global n
    n = value
    await ctx.send(f"n 변수가 {n}로 설정되었습니다.")

@bot.command(name='set_count')
async def set_count(ctx, value: int):
    global count
    count = value
    await ctx.send(f"count 변수가 {value}로 설정되었습니다.")

@bot.command(name='set_mpp')
async def set_mpp(ctx, value: int):
    global mpp
    mpp = value
    await ctx.send(f"mpp 변수가 {value}로 설정되었습니다.")

@bot.command(name='set_addp')
async def set_addp(ctx, value: int):
    global addp
    addp = value
    await ctx.send(f"addp 변수가 {value}로 설정되었습니다.")

@bot.command(name='set_mpdown')
async def set_mpdown(ctx, value: int):
    global mpdown
    mpdown = value
    await ctx.send(f"mpdown 변수가 {value}로 설정되었습니다.")

@bot.command(name='set_bp')
async def set_bp(ctx, value: int):
    global bp
    bp = value
    await ctx.send(f"bp 변수가 {value}로 설정되었습니다.")

@bot.command(name='set_dds')
async def set_dds(ctx, value: int):
    global bp
    date_diff_setting = value
    await ctx.send(f"date_diff_setting 변수가 {value}로 설정되었습니다.")

@bot.command(name='infprofit')
async def infprofit(ctx, value: int):
    global infprofit
    if infprofit == False:
        infprofit = True
    else:
        infprofit = False
    await ctx.send(f"Infinte Profite 모드가 {infprofit}로 설정되었습니다.")

@bot.command(name='setting')
async def setting(ctx):
    global mpp, addp, mpdown, count, n, sell_price, leverage, bp, date_diff_setting

    buy_price = sell_price*(1-(bp/100))
    
    embed = discord.Embed(title="Trading Bot Status", color=discord.Color.blue())
    embed.add_field(name="자동매도 퍼센트", value=f"{mpp}%", inline=False)
    embed.add_field(name="추가매수 퍼센트", value=f"{addp}%", inline=False)
    embed.add_field(name="자동익절 하락 퍼센트", value=f"{mpdown}%", inline=False)
    embed.add_field(name="추가매수 횟수", value=f"{count}", inline=False)
    embed.add_field(name="초기 투자비용 비율", value=f"{n}", inline=False)
    embed.add_field(name="마지막 판매 금액", value=f"{sell_price}", inline=False)
    embed.add_field(name="매수예정 금액", value=f"{buy_price}", inline=False)
    embed.add_field(name="매수예정 하락퍼센트", value=f"{bp}", inline=False)
    embed.add_field(name="레버리지", value=f"{leverage}", inline=False)
    embed.add_field(name="초기화 주기", value=f"{date_diff_setting}일", inline=False)
    

    await ctx.send(embed=embed)


@bot.command(name="database")
async def database(ctx, action: str, *args):
    if action == "show":
        try:
            limit = int(args[0]) if args else None
            data = fetch_from_db(limit)
            if data:
                response = "\n".join([f"{row[0]} | PNL: {row[1]:.2f}% | Realized Profit: {row[2]:.2f}" for row in data])
            else:
                response = "데이터가 없습니다."
        except ValueError:
            response = "숫자를 입력해주세요."
        await ctx.send(response)

    elif action == "all":
        data = fetch_from_db()
        if data:
            response = "\n".join([f"{row[0]} | PNL: {row[1]:.2f}% | Realized Profit: {row[2]:.2f}" for row in data])
        else:
            response = "데이터가 없습니다."
        await ctx.send(response)

    elif action == "clear":
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS data")
        conn.commit()
        conn.close()
        init_db()
        await ctx.send("데이터베이스가 초기화되었습니다.")

    else:
        await ctx.send("알 수 없는 명령어입니다. 사용 가능한 명령어: show, all, clear")

@bot.command(name="save")
async def save(ctx, date: str, roi: float, realized_profit: float):
    try:
        save_to_db(date, roi, realized_profit)
        await ctx.send(f"데이터가 저장되었습니다. 날짜: {date}, 수익률: {roi:.2f}%, Realized Profit: {realized_profit:.2f}")
    except Exception as e:
        await ctx.send(f"오류가 발생했습니다: {e}")

@bot.command(name='helpme')
async def helpme(ctx):

    await ctx.send('''
                   
!set_sellprice : 마지막 판매 가격 조정
!set_n : 투자비용 비율 조정 (전체시드/2^n)
!set_count : 추가매수 횟수 변수 조정
!set_mpp : 자동매도 퍼센트 지정
!set_addp : 추가매수 퍼센트 지정
!set_mpdown : 자동익절 하락 퍼센트 지정
!set_bp : 매수예정 하락퍼센트 지정
!set_ddp : sellprice 초기화 주기 설정
!close : 포지션 청산
!stop : 자동매매 중단
!start : 자동매매 시작
!tendency : 최근 차트 전송
!decline : 하락 비율 분석
!status : 현재 상태
!setting : 설정값 목록
!database show <number> : 거래내역 보기
!database all : 모든 거래내역 보기
!database clear : 거래내역 초기화
!save <date> <PNL> <realized profit> : 거래내역 추가
!infprofit : Infinte Profite Mode 토글
!helpme : 지금 보는 내용

''')
    

@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')

# 봇 실행
init_db()
bot.run(TOKEN)
