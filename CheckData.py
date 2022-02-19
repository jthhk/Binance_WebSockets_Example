import time
from datetime import datetime
from helpers.parameters import parse_args, load_config
import pandas as pd
import pandas_ta as ta
import sys
import os
import websocket, json,pprint
import threading
from threading import Thread, Event
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException
import ccxt
import logging
logger = logging.getLogger('websocket')
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler())
# logging needed otherwise slient fails

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
DEBUG = parsed_config['script_options']['DEBUG']
DISCORD_WEBHOOK = load_discord_creds(parsed_creds)

# Load creds for correct environment
print("Loading access_key....")
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

# Display Setttings
all_info = False
block_info = True


if __name__ == '__main__':

    
    if DEBUG : print ("DEBUG is enabled - get ready for lots of data, may want to use block_info instead")
    
    exchange = ccxt.binance()

    try:
        #while True:

        symbol = "LPTUSDT"
        macdbtc = exchange.fetch_ohlcv(item, timeframe='1m', limit=36)
        dfbtc = pd.DataFrame(macdbtc, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        macdbtc = dfbtc.ta.macd(fast=12, slow=26)
        get_histbtc = float(macdbtc.iloc[35, 1])
        print(item + ' 15m MACD=' + str(get_histbtc) + '| px=' + str(price))

            
    except Exception as e:
        print(str(e))
        print("Error on line {}".format(sys.exc_info()[-1].tb_lineno))
        

