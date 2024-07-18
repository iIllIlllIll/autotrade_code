from binance.client import Client
from binance.enums import *
import requests
import time
from datetime import datetime

# 바이낸스 API 키와 시크릿 키 설정
api_key = ''
api_secret = ''

client = Client(api_key, api_secret)

webhook_url = ''


# 초기설정
leverage = 20
symbol = "BTCUSDT"
sell_price = 0 # 마지막 판매 가격
n = 4 # 100/2^n

# 지갑 잔액 체크
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
# 코인 잔액 체크
def get_asset_balance(symbol):
    try:
        positions = client.futures_position_information()
        for position in positions:
            if position['symbol'] == symbol:
                return position['isolatedMargin']
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return 0.0

# 레버리지 설정
def set_leverage(symbol, leverage):
    try:
        response = client.futures_change_leverage(symbol=symbol, leverage=leverage)
        print(f"Leverage set: {response}")
    except Exception as e:
        print(f"An error occurred while setting leverage: {e}")

# 지정가 롱 포지션 매수주문
def place_limit_long_order(symbol, price, quantity, leverage):
    set_leverage(symbol,leverage)
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
    return round_price_to_tick_size(buy_quantity,tick_size)

# 주문 실행 함수 : 종목, 지정가격, 퍼센트(자산), 레버리지
def execute_limit_long_order(symbol, price, percentage, leverage):
    quantity = calculate_order_quantity(percentage)
    if quantity > 0:
        size = round(quantity/price*leverage,3)
        o = place_limit_long_order(symbol, price, size, leverage)
        return o
    else:
        print("Insufficient balance or invalid quantity.")

# 매도 주문
def place_limit_sell_order(symbol, price, quantity):
    try:
        order = client.order_limit_sell(
            symbol=symbol,
            price=str(price),
            quantity=str(quantity)
        )
        print(f"Order placed: {order}")
        return order
    except Exception as e:
        print(f"An error occurred: {e}")

def calculate_sell_quantity(symbol, percentage):
    balance = get_asset_balance(symbol)
    sell_quantity = balance * percentage / 100
    return round_price_to_tick_size(sell_quantity,tick_size)

def execute_limit_sell_order(symbol, price, percentage):
    sell_quantity = calculate_sell_quantity(symbol, percentage)
    if sell_quantity > 0:
        sell_size = round(sell_quantity/current_price*leverage,3)
        o = place_limit_sell_order(symbol, price, sell_size)
        return o 
    else:
        print("Insufficient balance or invalid quantity.")





# 포지션 정보 가져오기 : pnl, margin ratio, liquidation price 등등
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



# 디코 웹훅 메세지 보내기
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

# 주문 상태 확인
def check_order_status(symbol, order_id):
    try:
        order = client.futures_get_order(symbol=symbol, orderId=order_id)
        return order
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

# 틱 사이즈 확인
def get_tick_size(symbol):
    exchange_info = client.futures_exchange_info()
    for s in exchange_info['symbols']:
        if s['symbol'] == symbol:
            for f in s['filters']:
                if f['filterType'] == 'PRICE_FILTER':
                    return float(f['tickSize'])
    return None

# 틱 사이즈로 반올림
def round_price_to_tick_size(price, tick_size):
    return round(price / tick_size) * tick_size



# 실시간 자료얻기

buying = False # 매수상태일때 True
count = 0
waiting = False # 주문 대기상태일 때 True
order = None

print('''                                s                     s                                ..                  
                               :8                    :8                              dF                    
               x.    .        .88           u.      .88       .u    .               '88bu.                 
      u      .@88k  z88u     :888ooo  ...ue888b    :888ooo  .d88B :@8c        u     '*88888bu        .u    
   us888u.  ~"8888 ^8888   -*8888888  888R Y888r -*8888888 ="8888f8888r    us888u.    ^"*8888N    ud8888.  
.@88 "8888"   8888  888R     8888     888R I888>   8888      4888>'88"  .@88 "8888"  beWE "888L :888'8888. 
9888  9888    8888  888R     8888     888R I888>   8888      4888> '    9888  9888   888E  888E d888 '88%" 
9888  9888    8888  888R     8888     888R I888>   8888      4888>      9888  9888   888E  888E 8888.+"    
9888  9888    8888 ,888B .  .8888Lu= u8888cJ888   .8888Lu=  .d888L .+   9888  9888   888E  888F 8888L      
9888  9888   "8888Y 8888"   ^%888*    "*888*P"    ^%888*    ^"8888*"    9888  9888  .888N..888  '8888c. .+ 
"888*""888"   `Y"   'YP       'Y"       'Y"         'Y"        "Y"      "888*""888"  `"888*""    "88888%   
 ^Y"   ^Y'                                                               ^Y"   ^Y'      ""         "YP'    
                                                                                                           
    ver 1.1
    2024-07-19             
    made by 윈터띠                                                                                   
      
                                                                                                            ''')
message('''자동매매를 시작합니다''')

while True:
    # 매수상태인지 체크
    position_info = get_futures_position_info(symbol)
    if position_info and float(position_info['positionAmt']) != 0:
        buying = True
        if order != None:
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
    positionAmt = float(position_info['positionAmt']) # 포지션 수량
    entryprice = float(position_info['entryPrice']) # 진입가격
    inv_amount = entryprice*positionAmt/leverage # 투입금액
    if inv_amount != 0:
        pnl = unrealizedProfit/inv_amount*100 # PNL
    else:
        pnl = 0
    liquidation_price = position_info['liquidationPrice']

    tick_size = get_tick_size(symbol)

    if buying == False:
        if sell_price != 0:
            if (current_price - sell_price)/sell_price < -0.01:
                percentage = 100/(2**n)
                order = execute_limit_long_order(symbol,current_price,percentage)
                iquantity = calculate_order_quantity(percentage)
                message(f"매수주문완료\n현재가격 : {current_price}\n매수금액 : {iquantity}")
    
    if buying == True:
        # 추가매수 -50퍼일때
        if pnl <= -50:
            order_price = round_price_to_tick_size(current_price,tick_size)
            inv_size = round(inv_amount/current_price*leverage,3)
            order = place_limit_long_order(symbol,order_price,inv_size,leverage)
            count += 1
            message(f"추가매수주문완료\n현재가격 : {current_price}\n추가매수횟수 : {count}\n매수금액 : {inv_amount}")
            

        # 총액 매도 30퍼 이득
        if pnl >= 40:
            order = execute_limit_sell_order(symbol,current_price,100)
            message(f"매도완료\nPNL : {pnl}\nRealizedProfit : {unrealizedProfit}")
            sell_price = current_price
            percentage = 100/2**n
            count = 0

    now = datetime.now()
    if now.minute == 0 or True:  # 정시(00분)인지 확인
        if buying == False:
            status = '매수 대기중'
        else:
            status = '매수중'
        blnc = get_futures_asset_balance()
        msg = f'''
        ╔═══━━━───  STATUS  ───━━━═══╗
         현재 상태 : {status}
         현재 가격 : {current_price}
         현재 pnl : {pnl}
         잔액 : {blnc}
         매수금액 : {inv_amount}
         현재금액 : {inv_amount+unrealizedProfit}
         추가매수횟수 : {count}
                '''
        message(msg)
        time.sleep(60)

    time.sleep(10)



