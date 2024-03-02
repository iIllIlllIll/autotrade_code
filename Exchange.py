import time
import pyupbit
import datetime
import pandas as pd
import requests as rq


access = ""
secret = ""
ticker = 'KRW-BTC'
balance = 1
discord_webhook_url =''
ticker_name = 'BTC'
stop_loss = 0.995 # 손절 퍼센트
take_profit = 1.01 # 익절 퍼센트
tp = 1.01
sl = 0.995
tp2 = 1.025

def get_rsi(df, period=14): # df에 'RSI'추가해서 df반환
    asd = df["close"]
    delta = asd.diff()

    ups, downs = delta.copy(), delta.copy()
    ups[ups < 0] = 0
    downs[downs > 0] = 0

    AU = ups.ewm(com = period-1, min_periods = period).mean()
    AD = downs.abs().ewm(com = period-1, min_periods = period).mean()
    RS = AU/AD
    RSI = (100 - (100/(1+RS)))
    df['RSI'] = RSI

    return df

def stocastic(data,k_window=5,d_window=5,window=5):
    min_val = data.rolling(window=window, center=False).min()
    max_val = data.rolling(window=window, center=False).max()
    stoch = ((data-min_val)/(max_val-min_val))*100
    K = stoch.rolling(window=k_window, center=False).mean()
    D = K.rolling(window=d_window, center=False).mean()
    return K, D

def get_current_ohlcv(ticker):
    global df
    df = pyupbit.get_ohlcv(ticker=ticker,interval='minute30',count=30)
    get_rsi(df)
    df['K'], df['D'] = stocastic(df['RSI'])
    
    

class hk:
    def __init__(self,i):
        self.i = len(df)
        self.open = df['open'].iloc[i]
        self.high = df['high'].iloc[i]
        self.low = df['low'].iloc[i]
        self.close = df['close'].iloc[i]
    def c(self):
        close = (self.open + self.close + self.low + self.high)/4
        return close
    def o(self):
        open = (hk(self.i-1).c() + hk(self.i-1).c()) / 2
        return open
    def h(self):
        high = max(self.high,self.o(),self.c())
        return high
    def l(self):
        low = min(self.low,self.o(),self.c())
        return low

def size(i):
    size = abs(hk(i).c() - hk(i).o())
    return size 


def is_hammer(i):
    if hk(i).h() == hk(i).o():
        return True
    else:
        return False

def is_rhammer(i):
    if hk(i).l() == hk(i).o():
        return True
    else:
        return False
    

check = False
count = 0

def buy(i):
    global check, count
    if check == False:
        if df['K'].iloc[i-2] < df['D'].iloc[i-2] and df['K'].iloc[i-1] > df['D'].iloc[i-1]:
            if df['K'].iloc[i-1] - df['K'].iloc[i-1] > 0:
                check = True
                count = 0
    if check == True:
        count += 1
    if count == 5 and check == True:
        check = False
        count = 0
    if check == True:
        if is_rhammer(i) == True and hk(i-1).c()-hk(i-1).o() > 0:
            check = False
            count = 0
            return True

profit_sell = 0
loss_sell = 0   



def sell(i):
    global price, buy_price, take_profit, stop_loss, profit_sell, loss_sell, tp, sl, tp2
    if price/buy_price > take_profit: # 익절
        if take_profit == tp and is_rhammer(i) == True and is_rhammer(i-1) == True:
            take_profit = tp2
            stop_loss = 1.001
            return False
        profit_sell += 1
        stop_loss = sl
        take_profit = tp
        return True
    elif price/buy_price < stop_loss: # 손절
        loss_sell += 1
        stop_loss = sl
        return True
    else:
        return False


def get_balance(ticker):
    balances = upbit.get_balances()
    for b in balances:
        if b['currency'] == ticker:
            if b['balance'] is not None:
                return float(b['balance'])
            else:
                return 0
    return 0

def message(message):
    msg = {'content':f'{message}'}
    rq.post(discord_webhook_url,data=msg)
    print(message)



# 로그인
upbit = pyupbit.Upbit(access, secret)
message(f'autotrade start\nticker : {ticker}\ntake_profit : {take_profit}\nstop_loss : {stop_loss}')

# 자동매매 시작
if get_balance(f"{ticker_name}") > 0:
    Buying = True
else:
    Buying = False

while True:
    try:
        now = datetime.datetime.now()
        message(now)
        get_current_ohlcv(ticker)
        i = len(df) - 1
        price = df['open'].iloc[-1]

        if Buying == False and buy(i) == True:
            '''구매'''
            krw = get_balance("KRW")
            if krw > 5000: #업비트 최소주문금액
                upbit.buy_market_order(f"ticker", krw*0.9995)
                Buying = True
                buy_price = price
                message("매수완료, 매수가격 : {0}원".format(buy_price))
            else:
                message("잔액이 부족합니다")
        elif Buying == True and sell(i) == True:
            '''판매'''
            btc = get_balance(f"{ticker_name}")
            upbit.sell_market_order(f"{ticker}", btc*0.9995)
            Buying = False
            sell_price = price
            ror = (((sell_price/buy_price))*balance*0.9995 - balance*0.0005)*100
            balance = 1 # 초기화
            message("매도완료, 매도가격 : {0}, 거래 수익률 : {1}%".format(sell_price,ror))
        else:
            message("-- pass --\ncheck : {0}\ncount : {1}\nprice : {2}".format(check,count,price))
        time.sleep(60)
    except Exception as e:
        message("error:{0}".format(e))
        time.sleep(60)