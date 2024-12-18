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

with open("msg_system.txt", "r",encoding="utf-8") as file:
    msg_system = file.read()
with open("msg_system_warn.txt","r",encoding="utf-8") as file:
    msg_system_warn = file.read()

Aicommand = False
is_running = False

setup(bot)

init_db()
bot.run(TOKEN)