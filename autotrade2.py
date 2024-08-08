import discord
from discord.ext import commands
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timedelta
from binance.client import Client
from binance.enums import *
import asyncio

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

webhook_url = 'https://discord.com/api/webhooks/1262846700305911819/vQcV7aHcN7JMqRLIjyt7dOVK4BX23QU8XWJ5zK5njD9fo1Ja_Wpl2OUVsaZNLJvD8Xx5'

# 초기설정
leverage = 20
symbol = "BTCUSDT"
sell_price = 0  # 마지막 판매 가격
n = 4  # 100/2^n

# 전략 실행 상태
is_running = False

# 최고 수익률 기록
max_pnl = 0

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
            inv_amount = entryprice * positionAmt / leverage  # 투입금액
            if inv_amount != 0:
                pnl = unrealizedProfit / inv_amount * 100  # PNL
            else:
                pnl = 0
            liquidation_price = position_info['liquidationPrice']

            tick_size = get_tick_size(symbol)

            today_date = datetime.today()
            date_diff = today_date - sell_date
            minute_diff = date_diff.total_seconds() / 60

            if buying is False and order is None:
                if sell_price != 0:
                    if (current_price - sell_price) / sell_price < -0.01:
                        percentage = 100 / (2 ** n)
                        order = execute_limit_long_order(symbol, current_price, percentage, leverage)
                        iquantity = calculate_order_quantity(percentage)
                        message(f"매수주문완료\n현재가격 : {current_price}\n매수금액 : {iquantity}")
                    elif 1440 * 3 + 10 >= minute_diff >= 1440 * 3:
                        sell_price = current_price
                        sell_date = datetime.today()
            if buying is True and order is None:
                # 추가매수 -50퍼일때
                if pnl <= -50:
                    if count >= n - 1:
                        leverage = 5
                    order_price = round_price_to_tick_size(current_price, tick_size)
                    inv_size = round(inv_amount / current_price * leverage, 3)
                    order = place_limit_long_order(symbol, order_price, inv_size, leverage)
                    count += 1
                    message(f"추가매수주문완료\n현재가격 : {current_price}\n추가매수횟수 : {count}\n매수금액 : {inv_amount}")

                # 최고 수익률 갱신 및 10% 하락 시 매도
                if pnl > max_pnl:
                    max_pnl = pnl
                elif max_pnl >= 25 and pnl <= max_pnl - 10:
                    order = close(symbol)
                    message(f"매도완료\n최고 PNL: {max_pnl}%\n현재 PNL: {pnl}%\nRealizedProfit : {unrealizedProfit}")
                    sell_price = current_price
                    percentage = 100 / 2 ** n
                    count = 0
                    leverage = 20  # 초기 레버리지로 리셋
                    max_pnl = 0  # 최고 수익률 초기화
                    sell_date = datetime.today()

                # 총액 매도 30퍼 이득
                if pnl >= 50 and order is None:
                    order = close(symbol)
                    message(f"매도완료\nPNL : {pnl}\nRealizedProfit : {unrealizedProfit}")
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
                '''
                message(msg)
                await asyncio.sleep(60)

            await asyncio.sleep(10)
        except Exception as e:
            message(f"오류가 발생했습니다: {e}")

# 봇 명령어 정의
@bot.command(name='status')
async def get_status(ctx):
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

@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')

# 봇 실행
bot.run(TOKEN)
