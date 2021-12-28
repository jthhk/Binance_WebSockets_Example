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
import ccxt

import threading
from threading import Thread, Event

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
DROP_CALCULATION = False

# Display Setttings
all_info = True
block_info = False

# buy coin file 
if TEST_MODE:
    coin_path = 'test_coins_bought.json'
else:
    if BVT:
        coin_path = 'coins_bought.json'
    else:
        coin_path = 'live_coins_bought.json'

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
def on_open(ws):
    print("Opened connection.")

def on_close(ws,close_status_code, close_msg):
    print("Closed connection.")

def on_error(ws):

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
        InitializeDataFeed()


    
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
        MarketData.loc[Index, ['interval']] = candle["i"]
        MarketData.loc[Index, ['high']] = candle["h"]
        MarketData.loc[Index, ['low']] = candle["l"]
        MarketData.loc[Index, ['open']] =  candle["o"]
        MarketData.loc[Index, ['close']] =  candle["c"]

        if is_candle_closed:
            #refresh candles
            get_data_frame(symbol)        
        
    elif eventtype == "aggTrade":
        #is_market_maker = event['x']
        symbol = event["s"]
        Index = MarketData.loc[MarketData['symbol'] == symbol].index.item()
        MarketData.loc[Index, ['LastPx']] =  event["p"]
        MarketData.loc[Index, ['LastQty']] =  event["q"]
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
    elif eventtype == "Ping":
        pong_json = { 'Type':'Pong' }
        ws.send(json.dumps(pong_json))
        print("SENT:")
        print(json.dumps(pong_json, sort_keys=True, indent=2, separators=(',', ':')))
    elif eventtype == "error":
        pprint.pprint(event)

         


########################################################################

