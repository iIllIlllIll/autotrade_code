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
import inspect
import sys
from functions import *

# 초기설정
initial_leverage = 20
leverage = 20
symbol = "BTCUSDT"
sell_price = 0  # 마지막 판매 가격
n = 5  # 100/2^n

date_diff_setting = 3

count = 0
mpp = 100
addp = 40
mpdown = 10
int_mpdown = 10
bp = 1

# 전략 실행 상태
is_running = False
infprofit = False
AI_mode = False
waiting = False
Aicommand = False  
wait_up = False
stable_mode = True
warn_stratage = False
buymode = False
sellmode = False

circulation_mode = False
normal_mode = True

# 최고 수익률 기록
max_pnl = 0
latest_degree = 0
# countforwarn
countforwarn = 3
WARNINGFORLOSS = False

loss_amount = 0 # 임시손실

with open("msg_system.txt", "r",encoding="utf-8") as file:
    msg_system_orig = file.read()

with open("msg_system_warn.txt","r",encoding="utf-8") as file:
    msg_system_warn_orig = file.read()

with open("msg_system_circular.txt","r",encoding="utf-8") as file:
    msg_system_circular_orig = file.read()


# 봇 명령어 정의
@bot.command(name='status')
async def get_status(ctx):
    global is_running, sell_price, sell_date, buying, count, order, leverage, max_pnl, n, infprofit, AI_mode
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

    blnc = get_futures_asset_balance()
    buy_price = sell_price * 0.99

    if infprofit == True:
        infprofitmode = '🟢ON'
    else:
        infprofitmode = '🔴OFF'

    if AI_mode == True:
        aimode_msg = '🟢ON'
    else:
        aimode_msg = '🔴OFF'

    if WARNINGFORLOSS is True:
        warn = "⚠️WARNING"
    else:
        warn = "🔆normal"

    embed = discord.Embed(title="Trading Bot Status", color=discord.Color.blue())
    embed.add_field(name="현재 상태", value='🟢매수중' if positionAmt != 0 else '🔴매수 대기중', inline=True)
    embed.add_field(name="현재 가격", value=f"{current_price}", inline=True)
    embed.add_field(name="현재 PNL", value=f"{pnl}%", inline=True)
    embed.add_field(name="잔액", value=f"{blnc} USDT", inline=True)
    embed.add_field(name="매수 금액", value=f"{inv_amount}", inline=True)
    embed.add_field(name="현재 금액", value=f"{inv_amount + unrealizedProfit}", inline=True)
    embed.add_field(name="💸현재 수익", value=f"{unrealizedProfit}", inline=True)
    embed.add_field(name="추가 매수 횟수", value=f"{count}", inline=True)
    embed.add_field(name="마지막 판매 금액", value=f"{sell_price}", inline=True)
    embed.add_field(name="매수 예정 금액", value=f"{buy_price}", inline=True)
    embed.add_field(name="청산 금액", value=f"{liquidation_price}", inline=True)    
    embed.add_field(name="주문 상태", value=f"{order}", inline=True)
    embed.add_field(name="판매 가격", value=f"{sell_price}", inline=True)
    embed.add_field(name="레버리지", value=f"{leverage}", inline=True)
    embed.add_field(name="n값", value=f"{n}", inline=True)
    embed.add_field(name="Infinte Profit Mode", value=f"{infprofitmode}", inline=True)
    embed.add_field(name="🤖AI Trading Mode", value=f"{aimode_msg}", inline=True)
    embed.add_field(name="WARNING", value=f"{warn}",inline=True)

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
    global date_diff_setting
    date_diff_setting = value
    await ctx.send(f"date_diff_setting 변수가 {value}로 설정되었습니다.")

@bot.command(name='infprofit')
async def infprofit(ctx):
    global infprofit
    if infprofit == False:
        infprofit = True
    else:
        infprofit = False
    await ctx.send(f"Infinte Profite 모드가 {infprofit}로 설정되었습니다.")

@bot.command(name='aimode')
async def aimode(ctx):
    global AI_mode
    if AI_mode == False:
        AI_mode = True
    else:
        AI_mode = False
    await ctx.send(f"AI Trading 모드가 {AI_mode}로 설정되었습니다.")

@bot.command(name='set_leverage')
async def set_lev(ctx, value: int):
    global leverage, symbol
    leverage = value
    set_leverage(symbol,leverage)
    await ctx.send(f"레버리지가 {value}로 설정되었습니다.")

@bot.command(name='set_countforwarn')
async def countforwarn2(ctx, value: int):
    global countforwarn
    countforwarn = value
    await ctx.send(f"countforwarn 변수가 {value}로 설정되었습니다")

@bot.command(name='stable')
async def stable(ctx):
    global stable_mode
    if stable_mode == False:
        stable_mode = True
    else:
        stable_mode = False
    await ctx.send(f"stable_mode가 {stable_mode}로 설정되었습니다")

