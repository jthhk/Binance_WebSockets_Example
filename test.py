import re
import aiohttp
import asyncio
import time
from datetime import datetime
from helpers.parameters import parse_args, load_config
import pandas as pd
import pandas_ta as ta
import ccxt
import requests
import sys
import os
import websocket, json,pprint
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException

# Load creds modules
from helpers.handle_creds import (
	load_correct_creds, load_discord_creds
)

# Settings
args = parse_args()
DEFAULT_CONFIG_FILE = 'config.yml'
DEFAULT_CREDS_FILE = 'creds.yml'


config_file = args.config if args.config else DEFAULT_CONFIG_FILE
creds_file = args.creds if args.creds else DEFAULT_CREDS_FILE
parsed_creds = load_config(creds_file)
parsed_config = load_config(config_file)

# Load trading vars
PAIR_WITH = parsed_config['trading_options']['PAIR_WITH']
EX_PAIRS = parsed_config['trading_options']['FIATS']
TEST_MODE = parsed_config['script_options']['TEST_MODE']
TAKE_PROFIT = parsed_config['trading_options']['TAKE_PROFIT']
DISCORD_WEBHOOK = load_discord_creds(parsed_creds)

# Load creds for correct environment
access_key, secret_key = load_correct_creds(parsed_creds)
client = Client(access_key, secret_key)


# If True, an updated list of coins will be generated from the site - http://edgesforledges.com/watchlists/binance.
# If False, then the list you create in TICKERS_LIST = 'tickers.txt' will be used.
CREATE_TICKER_LIST = False

# When creating a ticker list from the source site:
# http://edgesforledges.com you can use the parameter (all or innovation-zone).
# ticker_type = 'innovation-zone'
ticker_type = 'all'
if CREATE_TICKER_LIST:
	TICKERS_LIST = 'tickers_all_USDT.txt'
else:
	TICKERS_LIST = 'tickers.txt'

# System Settings
BVT = False
OLORIN = True  # if not using Olorin Sledge Fork set to False
if OLORIN:
	signal_file_type = '.buy'
else:
	signal_file_type = '.exs'

# send message to discord
DISCORD = False

# Strategy Settings
LIMIT = 4
INTERVAL = '1d'
profit_min = 15
profit_max = 100  # only required if you want to limit max profit
percent_below = 0.6  # change risk level:  0.7 = 70% below high_price, 0.5 = 50% below high_price
# movement can be either:
#  "MOVEMENT" for original movement calc
#  "ATR_MOVEMENT" for Average True Range Percentage calc
MOVEMENT = 'MOVEMENT'

# Display Setttings
all_info = True
block_info = False

class TextColors:
	BUY = '\033[92m'
	WARNING = '\033[93m'
	SELL_LOSS = '\033[91m'
	SELL_PROFIT = '\033[32m'
	DIM = '\033[2m\033[35m'
	DEFAULT = '\033[39m'
	YELLOW = '\033[33m'
	TURQUOISE = '\033[36m'
	UNDERLINE = '\033[4m'
	END = '\033[0m'
	ITALICS = '\033[3m'
	TCR = '\033[91m'
	TCG = '\033[32m'
	TCD = '\033[39m'

def msg_discord(msg):

	message = msg + '\n\n'

	mUrl = "https://discordapp.com/api/webhooks/"+DISCORD_WEBHOOK
	data = {"content": message}
	response = requests.post(mUrl, json=data)

#########################################################################
# Websocket module parameters
#########################################################################
# Websocket functions, to inform about current status
def on_open(ws):
    print("Opened connection.")

def on_close(ws):
    print("Closed connection.")

def on_message(ws, message):

    print("Received message.")
    event = json.loads(message)
    #pprint.pprint(event)
    
    try:
        eventtype = event['e'] 
    except:
        eventtype = "BookTicker"
    
    if eventtype == "kline":
        print("kline update")
        candle=event['k']
        is_candle_closed = candle['x']
        #if is_candle_closed:
        symbol = candle["s"]
        Interval = candle["i"]
        highest = candle['h'] 
        lowest = candle['l']
        open = candle['o']
        close = candle['c']
            
    elif eventtype == "aggTrade":
        print("aggTrade update")
        is_market_maker = event['x']
        symbol = event["s"]
        LastPx = event["p"]
        LastQty = event["q"]
        #side = "B" 
        #if is_market_maker:
        #    side = "S" 
    else:
        print("bookTicker update")
        symbol = event["s"]
        BBPx = event["b"]
        BBQty = event["B"]
        BAPx = event["a"]
        BAQty = event["A"]
        

########################################################################

def do_work():
    #Define watch list  
    #tickers = [line.strip() for line in open(TICKERS_LIST)]
    SOCKET_URL= "wss://stream.binance.com:9443/ws/"
    
    current_ticker_list = ["ethbtc@bookTicker","bnbbtc@bookTicker"]
    SOCKET = SOCKET_URL + '/'.join(current_ticker_list)
    print(SOCKET)
    ticker_list = websocket.WebSocketApp(SOCKET, on_open=on_open, on_close=on_close, on_message=on_message)
    print("CTRL+C to cxl and move to next worker")
    ticker_list.run_forever()

    current_potential_list = ["ethbtc@kline_1m","ethbtc@kline_5m"]
    SOCKET = SOCKET_URL + '/'.join(current_potential_list)
    print(SOCKET)
    potential_list = websocket.WebSocketApp(SOCKET, on_open=on_open, on_close=on_close, on_message=on_message)
    print("CTRL+C to cxl and move to next worker")
    potential_list.run_forever()
    
    current_trade_list = ["ethbtc@aggTrade","ethbtc@aggTrade"]
    SOCKET = SOCKET_URL + '/'.join(current_trade_list)
    print(SOCKET)
    trade_list = websocket.WebSocketApp(SOCKET, on_open=on_open, on_close=on_close, on_message=on_message)
    print("CTRL+C to cxl and close")
    trade_list.run_forever()


if __name__ == '__main__':
	do_work()