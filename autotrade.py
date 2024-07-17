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
def get_usdt_balance():
    balance = client.futures_account_balance()
    for asset in balance:
        if asset['asset'] == 'USDT':
            return float(asset['balance'])
    return 0.0
# 코인 잔액 체크
def get_asset_balance(symbol):
    try:
        balance = client.get_asset_balance(asset=symbol)
        return float(balance['free'])
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
    set_leverage(leverage)
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

def calculate_order_quantity(symbol, price, percentage):
    usdt_balance = get_usdt_balance()
    order_amount_usdt = usdt_balance * percentage / 100
    info = client.futures_exchange_info()
    for s in info['symbols']:
        if s['symbol'] == symbol:
            min_qty = float(s['filters'][1]['minQty'])
            quantity = order_amount_usdt / float(price)
            return max(quantity, min_qty)
    return 0.0

# 주문 실행 함수 : 종목, 지정가격, 퍼센트(자산), 레버리지
def execute_limit_long_order(symbol, price, percentage, leverage):
    quantity = calculate_order_quantity(symbol, price, percentage)
    if quantity > 0:
        o = place_limit_long_order(symbol, price, quantity, leverage)
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
    return sell_quantity

def execute_limit_sell_order(symbol, price, percentage):
    sell_quantity = calculate_sell_quantity(symbol, percentage)
    if sell_quantity > 0:
        o = place_limit_sell_order(symbol, price, sell_quantity)
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


    current_price = client.get_symbol_ticker(symbol=f"{symbol}") # 실시간 가격
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


    if buying == False:
        if sell_price != 0:
            if (current_price - sell_price)/sell_price < -0.01:
                percentage = 100/(2**n)
                order = execute_limit_long_order(symbol,current_price,percentage)
                message(f"매수주문완료\n현재가격 : {current_price}")
    
    if buying == True:
        # 추가매수 -50퍼일때
        if pnl <= -50:
            order = place_limit_long_order(symbol,current_price,inv_amount,leverage)
            count += 1
            message(f"추가매수주문완료\n현재가격 : {current_price}\n추가매수횟수 : {count}")
            

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
        blnc = get_usdt_balance()
        msg = f'''[ 정기보고 ]\n현재 상태 : {status}\n현재 가격 : {current_price}\n현재 pnl : {pnl}\n잔액 : {blnc}\n추가매수횟수 : {count}'''
        message(msg)
        time.sleep(60)

    time.sleep(10)