@bot.command(name='warn_stratage')
async def warn_stratage(ctx):
    global warn_stratage
    if warn_stratage == False:
        warn_stratage = True
    else:
        warn_stratage = False
    await ctx.send(f"warn_stratage 모드가 {warn_stratage}로 설정되었습니다")

@bot.command(name='normal')
async def normal(ctx):
    global normal_mode, circulation_mode
    if normal_mode == False:
        normal_mode = True
        circulation_mode = False
    else:
        normal_mode = False
        circulation_mode = True
    await ctx.send(f"normal_mode 모드가 {normal_mode}로 설정되었습니다")

@bot.command(name='circulation')
async def circulation(ctx):
    global circulation_mode, normal_mode
    if circulation_mode == False:
        circulation_mode = True
        normal_mode = False
    else:
        circulation_mode = False
        normal_mode = True
    await ctx.send(f"circulation_mode 모드가 {circulation_mode}로 설정되었습니다")

@bot.command(name='setting')
async def setting(ctx):
    global mpp, addp, mpdown, count, n, sell_price, leverage, bp, date_diff_setting, WARNINGFORLOSS, ready_price, stable_mode
    global buy_ready_price, sell_ready_price
    global circulation_mode, normal_mode

    buy_price = sell_price*(1-(bp/100))
    
    embed = discord.Embed(title="Trading Bot Status", color=discord.Color.blue())
    embed.add_field(name="자동매도 퍼센트", value=f"{mpp}%", inline=True)
    embed.add_field(name="추가매수 퍼센트", value=f"{addp}%", inline=True)
    embed.add_field(name="자동익절 하락 퍼센트", value=f"{mpdown}%", inline=True)
    embed.add_field(name="추가매수 횟수", value=f"{count}", inline=True)
    embed.add_field(name="초기 투자비용 비율", value=f"{n}", inline=True)
    embed.add_field(name="마지막 판매 금액", value=f"{sell_price}", inline=True)
    embed.add_field(name="매수예정 금액", value=f"{buy_price}", inline=True)
    embed.add_field(name="매수예정 하락퍼센트", value=f"{bp}", inline=True)
    embed.add_field(name="레버리지", value=f"{leverage}", inline=True)
    embed.add_field(name="초기화 주기", value=f"{date_diff_setting}일", inline=True)
    embed.add_field(name="WARNINGFORLOSS", value=f"{WARNINGFORLOSS}", inline=True)
    embed.add_field(name="ready_price", value=f"{ready_price}", inline=True)
    embed.add_field(name="buy_ready_price", value=f"{buy_ready_price}", inline=True)
    embed.add_field(name="sell_ready_price", value=f"{sell_ready_price}", inline=True)
    embed.add_field(name="analysis2_state", value=f"{analysis2_state}", inline=True)
    embed.add_field(name="stable_mode", value=f"{stable_mode}", inline=True)
    embed.add_field(name="circulation_mode", value=f"{circulation_mode}", inline=True)
    embed.add_field(name="normal_mode", value=f"{normal_mode}", inline=True)

    await ctx.send(embed=embed)

@bot.command(name='buy') # 현재가격으로 구매 : !buy 구매수량(달러)
async def buycommand(ctx,value: float):
    global is_running, sell_price, sell_date, buying, count, order, leverage, max_pnl, n, infprofit, AI_mode
    
    current_price_info = client.get_symbol_ticker(symbol=f"{symbol}")
    current_price = float(current_price_info['price'])
    inv_amount = value  # 투입할 금액

    order_price = round(current_price*1.001, 1)
    inv_size = round(inv_amount / current_price * leverage, 3)
    order = place_limit_long_order(symbol, order_price, inv_size, leverage)
    message(f"[명령어]매수주문완료\n현재가격 : {current_price}\n추가매수횟수 : {count}\n매수금액 : {inv_amount}\n레버리지 : {leverage}")
    await ctx.send(f"주문완료")


@bot.command(name='aianalogy')
async def aianalogy(ctx):
    global Aicommand
    Aicommand = True
    await ctx.send(f"Ai분석 실시.")

