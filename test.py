import time
from datetime import datetime
from helpers.parameters import parse_args, load_config
import pandas as pd
import pandas_ta as ta
import sys
import os
import websocket, json,pprint
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException
import logging
logger = logging.getLogger('websocket')
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler())
# websocket._logging._logger.level = -99

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
    #print (ws.sock.connected)

def on_close(ws):
    print("Closed connection.")

def on_error(ws,error):
    #getting all the error information
    print ('On_Error')
    print (os.sys.exc_info()[0:2])
    print ('Error info: %s' %(error))
    print(error)
    TriggerRestart = True

    if ( "timed" in str(error) ):
        print ( "WebSocket Connenction is getting timed out: Please check the netwrork connection")
    elif( "getaddrinfo" in str(error) ):
        print ( "Network connection is lost: Cannot connect to the host. Please check the network connection ")
    elif( "unreachable host" in str(error) ):
        print ( "Cannot establish connetion with B6-Web: Network connection is lost or host is not running")
    else:
        TriggerRestart = False    

    if TriggerRestart:
        #for recreatng the WebSocket connection 
        if (ws is not None):
            #ws.close()
            ws.on_message = None
            ws.on_open = None
            ws.close = None    
            print ('deleting ws')
            del ws

        #Forcebly set ws to None            
        ws = None

        count = 0
        print ( "Websocket Client trying  to re-connect" ) 
        do_work()


    
def on_message(ws, message):

    global MarketData

    if DEBUG : print("Received message.")
    event = json.loads(message)
    
    try:
        eventtype = event['e'] 
    except:
        eventtype = "BookTicker"
    
    if DEBUG : print(f"{eventtype} event")

    if eventtype == "kline":
        candle=event['k']
        #Need to check Candle is closed 
        is_candle_closed = candle['x']
        symbol = candle["s"]
        Index = MarketData.loc[MarketData['symbol'] == symbol].index.item()
        if is_candle_closed:
            MarketData.loc[Index, ['interval']] = candle["i"]
            MarketData.loc[Index, ['high']] = candle["h"]
            MarketData.loc[Index, ['low']] = candle["l"]
            MarketData.loc[Index, ['open']] =  candle["o"]
            MarketData.loc[Index, ['close']] =  candle["c"]
            MarketData.loc[Index, ['kline']] =  True
        
    elif eventtype == "aggTrade":
        #is_market_maker = event['x']
        symbol = event["s"]
        Index = MarketData.loc[MarketData['symbol'] == symbol].index.item()
        MarketData.loc[Index, ['LastPx']] =  event["p"]
        MarketData.loc[Index, ['LastQty']] =  event["q"]
        MarketData.loc[Index, ['aggTrade']] =  True
        #side = "B" 
        #if is_market_maker:
        #    side = "S" 
    elif eventtype == "BookTicker":
        #data = {'BBPx' : event["b"],  'BBQty' : event["B"], 'BAPx' : event["a"], 'BAQty' : event["A"], 'bookTicker' : 1 }
        symbol = event["s"]
        Index = MarketData.loc[MarketData['symbol'] == symbol].index.item()
        MarketData.loc[Index, ['BBPx']] =  event["b"]
        MarketData.loc[Index, ['BBQty']] =  event["B"]
        MarketData.loc[Index, ['BAPx']] =  event["a"]
        MarketData.loc[Index, ['BAQty']] =  event["A"]
        MarketData.loc[Index, ['bookTicker']] =  True
    elif eventtype == "error":
        pprint.pprint(event)


    if MarketData.loc[Index]['bookTicker']  and MarketData.loc[Index]['aggTrade'] and MarketData.loc[Index]['kline']:
        #do your strategy check
        #only trigegrs when we get a full set of data eg int he end of the candle/kline 

        last_price = float(MarketData.loc[Index]['LastPx'])
        high_price = float(MarketData.loc[Index]['high'])
        low_price = float(MarketData.loc[Index]['low'])
        range = high_price - low_price
        potential = (low_price / high_price) * 100
        buy_above = low_price * 1.00
        buy_below = high_price - (range * percent_below)
        current_range = high_price - last_price
        max_potential = potential * 0.98
        min_potential = potential * 0.6
        safe_potential = potential - 12
        current_potential = ((high_price / last_price) * 100) - 100
        movement = (low_price / range)
        print(f'{symbol} {current_potential:.2f}% M:{movement:.2f}%')

        print(f'\nCoin:            {symbol}\n'
            f'Price:            ${last_price:.3f}\n'
            f'High:             ${high_price:.3f}\n'
            f'Low:             ${low_price:.3f}\n'
            f'Day Max Range:    ${range:.3f}\n'
            f'Current Range:    ${current_range:.3f} \n'
            f'Daily Range:      ${range:.3f}\n'
            f'Current Range     ${current_range:.3f} \n'
            f'Potential profit before safety: {potential:.0f}%\n'
            f'Buy above:        ${buy_above:.3f}\n'
            f'Buy Below:        ${buy_below:.3f}\n'
            f'Potential profit: {TextColors.TURQUOISE}{current_potential:.0f}%{TextColors.DEFAULT}'
            f'Max Profit {max_potential:.2f}%\n'
            f'Min Profit {min_potential:.2f}%\n'
            )
        print (MarketData)            

        #Reset update flags 
        MarketData.loc[Index, ['bookTicker']] = False
        MarketData.loc[Index, ['aggTrade']] = False
        MarketData.loc[Index, ['kline']] = False

        if DEBUG : print (MarketData)            
        
 

########################################################################

def do_work():
    
    global MarketData

    SOCKET_URL= "wss://stream.binance.com:9443/ws/"
    SOCKET_LIST = ["coin@bookTicker","coin@kline_1m","coin@aggTrade"]
    current_ticker_list = []
    #-------------------------------------------------------------------------------
    #Create a dataframe to hold the latest coin data from multiple requests 
    MarketData = pd.DataFrame(columns=['symbol', 'open', 'high', 'low', 'close', 'interval','LastPx','LastQty','BBPx','BBQty','BAPx','BAQty','kline','aggTrade','bookTicker','updated'])
    MarketData['symbol']=MarketData.index
    MarketData = MarketData.reset_index(drop=True)

    #-------------------------------------------------------------------------------
    #Define watch list - Should be a loop hardcode for now  
    tickers = [line.strip() for line in open(TICKERS_LIST)]
    for item in tickers:
        coin = item + PAIR_WITH
        data =  {'symbol': coin}
        MarketData= MarketData.append(data,ignore_index=True)
        coinlist= [sub.replace('coin', coin.lower()) for sub in SOCKET_LIST]
        current_ticker_list.extend(coinlist)

    if DEBUG:
        print (MarketData) 
        print (current_ticker_list) 

    #-------------------------------------------------------------------------------
    SOCKET = SOCKET_URL + '/'.join(current_ticker_list)
    print(SOCKET)
    ticker_list = websocket.WebSocketApp(SOCKET, on_open=on_open, on_close=on_close, on_message=on_message, on_error=on_error)
    print("CTRL+C to cxl")
    ticker_list.run_forever()
    ticker_list.close()


if __name__ == '__main__':
    if DEBUG : print ("DEBUG is enabled")
    
    do_work()
