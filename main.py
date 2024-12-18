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

from functions import *
from discord_funtions import *


# Intents 설정
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='#', intents=intents)

key_file_path = "keys.json"

# JSON 파일 읽기
with open(key_file_path, "r") as file:
    data = json.load(file)

# 변수에 접근
api_key = data["api_key"]
api_secret = data["api_secret"]
openai_api_key = data['openai_api_key']
TOKEN = data['TOKEN']
webhook_url = data['webhook_url']
webhook_url_alert = data['webhook_url_alert']


client = Client(api_key, api_secret)
openaiclient = OpenAI(api_key=openai_api_key)


symbol = 'BTCUSDT'
leverage = 20



Aicommand = False
is_running = False




setup(bot)

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

init_db()
bot.run(TOKEN)