@bot.command(name='set_warningforloss')
async def warningforloss(ctx):
    global WARNINGFORLOSS
    if WARNINGFORLOSS is True:
        WARNINGFORLOSS = False
    else:
        WARNINGFORLOSS = True
    await ctx.send(f"WARNINGFORLOSS가 {WARNINGFORLOSS}로 설정되었습니다.")



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
async def save(ctx, date: str, roi: float, realized_profit: float, count:float, i_price:float, f_price:float):
    try:
        save_to_db(date, roi, realized_profit, count, i_price, f_price)
        await ctx.send(f"데이터가 저장되었습니다. 날짜: {date}, 수익률: {roi:.2f}%, Realized Profit: {realized_profit:.2f}, 추가매수 횟수 : {count},매수금액 : {i_price},최종금액 : {f_price}")
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
!set_leverage : 레버리지 세팅
!set_countforwarn : countforwarn 변수 설정
!set_warningforloss : WARNINGFORLOSS 토글
!close : 포지션 청산
!stop : 자동매매 중단
!start : 자동매매 시작
!tendency : 최근 차트 전송
!status : 현재 상태
!setting : 설정값 목록
!database show <number> : 거래내역 보기
!database all : 모든 거래내역 보기
!database clear : 거래내역 초기화
!save <date> <PNL> <realized profit> : 거래내역 추가
!infprofit : Infinte Profite Mode 토글
!aimode : AI Trading Mode 토글
!stable : Stable Mode 토글
!warn_stratage : 경고 모드 토글글
!normal : 기본 모드 토글
!circulation : 순환매 모드 토글
!buy <USDT> : 현재 가격으로 구매하기
!aianalogy : ai분석 실시
!credit : 크레딧
!helpme : 지금 보는 내용
!update : 패치노트 보기

''')
    

@bot.command(name='credit')
async def credit(ctx):
    await ctx.send('''

    ver 8.0
    last update 2025-01-18
    made by 윈터띠

''')

@bot.command(name='update')
async def update(ctx):
    with open("PATCHNOTE.txt", "r",encoding="utf-8") as file:
        text = file.read()
        await ctx.send(f"```{text}```")

@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')
    print('''
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
    