def get_data_frame(symbol):

    global MarketPriceFrames

    exchange = ccxt.binance()
    timeframes = ['5m','15m','4h', '1d']
    for item in timeframes:	
        macd = exchange.fetch_ohlcv(symbol, timeframe=item, limit=36)
        df1  = pd.DataFrame(macd, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        macd = df1.ta.macd(fast=12, slow=26)
        Index = MarketPriceFrames.loc[MarketPriceFrames['symbol'] == symbol].index.item()
        MarketPriceFrames.loc[Index, item] =  macd.iloc[35][1]
        MarketPriceFrames.loc[Index, ['updated']] = datetime.now()


def InitializeDataFeed():
    
    global MarketData, MarketPriceFrames, web_socket_app

    SOCKET_URL= "wss://stream.binance.com:9443/ws/"
    SOCKET_LIST = ["coin@bookTicker","coin@kline_1m","coin@aggTrade"]
    current_ticker_list = []
    #-------------------------------------------------------------------------------
    #Create a dataframe to hold the latest coin data from multiple requests 
    MarketData = pd.DataFrame(columns=['symbol', 'open', 'high', 'low', 'close', 'interval','LastPx','LastQty','BBPx','BBQty','BAPx','BAQty','updated'])
    MarketData['symbol']=MarketData.index
    MarketData = MarketData.reset_index(drop=True)
    
    #Create a dataframe to hold the latest coin data from multiple requests 
    MarketPriceFrames = pd.DataFrame(columns=['symbol', '5m', '15m', '4h', '1d','updated'])
    MarketPriceFrames['symbol']=MarketPriceFrames.index
    MarketPriceFrames = MarketPriceFrames.reset_index(drop=True)

    #-------------------------------------------------------------------------------
    #Define watch list 
    CoinsCounter = 0
    tickers = [line.strip() for line in open(TICKERS_LIST)]
    print( str(datetime.now()) + " :Preparing watch list defined in tickers file...")
    for item in tickers:
        #Create Dataframes with coins
        coin = item + PAIR_WITH
        data =  {'symbol': coin}
        MarketData= MarketData.append(data,ignore_index=True)
        MarketPriceFrames= MarketPriceFrames.append(data,ignore_index=True)
        get_data_frame(coin)  #not sure about this TBH
        coinlist= [sub.replace('coin', coin.lower()) for sub in SOCKET_LIST]
        current_ticker_list.extend(coinlist)
        CoinsCounter += 1

    print(f'{str(datetime.now())}: Total Coins: {CoinsCounter}')

    if DEBUG:
        print (MarketData) 
        print (current_ticker_list) 
        print (MarketPriceFrames) 

    #-------------------------------------------------------------------------------
    SOCKET = SOCKET_URL + '/'.join(current_ticker_list)
    print( str(datetime.now()) + " :Connecting to WebSocket " + SOCKET + " ...")
    web_socket_app = websocket.WebSocketApp(SOCKET, header=['User-Agent: Python'],
                                        on_message=on_message,
                                        on_error=on_error,
                                        on_close=on_close)
    web_socket_app.on_open = on_open

    # Event loop
    wst = threading.Thread(target=web_socket_app.run_forever)
    wst.start()
    #-------------------------------------------------------------------------------



if __name__ == '__main__':
    
    if DEBUG : print ("DEBUG is enabled - get ready for lots of data")
    
    global MarketData, MarketPriceFrames, web_socket_app
    exchange = ccxt.binance()

    #Setup the ticker dataframe and Websockets
    InitializeDataFeed()

    try:
        while True:

            #Get Held coins so we don't but 2 of the same
            held_coins_list = {}            
            CoinsCounter = 0
            CoinsSkippedCounter = 0 
            CoinsBuyCounter = 0

            if os.path.isfile(coin_path) and os.stat(coin_path).st_size != 0:
                with open(coin_path) as file:
                    held_coins_list = json.load(file)	

            #Get bitcoinpx for ref 
            macdbtc = exchange.fetch_ohlcv('BTCUSDT', timeframe='1m', limit=36)
            dfbtc = pd.DataFrame(macdbtc, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            macdbtc = dfbtc.ta.macd(fast=12, slow=26)
            get_histbtc = macdbtc.iloc[35, 1]
            
            for index, row in MarketData.iterrows():                         

                symbol = MarketData.loc[index]['symbol']
                CoinsCounter += 1
                if (symbol in held_coins_list):
                    CoinsSkippedCounter += 1
                    if DEBUG:   
                        print(f'{TextColors.DEFAULT}{symbol} Skipping as we already hold \n')
                else:
                    ##################################################################
                    #Get the latest market data 
                    ##################################################################
                    last_price = float(MarketData.loc[index]['LastPx'])
                    high_price = float(MarketData.loc[index]['high'])
                    low_price = float(MarketData.loc[index]['low'])
                    bid_price = float(MarketData.loc[index]['BBPx'])
                    ask_price = float(MarketData.loc[index]['BAPx'])
                    close_price = float(MarketData.loc[index]['close'])

                    #Candle data 
                    iIndex = MarketData.loc[MarketData['symbol'] == symbol].index.item()
                    macd5m = MarketPriceFrames.loc[iIndex, '5m']
                    macd15m = MarketPriceFrames.loc[iIndex, '15m']
                    macd4h = MarketPriceFrames.loc[iIndex, '4h']
                    macd1d = MarketPriceFrames.loc[iIndex, '1d']

                    #Standard Strategy Calcs 
                    range = high_price - low_price
                    potential = (low_price / high_price) * 100
                    buy_above = low_price * 1.00
                    current_range = high_price - last_price
                    current_potential = ((high_price / last_price) * 100) - 100
                    buy_below = high_price - (range * percent_below)
                    if range == 0: 
                        #it is possible to have the samw High/low/last trade resulting in "Cannot divide by zero"
                        movement = 0
                    else:
                        movement = (low_price / range)                            
                    
                    macd1m = MarketData.loc[index, 'close']  #using close of candle but some may want to use open

                    ##################################################################
                    #Do your custom strategy calcs
                    max_potential = potential * profit_max 
                    min_potential = potential * profit_min
                    current_drop = (100 * (current_range)) / high_price

                    atr = []               # average true range
                    atr.append(high_price-low_price)
                    atr_percentage = ((sum(atr)/len(atr)) / close_price) * 100
                    ##################################################################
                    #Do your strategy check
                    Custom_Fields = ""
                    RealTimeCheck = False
                    TimeFrameCheck = False 
                    TimeFrameOption = False
                    BuyCoin = False

                    if DROP_CALCULATION:
                        current_potential = current_drop
                    
                    #Different models 
                    if MOVEMENT == "MOVEMENT":
                        TimeFrameOption = (movement >= (TAKE_PROFIT + 0.2))
                    elif MOVEMENT ==  "ATR_MOVEMENT":
                        TimeFrameOption = (atr_percentage >= TAKE_PROFIT)
                    else:
                        TimeFrameOption = True

                    #Main Strategy checker
                    if TimeFrameOption:
                        RealTimeCheck = (profit_min < current_potential < profit_max and last_price < buy_below)
                        if RealTimeCheck:
                            TimeFrameCheck = (macd1m >= 0 and macd5m  >= 0 and macd15m >= 0 and macd1d >= 0 and get_histbtc >= 0)
                            if TimeFrameCheck:
                                BuyCoin = True

                    #Custom logging output
                    Custom_Fields = (
                                    "f'Max Profit:       {max_potential:.2f}%\n'" 
                                    "f'Min Profit:       {min_potential:.2f}%\n'"
                                    )

                    if DEBUG:
                        print(f'{TextColors.DEFAULT}{symbol} RealTimecheck:{RealTimeCheck} Timeframecheck:{TimeFrameCheck} TimeFrameOption: {TimeFrameOption} \n')

                    ##################################################################
                    #Buy coin check
                    ##################################################################
                    if BuyCoin:
                        CoinsBuyCounter += 1
                        # add to signal
                        with open(f'signals/snail_scan{signal_file_type}', 'a+') as f:
                            f.write(str(symbol) + '\n')
                            print(f'{TextColors.BUY}{str(datetime.now())}:{symbol} \n')


                    ##################################################################
                    #Debug Output
                    ##################################################################
                    if DEBUG:
                        print(f'\nCoin:            {symbol}\n'
                            f'Price:            ${last_price:.3f}\n'
                            f'Bid:            ${bid_price:.3f}\n'
                            f'Ask:            ${ask_price:.3f}\n'
                            f'High:             ${high_price:.3f}\n'
                            f'Low:             ${low_price:.3f}\n'
                            f'Close:             ${close_price:.3f}\n'
                            f'Day Max Range:    ${range:.3f}\n'
                            f'Current Range:    ${current_range:.3f} \n'
                            f'Daily Range:      ${range:.3f}\n'
                            f'Current Range     ${current_range:.3f} \n'
                            f'Potential profit before safety: {potential:.0f}%\n'
                            f'Buy above:        ${buy_above:.3f}\n'
                            f'Buy Below:        ${buy_below:.3f}\n'
                            f'Potential profit: {current_potential:.0f}%'
                            f'Movement:         {movement:.2f}%\n'
                            f'{Custom_Fields}'
                            f'Last Update:      {datetime.now()}\n'
                            )
                        print (MarketData)            
                        print ("-------MACD--------")
                        print(f'\nCoin:            {symbol}\n'
                            f'macd1m:             {macd1m}\n'
                            f'macd5m:             {macd5m}\n'
                            f'macd15m:            {macd15m}\n'
                            f'macd4h:             {macd4h}\n'
                            f'macd1d:             {macd1d}\n'
                            )
                        print (MarketPriceFrames)            
                        print ("-------Bitcoin--------")
                        print (f"get_histbtc:   {get_histbtc}")

            print(f'{str(datetime.now())}: Total Coins Scanned: {CoinsCounter} Skipped:{CoinsSkippedCounter} Reviewed:{CoinsCounter - (CoinsSkippedCounter + CoinsBuyCounter)} Bought:{CoinsBuyCounter}')
            time.sleep(3)
            
    except Exception as e:
        print(str(e))
        print("Error on line {}".format(sys.exc_info()[-1].tb_lineno))
        
        #only pushing data frm dataframe to help debug 
        print(f'\nCoin:            {symbol}\n'
            f'Price:            ${last_price:.3f}\n'
            f'Bid:            ${bid_price:.3f}\n'
            f'Ask:            ${ask_price:.3f}\n'
            f'High:             ${high_price:.3f}\n'
            f'Low:             ${low_price:.3f}\n'
            f'Close:             ${close_price:.3f}\n'
            )

        web_socket_app.close()
    except KeyboardInterrupt:
        web_socket_app.close()