## 기본 전략
async def start_trading_strategy():
    global is_running, sell_price, sell_date, buying, count, order, leverage, max_pnl, AI_mode, infprofit, waiting, Aicommand, WARNINGFORLOSS, countforwarn
    global msg_system_orig, msg_system_warn_orig, msg_system_circular_orig
    global wait_up, latest_degree, circulation_mode, normal_mode
    global ready_price, analysis2_state, stable_mode, warn_stratage, buymode, loss_amount, buy_ready_price, sell_ready_price

    sell_date = datetime.today()
    sell_price = 0
    ready_date = datetime.today()
    last_buy_date = datetime.today()
    
    sta = None
    current_price = None
    blnc = 0
    inv_amount = 0
    unrealizedProfit = 0
    pnl = 0

    loss_amount = 0


    ready_reason = None
    buy_ready_reason = None
    sell_ready_reason = None

    buy_ready_price = 0
    sell_ready_price = 0
    


    buying = False  # 매수상태일때 True
    count = 0
    order = None
    max_pnl = 0  # 최고 수익률 초기화
    BIGWARNING = False
    lowest_price = 0
    file_path = 0

    difference_in_minutes = 0

    ready_price = 0 # 2차 분석 기준되는 가격
    analysis2_state = False # 2차분석 후 구매예정상태 플래그
    last_buy_price = 0

    print("Trading strategy started")
    message("자동매매를 시작합니다")
    set_leverage(symbol,initial_leverage)

    while is_running:
        try:
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

            msg_current_status = f'''
### Current Status:
Status : {sta}
Balance : {blnc}
Purchase Amount : {inv_amount}
Valuation Amount : {inv_amount + unrealizedProfit}
Current Rate of Return : {pnl}
'''
            msg_stratagy = f'''
You are a Bitcoin Investment Assistance AI, which judges when to buy and when to buy additionally based on given chart data.    

### Investment Strategy:
1. The leverage is set to {leverage} times.  
2. The initial purchase amount is calculated as total assets divided by (2^{n}). 
3. If the return drops to -20% or below, initiate the circular trading mode. If the return falls further to -{addp}% or below, execute additional purchases regardless of potential rebound levels.


### Circular Trading Mode Strategy
Condition:
The circular trading mode is initiated when the current position's return drops to -20% or below. If the return falls to -{addp}% or lower, additional purchases are made regardless of potential rebound levels.

Circular Trading Mode Definition:

1. Execute additional purchases at points where the chart is expected to rebound.
This aims to lower the average entry price (break-even price) of the current position.

2. Sell the amount purchased additionally at points where resistance is likely to occur.
This helps recover a portion of the funds and adjust the position size.


'''


            msg_system = msg_stratagy + msg_system_orig
            msg_user1 = msg_current_status
            msg_user2 = f'''
### You have to do Second analysis
# How you analysed in First analysis:
# price : {ready_price}
# reason : {ready_reason}
''' + msg_current_status
            msg_system_warn = msg_stratagy + f"Now we have done with the {count} additional purchase" + msg_system_warn_orig
            msg_user_warn = f'''
# Last Buy time : {last_buy_date}
# Last Buy Price : {last_buy_price}
# Current time : {today_date}
# Current Price : {current_price}

'''+ msg_current_status
            

            msg_system_circular = msg_stratagy + f"Now we have to do Circular trading mode. buymode:{buymode}" + msg_system_circular_orig

            
            msg_user_circular = msg_current_status + "You have to do First analysis of <Additional purchases Related> and <Sell Related>"
            msg_user_circular_buy2 = msg_current_status + "You have to do second analysis of <Additional purchases Related>" + f'''
# How you analysed in First analysis:
# price : {buy_ready_price}
# reason : {buy_ready_reason}
'''
            msg_user_circular_sell2 = msg_current_status + "You have to do second analysis of <Sell Related>" + f'''
# How you analysed in First analysis:
# price : {sell_ready_price}
# reason : {sell_ready_reason}
'''


            # 매수상태인지 체크
            

            position_info = get_futures_position_info(symbol)
            order = get_latest_order(symbol)
            if position_info != 0 and float(position_info['positionAmt']) != 0:
                buying = True
                if order is not None:
                    order_id = order['orderId']
                    order_status = check_order_status(symbol, order_id)
                    if order_status and order_status['status'] == 'FILLED':
                        message(f"{order_id}\n주문이 체결되었습니다.")
                        order = None
                        waiting = False
                    else:
                        waiting = True

            else:
                buying = False


            cancel_old_orders(client, symbol)

            now = datetime.now()
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

            #############
            ## 매수관련 ##
            #############
            if AI_mode is False and buying is False and order is None:
                if sell_price != 0:
                    if (current_price - sell_price) / sell_price < -bp/100:
                        percentage = 100 / (2 ** n)
                        order_price = round(current_price,1)
                        order = execute_limit_long_order(symbol, order_price, percentage, leverage)
                        iquantity = calculate_order_quantity(percentage)
                        message(f"매수주문완료\n현재가격 : {current_price}\n매수금액 : {iquantity}")
                        last_buy_date = datetime.today()
                    elif 1440 * date_diff_setting + 10 >= minute_diff >= 1440 * date_diff_setting:
                        sell_price = current_price
                        sell_date = datetime.today()

            elif AI_mode is True and order is None:
                
                if Aicommand is True or now.minute == 30: # 1시간마다 측정 , 정기 분석
                    if WARNINGFORLOSS is False:
                        candles = get_5min_candles(symbol, lookback='1000 minutes ago UTC') 
                        file_path = create_tendency_chart(candles)
                        base64_image = encode_image(file_path)

                        if buying is False:
                            sta = 'pending purchase'
                        else:
                            sta = 'Currently Buying'
                        blnc = get_futures_asset_balance()
                        
                        response = openai_response(symbol,msg_system,msg_user1,base64_image)
                        
                        ai_response = json.loads(response.choices[0].message.content)
                        analysis1 = ai_response.get("analysis1")
                        analysis2 = ai_response.get("analysis2")
                        decrease_status = ai_response.get("decrease_status")
                        
                        aimsg1 = f'''

# 🤖 AI ANALYSIS 
현재상태 : {sta}
현재시간 : {now} 
## 📊1차 분석
```
DECISION : {analysis1.get('decision') if analysis1 else None}
PRICE : {analysis1.get('price') if analysis1 else None}
TIME : {analysis1.get('time') if analysis1 else None}
REASON : {analysis1.get('reason') if analysis1 else None}
``` 
## 📊2차 분석
```
DECISION : {analysis2.get('decision') if analysis2 else None}
PRICE : {analysis2.get('degree') if analysis2 else None}
REASON : {analysis2.get('reason') if analysis2 else None}
``` 
## 📉하락 상태
```
STATUS : {decrease_status.get('status') if decrease_status else None}
DEGREE : {decrease_status.get('degree') if decrease_status else None}
REASON : {decrease_status.get('reason') if decrease_status else None}
```
                    
                    '''
                        latest_degree = decrease_status.get('degree') if decrease_status else None
                        message(aimsg1)
                        if float(latest_degree) >= 7:
                            message_alert(f"## ⚠️경고! 현재 하강 추세 강도가 {latest_degree}입니다")
                        if analysis1 != None:
                            if analysis1.get('decision') == 'good':
                                ready_price = float(analysis1.get('price'))
                                ready_reason = analysis1.get('reason')
                                ready_time = analysis1.get('time')
                                ready_date = datetime.today()
                        Aicommand = False
                        await asyncio.sleep(60)
                        

                    elif WARNINGFORLOSS is True and warn_stratage is True:  # warning 경고
                        klines = client.get_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_5MINUTE, limit=10)

                        if current_price <= lowest_price:
                            CheckforLoss = True
                        elif now.minute == 20 or now.minute == 40 or now.minute == 0:
                            CheckforLoss = True
                        else:
                            CheckforLoss = False

                        # 하락 추세 확인 및 최저점 갱신
                        for kline in klines:
                            low_price = float(kline[3])  # 최저가
                            if low_price < lowest_price:
                                lowest_price = low_price
                        
                        
                    elif CheckforLoss == True:
                        candles = get_5min_candles(symbol, lookback='1000 minutes ago UTC') 
                        file_path = create_tendency_chart(candles)
                        base64_image = encode_image(file_path)
                        candles1 = get_1hour_candles(symbol, lookback='100 hours ago UTC')
                        file_path = create_tendency_chart(candles1)
                        base64_image2 = encode_image(file_path)
                        sta = 'Currently Buying'
                        blnc = get_futures_asset_balance()
                        
                        response = openai_response_warn(symbol,msg_system_warn,msg_user_warn,base64_image,base64_image2)
                        ai_response = json.loads(response)
                        state = ai_response.get('state')
                        degree = ai_response.get('degree')
                        reason = ai_response.get('reason')

                        aimsg1_warn = f'''

# 🤖 AI ANALYSIS 
현재상태 : {sta}
현재시간 : {now} 

## 📉급하락 분석
STATE : {state}
DEGREE : {degree}
REASON : {reason}

'''
                        

                        message(aimsg1_warn)
                        if state == 'plummet':
                            BIGWARNING = True
                        elif state == 'normal':
                            WARNINGFORLOSS = False

                        Aicommand = False
                        CheckforLoss = False
                        await asyncio.sleep(60)

                if ready_price != 0 and buying is False:
                    if current_price <= ready_price and analysis2_state is False:
                        #2차분석 실시
                        candles = get_5min_candles(symbol, lookback='1000 minutes ago UTC') 
                        file_path = create_tendency_chart(candles)
                        base64_image = encode_image(file_path)
                        sta = 'pending purchase'
                        blnc = get_futures_asset_balance()
                        response = openai_response(symbol,msg_system,msg_user2,base64_image)
                        ai_response = json.loads(response.choices[0].message.content)
                        analysis1 = ai_response.get("analysis1")
                        analysis2 = ai_response.get("analysis2")
                        decrease_status = ai_response.get("decrease_status")

                        aimsg2 = f'''
                

# 🤖 AI ANALYSIS 
현재상태 : {sta}
현재시간 : {now} 
## 📊1차 분석
```
DECISION : {analysis1.get('decision') if analysis1 else None}
PRICE : {analysis1.get('price') if analysis1 else None}
TIME : {analysis1.get('time') if analysis1 else None}
REASON : {analysis1.get('reason') if analysis1 else None}
``` 
## 📊2차 분석
```
DECISION : {analysis2.get('decision') if analysis2 else None}
PRICE : {analysis2.get('degree') if analysis2 else None}
REASON : {analysis2.get('reason') if analysis2 else None}
``` 
## 📉하락 상태
```
STATUS : {decrease_status.get('status') if decrease_status else None}
DEGREE : {decrease_status.get('degree') if decrease_status else None}
REASON : {decrease_status.get('reason') if decrease_status else None}
```
                    
                    '''
                        message(aimsg2)

                        if analysis2 != None:
                            if analysis2.get('decision') == 'good':
                                analysis2_state = True
                        

                    if analysis2_state is True:
                        if analysis2 != None:
                            if current_price <= ready_price:    
                                percentage = 100 / (2 ** n)
                                order_price = round(current_price,1)
                                order = execute_limit_long_order(symbol, order_price, percentage, leverage)
                                iquantity = calculate_order_quantity(percentage)
                                message(f"매수주문완료\n현재가격 : {current_price}\n매수금액 : {iquantity}")
                                last_buy_date = datetime.today()
                                analysis2_state = False
                                ready_price = 0
                
                    diff = today_date - ready_date
                    if diff.total_seconds() >= 60*60*3:
                        ready_price = 0


            # if buying is False and order is None and wait_up is True:
            #     asdasdasdasd
            #     candles = get_5min_candles(symbol, lookback='1000 minutes ago UTC') 
            #     file_path = create_tendency_chart(candles)
            #     base64_image = encode_image(file_path)
            #     sta = 'pending purchase'
            #     blnc = get_futures_asset_balance()
            #     response = openai_response(symbol,msg_system_wait,msg_user2,base64_image)
            #     ai_response = json.loads(response.choices[0].message.content) 
            #     analysis1 = ai_response.get("analysis1")

            if normal_mode is True and buying is True and order is None:
                # 추가매수 -addp퍼일때
                if pnl <= -addp and waiting is False:
                    order_price = round(current_price,1)
                    inv_size = round(inv_amount / current_price * leverage, 3)
                    order = place_limit_long_order(symbol, order_price, inv_size, leverage)
                    message(f"추가매수주문완료\n현재가격 : {current_price}\n추가매수횟수 : {count}\n매수금액 : {inv_amount}\n레버리지 : {leverage}")
                    waiting = True
                    count += 1
                    last_buy_date = datetime.today()
                    last_buy_price = current_price
                # 최고 수익률 갱신 및 10% 하락 시 매도
                if pnl > max_pnl:
                    max_pnl = pnl
                elif max_pnl >= 25 and pnl <= max_pnl - mpdown:
                    order = close(symbol)
                    message(f"매도완료\n최고 PNL: {max_pnl}%\n현재 PNL: {pnl}%\nRealizedProfit : {unrealizedProfit}")
                    save_to_db(datetime.today(),pnl,unrealizedProfit, count, inv_amount, inv_amount+unrealizedProfit)
                    sell_price = current_price
                    percentage = 100 / 2 ** n
                    count = 0
                    leverage = 20  # 초기 레버리지로 리셋
                    max_pnl = 0  # 최고 수익률 초기화
                    sell_date = datetime.today()
                    last_buy_date = datetime.today()

                time_difference = now - last_buy_date
                difference_in_minutes = time_difference.total_seconds() / 60 
                if difference_in_minutes >= 60*3:
                    if leverage*0.04*2 + 1 < pnl and pnl <= leverage*0.04*2 + 3 and stable_mode is True:
                        order = close(symbol)
                        message(f"본전매도완료\n최고 PNL: {max_pnl}%\n현재 PNL: {pnl}%\nRealizedProfit : {unrealizedProfit}")
                        save_to_db(datetime.today(),pnl,unrealizedProfit, count, inv_amount, inv_amount+unrealizedProfit)
                        sell_price = current_price
                        percentage = 100 / 2 ** n
                        count = 0
                        leverage = 20  # 초기 레버리지로 리셋
                        max_pnl = 0  # 최고 수익률 초기화
                        sell_date = datetime.today()
                        last_buy_date = datetime.today()

                        # wait_up = True

                # 손실 감수 전략
                if warn_stratage is True:
                    if count >= countforwarn and WARNINGFORLOSS is False:
                        if plummet(symbol,40) == True:
                            WARNINGFORLOSS = True
                    else:
                        WARNINGFORLOSS = False

                    if BIGWARNING is True:
                        order = close(symbol)
                        message(f"매도완료\n손실률 : {pnl}\nRealizedLoss : {unrealizedProfit}")
                        save_to_db(datetime.today(),pnl,unrealizedProfit, count, inv_amount, inv_amount+unrealizedProfit)
                        sell_price = current_price
                        percentage = 100 / 2 ** n
                        count = 0
                        leverage = 20  # 초기 레버리지로 리셋
                        max_pnl = 0  # 최고 수익률 초기화
                        sell_date = datetime.today()
                        BIGWARNING = False
                    

                # 총액 매도 30퍼 이득
                if infprofit == False and pnl >= mpp:
                    order = close(symbol)
                    message(f"매도완료\nPNL : {pnl}\nRealizedProfit : {unrealizedProfit}")
                    save_to_db(datetime.today(),pnl,unrealizedProfit, count, inv_amount, inv_amount+unrealizedProfit)
                    sell_price = current_price
                    percentage = 100 / 2 ** n
                    count = 0
                    leverage = 20  # 초기 레버리지로 리셋
                    max_pnl = 0  # 최고 수익률 초기화
                    sell_date = datetime.today()

            if circulation_mode is True and buying is True and order is None:
                # infprofit 모드 off
                if infprofit == False and pnl >= mpp:
                    order = close(symbol)
                    message(f"매도완료\nPNL : {pnl}\nRealizedProfit : {unrealizedProfit}")
                    save_to_db(datetime.today(),pnl,unrealizedProfit, count, inv_amount, inv_amount+unrealizedProfit)
                    sell_price = current_price
                    percentage = 100 / 2 ** n
                    count = 0
                    leverage = 20  # 초기 레버리지로 리셋
                    max_pnl = 0  # 최고 수익률 초기화
                    sell_date = datetime.today()
        
                # infprofit 모드 on
                if pnl > max_pnl:
                    max_pnl = pnl
                elif max_pnl >= 25 and pnl <= max_pnl - mpdown:
                    order = close(symbol)
                    message(f"매도완료\n최고 PNL: {max_pnl}%\n현재 PNL: {pnl}%\nRealizedProfit : {unrealizedProfit}")
                    save_to_db(datetime.today(),pnl,unrealizedProfit, count, inv_amount, inv_amount+unrealizedProfit)
                    sell_price = current_price
                    percentage = 100 / 2 ** n
                    count = 0
                    leverage = 20  # 초기 레버리지로 리셋
                    max_pnl = 0  # 최고 수익률 초기화
                    sell_date = datetime.today()
                    last_buy_date = datetime.today()
                
                # 본전매도 stable 모드
                if difference_in_minutes >= 60*3:
                    if leverage*0.04*2 + 1 < pnl and pnl <= leverage*0.04*2 + 3 and stable_mode is True:
                        order = close(symbol)
                        message(f"본전매도완료\n최고 PNL: {max_pnl}%\n현재 PNL: {pnl}%\nRealizedProfit : {unrealizedProfit}")
                        save_to_db(datetime.today(),pnl,unrealizedProfit, count, inv_amount, inv_amount+unrealizedProfit)
                        sell_price = current_price
                        percentage = 100 / 2 ** n
                        count = 0
                        leverage = 20  # 초기 레버리지로 리셋
                        max_pnl = 0  # 최고 수익률 초기화
                        sell_date = datetime.today()
                        last_buy_date = datetime.today()

                 # 추가매수 -addp퍼일때
                if pnl <= -addp and waiting is False:
                    order_price = round(current_price,1)
                    inv_size = round(inv_amount / current_price * leverage, 3)
                    order = place_limit_long_order(symbol, order_price, inv_size, leverage)
                    message(f"추가매수주문완료\n현재가격 : {current_price}\n추가매수횟수 : {count}\n매수금액 : {inv_amount}\n레버리지 : {leverage}")
                    waiting = True
                    count += 1
                    last_buy_date = datetime.today()
                    last_buy_price = current_price

                
                
                if pnl <= -20 and count == 0:
                    circular_mode = True

                
                # 순환매
                if circular_mode is True:

                    if pnl >= -20:
                        buymode = False
                    else:
                        buymode = True

                    if count >= 1 and pnl > -40:
                        sellmode = True
                    else:
                        sellmode = False

                    if now.minute == 15 or now.minute == 45 or Aicommand is True:
                        candles = get_5min_candles(symbol, lookback='1000 minutes ago UTC') 
                        file_path = create_tendency_chart(candles)
                        base64_image1 = encode_image(file_path)
                        candles1 = get_15min_candles(symbol, lookback='1000 minutes ago UTC')
                        file_path = create_tendency_chart(candles1)
                        base64_image2 = encode_image(file_path)

                        response = openai_response_warn(symbol,msg_system_circular,msg_user_circular,base64_image1,base64_image2)

                        ai_response = json.loads(response.choices[0].message.content)
                        buy_analysis1 = ai_response.get("buy_analysis1")
                        buy_analysis2 = ai_response.get("buy_analysis2")
                        sell_analysis1 = ai_response.get("sell_analysis1")
                        sell_analysis2 = ai_response.get("sell_analysis2")

                        buy_ready_price = float(buy_analysis1.get('price'))
                        buy_ready_reason = buy_analysis1.get('reason')
                        sell_ready_price = float(sell_analysis1.get('price'))
                        sell_ready_reason = sell_analysis1.get('reason')

                        aimsg_c1 = f'''

    # 🤖 CIRCULAR MODE AI ANALYSIS 
    현재상태 : {sta}
    PNL : {pnl}
    현재시간 : {now} 
    ## 🅱️ BUY 1차 분석
    ```
    DECISION : {buy_analysis1.get('decision') if analysis1 else None}
    PRICE : {buy_analysis1.get('price') if analysis1 else None}
    REASON : {buy_analysis1.get('reason') if analysis1 else None}
    ``` 

    ## 💲 SELL 1차 분석
    ```
    DECISION : {sell_analysis1.get('decision') if analysis1 else None}
    PRICE : {sell_analysis1.get('price') if analysis1 else None}
    REASON : {sell_analysis1.get('reason') if analysis1 else None}
    ``` 

                        '''
                        message(aimsg_c1)


                        if buy_analysis1 != None:
                            if buy_analysis1.get('decision') == 'good':
                                buy2_state = True
                        if sell_analysis1 != None:
                            if sell_analysis1.get('decision') == 'good':
                                sell2_state = True
                        Aicommand = False
                        await asyncio.sleep(60)


                    if current_price <= buy_ready_price and buy2_state is True and buymode is True: # 2차분석 buy
                        candles = get_5min_candles(symbol, lookback='1000 minutes ago UTC') 
                        file_path = create_tendency_chart(candles)
                        base64_image1 = encode_image(file_path)
                        candles1 = get_15min_candles(symbol, lookback='1000 minutes ago UTC')
                        file_path = create_tendency_chart(candles1)
                        base64_image2 = encode_image(file_path)

                        response = openai_response_warn(symbol,msg_system_circular,msg_user_circular_buy2,base64_image1,base64_image2)

                        ai_response = json.loads(response.choices[0].message.content)
                        buy_analysis1 = ai_response.get("buy_analysis1")
                        buy_analysis2 = ai_response.get("buy_analysis2")

                        aimsg_cb2 = f'''

    # 🤖 CIRCULAR MODE AI ANALYSIS BUY_2
    현재상태 : {sta}
    PNL : {pnl}
    현재시간 : {now} 

    ## 🅱️ BUY 2차 분석
    ```
    DECISION : {buy_analysis2.get('decision') if analysis2 else None}
    PRICE : {buy_analysis2.get('price') if analysis2 else None}
    REASON : {buy_analysis2.get('reason') if analysis2 else None}
    ``` 
                        '''
                        
                        message(aimsg_cb2)

                    if buy2_state is True:
                        if buy_analysis2 != None:
                            if current_price <= float(buy_analysis2.get('price')):
                                percentage = 100 / (2 ** n)
                                buy_amount = percentage*blnc/100
                                order_price = round(current_price,1)
                                order = execute_limit_long_order(symbol, order_price, percentage, leverage)
                                iquantity = calculate_order_quantity(percentage)
                                message(f"추가매수주문완료\n현재가격 : {current_price}\n매수금액 : {iquantity}")
                                count += 1
                                last_buy_date = datetime.today()
                                buy2_state = False
                                buy_ready_price = 0

                    if current_price >= sell_ready_price and sell2_state is True and sellmode is True: # 2차분석 sell
                        candles = get_5min_candles(symbol, lookback='1000 minutes ago UTC') 
                        file_path = create_tendency_chart(candles)
                        base64_image1 = encode_image(file_path)
                        candles1 = get_15min_candles(symbol, lookback='1000 minutes ago UTC')
                        file_path = create_tendency_chart(candles1)
                        base64_image2 = encode_image(file_path)

                        response = openai_response_warn(symbol,msg_system_circular,msg_user_circular_sell2,base64_image1,base64_image2)

                        ai_response = json.loads(response.choices[0].message.content)
                        sell_analysis1 = ai_response.get("sell_analysis1")
                        sell_analysis2 = ai_response.get("sell_analysis2")

                        aimsg_cs2 = f'''

    # 🤖 CIRCULAR MODE AI ANALYSIS SELL_2
    현재상태 : {sta}
    PNL : {pnl}
    현재시간 : {now} 

    ## 💲 SELL 2차 분석
    ```
    DECISION : {sell_analysis2.get('decision') if analysis2 else None}
    PRICE : {sell_analysis2.get('price') if analysis2 else None}
    REASON : {sell_analysis2.get('reason') if analysis2 else None}
    ``` 

                        '''
                        message(aimsg_cs2)
                    
                    if sell2_state is True:
                        if sell_analysis2 != None:
                            if current_price >= float(sell_analysis2.get('price')):
                                sell_amount = buy_amount
                                loss_amount += abs(sell_amount*pnl/100)
                                order = close_usdt(symbol,leverage,sell_amount)
                                message(f"부분매도주문완료\n현재가격 : {current_price}\n매도도금액 : {sell_amount}")
                                sell2_state = False
                                sell_ready_price = 0

                    if pnl >= 0:
                        if unrealizedProfit >= loss_amount*1.1: # circular mode 탈출
                            sell_amount = inv_amount - blnc/(2 ** n)
                            order = close_usdt(symbol,leverage,sell_amount)
                            message(f"매도주문완료\n현재가격 : {current_price}\n매도도금액 : {sell_amount}")
                            save_to_db(datetime.today(),pnl,unrealizedProfit, count, inv_amount, inv_amount+unrealizedProfit)
                            circular_mode = False
                            sell_price = current_price
                            percentage = 100 / 2 ** n
                            count = 0
                            leverage = 20  # 초기 레버리지로 리셋
                            max_pnl = 0  # 최고 수익률 초기화
                            sell_date = datetime.today()
                            last_buy_date = datetime.today()
                            sellmode = False
                            buymode = False
                            sell2_state = False
                            buy2_state = False
                            loss_amount = 0


                        



            now = datetime.now()
            if now.minute == 0:  # 정시(00분)인지 확인
                if buying is False:
                    status = '🔴매수 대기중'
                else:
                    status = '🟢매수중'
                blnc = get_futures_asset_balance()
                buy_price = sell_price * 0.99

                if infprofit == True:
                    infprofitmode = '🟢ON'
                else:
                    infprofitmode = '🔴OFF'

                if AI_mode == True:
                    aimode_msg = '🟢ON'
                else:
                    aimode_msg = '🔴OFF'

                if WARNINGFORLOSS is True:
                    warn = "⚠️WARNING"
                else:
                    warn = "🔆normal"

                msg = f'''
# 🪙 STATUS
```
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
Infinte Profit Mode : {infprofitmode}
AI trade Mode : {aimode_msg}
WARNING : {warn}
Loss Amount : {loss_amount}
```
                '''
                message(msg)
                await asyncio.sleep(60)

            await asyncio.sleep(10)
        except Exception as e:
            error_log = f"""
            오류 발생: {e}
            위치: {traceback.format_exc()}
            현재 상태:
            buying: {buying}
            current_price: {current_price}
            sell_price: {sell_price}
            """
            message(error_log)
