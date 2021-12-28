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
all_info = False
block_info = True

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


#############################START OF WEB SOCKET###########################################
def on_open(ws):
    print("Opened connection.")

def on_close(ws,close_status_code, close_msg):
    print("Closed connection.")

def on_error(ws):
    ########################################################
    #Handle disconnects/timeouts and try to reconnect 
    ########################################################
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
    ########################################################
    #Handles each event sent and puts it into the correct dataframe (MarketData)
    #TO DO: PING
    ########################################################

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

        #fall back as aggTrade or close may not be in yet
        if is_nan(MarketData.loc[Index]['close']):
            MarketData.loc[Index, ['close']] = candle["o"]

        if is_nan(MarketData.loc[Index]['LastPx']):
            MarketData.loc[Index, ['LastPx']] = candle["o"]

        if is_candle_closed:
            #refresh candles
            get_data_frame(symbol)        
        
    elif eventtype == "aggTrade":
        symbol = event["s"]
        Index = MarketData.loc[MarketData['symbol'] == symbol].index.item()
        MarketData.loc[Index, ['LastPx']] =  event["p"]
        MarketData.loc[Index, ['LastQty']] =  event["q"]
        #is_market_maker = event['x']
        #side = "B" 
        #if is_market_maker:
        #    side = "S" 
    elif eventtype == "BookTicker":
        symbol = event["s"]
        Index = MarketData.loc[MarketData['symbol'] == symbol].index.item()
        MarketData.loc[Index, ['BBPx']] =  event["b"]
        MarketData.loc[Index, ['BBQty']] =  event["B"]
        MarketData.loc[Index, ['BAPx']] =  event["a"]
        MarketData.loc[Index, ['BAQty']] =  event["A"]

        #fall back as aggTrade or close may not be in yet
        if is_nan(MarketData.loc[Index]['close']):
            MarketData.loc[Index, ['close']] = event["a"]

        if is_nan(MarketData.loc[Index]['LastPx']):
            MarketData.loc[Index, ['LastPx']] = event["a"]

    elif eventtype == "Ping":
        pong_json = { 'Type':'Pong' }
        ws.send(json.dumps(pong_json))
        print("SENT:")
        print(json.dumps(pong_json, sort_keys=True, indent=2, separators=(',', ':')))
    elif eventtype == "error":
        pprint.pprint(event)

#############################END OF WEB SOCKET###########################################

def is_nan(x):
    return (x != x)

def get_data_frame(symbol):
    #######################################
    #Get the historic data for each stock and store in a dataframe (MarketPriceFrames)
    #TO DO: need to move to Web socket - slows the whole thing down if large number of coins
    #######################################

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
    #######################################
    # (a) Create 2 daat drames one for Current market data (MarketData), second for the historic data (MarketPriceFrames)
    # (b) Define watch list and create a row for every coin 
    # (c) Open Web socket to start collecting market data into the Dataframes  
    # TO DO: Review: Looking at 3 things - SOCKET_LIST - bookTicker and aggTrade are pretty busy 
    # ######################################    
    global MarketData, MarketPriceFrames, web_socket_app

    SOCKET_URL= "wss://stream.binance.com:9443/ws/"
    SOCKET_LIST = ["coin@bookTicker","coin@kline_1m","coin@aggTrade"]
    current_ticker_list = []
    #-------------------------------------------------------------------------------
    #(a) Create a dataframe to hold the latest coin data from multiple requests 
    MarketData = pd.DataFrame(columns=['symbol', 'open', 'high', 'low', 'close', 'interval','LastPx','LastQty','BBPx','BBQty','BAPx','BAQty','updated'])
    MarketData['symbol']=MarketData.index
    MarketData = MarketData.reset_index(drop=True)
    
    #Create a dataframe to hold the latest coin data from multiple requests 
    MarketPriceFrames = pd.DataFrame(columns=['symbol', '5m', '15m', '4h', '1d','updated'])
    MarketPriceFrames['symbol']=MarketPriceFrames.index
    MarketPriceFrames = MarketPriceFrames.reset_index(drop=True)

    #-------------------------------------------------------------------------------
    # (b) Define watch list and add a row for each coin in the two dataframes
    CoinsCounter = 0
    tickers = [line.strip() for line in open(TICKERS_LIST)]
    print( str(datetime.now()) + " :Preparing watch list defined in tickers file...")
    for item in tickers:
        #Create Dataframes with coins
        coin = item + PAIR_WITH
        data =  {'symbol': coin}
        MarketData= MarketData.append(data,ignore_index=True)
        MarketPriceFrames= MarketPriceFrames.append(data,ignore_index=True)
        get_data_frame(coin)  
        coinlist= [sub.replace('coin', coin.lower()) for sub in SOCKET_LIST]
        current_ticker_list.extend(coinlist)
        CoinsCounter += 1

    print(f'{str(datetime.now())}: Total Coins: {CoinsCounter}')

    if DEBUG:
        print (MarketData) 
        print (current_ticker_list) 
        print (MarketPriceFrames) 

    #-------------------------------------------------------------------------------
    # (c) Create a Web Socket to get the market data 
    SOCKET = SOCKET_URL + '/'.join(current_ticker_list)
    print( str(datetime.now()) + " :Connecting to WebSocket ...")
    if DEBUG:
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
    
    if DEBUG : print ("DEBUG is enabled - get ready for lots of data, may want to use block_info instead")
    
    global MarketData, MarketPriceFrames, web_socket_app
    exchange = ccxt.binance()

    #(a) Setup the ticker dataframe and Websockets
    InitializeDataFeed()

    try:
        while True:

            held_coins_list = {}            
            CoinsCounter = 0
            CoinsSkippedCounter = 0 
            CoinsBuyCounter = 0
            Custom_Fields = ""

            #Get Held coins so we don't but 2 of the same
            if os.path.isfile(coin_path) and os.stat(coin_path).st_size != 0:
                with open(coin_path) as file:
                    held_coins_list = json.load(file)	

            #Get bitcoinpx for ref 
            macdbtc = exchange.fetch_ohlcv('BTCUSDT', timeframe='1m', limit=36)
            dfbtc = pd.DataFrame(macdbtc, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            macdbtc = dfbtc.ta.macd(fast=12, slow=26)
            get_histbtc = float(macdbtc.iloc[35, 1])
            
            for index, row in MarketData.iterrows():                         

                symbol = MarketData.loc[index]['symbol']
                CoinsCounter += 1
                if (symbol in held_coins_list):
                    CoinsSkippedCounter += 1
                    if block_info:   
                        print(f'{TextColors.DEFAULT}{symbol} Skipping as we already holding \n')
                else:
                    #-----------------------------------------------------------------
                    #Get the latest market data 
                    last_price = float(MarketData.loc[index]['LastPx'])
                    high_price = float(MarketData.loc[index]['high'])
                    low_price = float(MarketData.loc[index]['low'])
                    bid_price = float(MarketData.loc[index]['BBPx'])
                    ask_price = float(MarketData.loc[index]['BAPx'])
                    close_price = float(MarketData.loc[index]['close'])
                    current_bid = float(MarketData.loc[index]['BBPx'])
                    current_ask = float(MarketData.loc[index]['BAPx'])

                    #Candle data 
                    iIndex = MarketData.loc[MarketData['symbol'] == symbol].index.item()
                    macd5m = float(MarketPriceFrames.loc[iIndex, '5m'])
                    macd15m = float(MarketPriceFrames.loc[iIndex, '15m'])
                    macd4h = float(MarketPriceFrames.loc[iIndex, '4h'])
                    macd1d = float(MarketPriceFrames.loc[iIndex, '1d'])

                    #Standard Strategy Calcs 
                    #using last Candle lowpx and highpx 
                    range = float(high_price - low_price)
                    potential = float((low_price / high_price) * 100)
                    buy_above = float(low_price * 1.00)
                    buy_below = float(high_price - (range * percent_below))
                    max_potential = float(potential * profit_max)
                    min_potential = float(potential * profit_min)
                                        
                    #using last Candle highpx and last trade price, if last trade nan then fall back to lowpx or AskPx
                    current_range = float(high_price - last_price)
                    current_potential = float((last_price / high_price) * 100)
                    current_buy_above = float(last_price * 1.00)
                    current_buy_below = float(high_price - (current_range * percent_below))
                    current_max_potential = float(current_potential * profit_max) 
                    current_min_potential = float(current_potential * profit_min)

                    if current_range == 0: 
                        #it is possible to have the samw High/low/last trade resulting in "Cannot divide by zero"
                        movement = 0
                    else:
                        movement = (low_price / current_range)   


                    macd1m = float(MarketData.loc[index, 'open'])  
                    BuyCoin = False
                    #-----------------------------------------------------------------
                    #Do your custom strategy calcs
                    if current_range == 0: 
                        #it is possible to have the samw current_range=0 resulting in "Cannot divide by zero"
                        current_drop = (100 * (current_range)) / high_price
                    else:
                        current_drop = 0

                    atr = []               # average true range
                    atr.append(high_price-low_price)
                    atr_percentage = ((sum(atr)/len(atr)) / close_price) * 100
                    #-----------------------------------------------------------------
                    #Do your strategy check here

                    RealTimeCheck = False
                    TimeFrameCheck = False 
                    TimeFrameOption = False

                    if DROP_CALCULATION:
                        current_potential = current_drop
                    
                    #Different MOVEMENT models 
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

                    #Custom logging output for the algo
                    if all_info:
                        print(f'{TextColors.DEFAULT}{symbol} RealTimecheck:{RealTimeCheck} Timeframecheck:{TimeFrameCheck} TimeFrameOption: {TimeFrameOption} \n')
                        print ("-------DEBUG--------")
                        print(f'\nCoin:            {symbol}\n'
                              f'CHECK1 True:       {(profit_min < current_potential < profit_max)} \n'
                              f'CHECK2 True:       {(last_price < buy_below)} \n'
                              f'Data 1 :           {profit_min} | {current_potential} | {profit_max} | {last_price} | {buy_below}  \n'
                              f'Data 2 :           {macd1m} | {macd5m} | {macd15m} | {macd1d} |  {get_histbtc} \n'
                              )

                    #Custom logging output for generic debug mode below
                    Custom_Fields = (
                                    "current_drop:        " + str(current_drop) + "\n" 
                                    "atr_percentage:      " + str(atr_percentage)  + "\n" 
                                    )

                    #-----------------------------------------------------------------
                    #Buy coin check
                    if BuyCoin:
                        CoinsBuyCounter += 1
                        # add to signal
                        with open(f'signals/snail_scan{signal_file_type}', 'a+') as f:
                            f.write(str(symbol) + '\n')
                            print(f'{TextColors.BUY}{str(datetime.now())}:{symbol} \n')


                    #-----------------------------------------------------------------
                    #Debug Output
                    #may chnage this to output to a file
                    if DEBUG:
                        print (f'{TextColors.DEFAULT}-------DEBUG--------')
                        print(f'\nCoin:            {symbol}\n'
                            f'Price:               ${last_price:.3f}\n'
                            f'Bid:                 ${bid_price:.3f}\n'
                            f'Ask:                 ${ask_price:.3f}\n'
                            f'High:                ${high_price:.3f}\n'
                            f'Low:                 ${low_price:.3f}\n'
                            f'Close:               ${close_price:.3f}\n'
                            f'----------------------------------------------\n'
                            f'Day Max Range:        ${range:.3f}\n'
                            f'Buy above:            ${buy_above:.3f}\n'
                            f'Buy Below:            ${buy_below:.3f}\n'
                            f'Potential profit:      {potential:.0f}%\n'
                            f'Potential max profit:  {max_potential:.0f}%\n'
                            f'Potential min profit:  {min_potential:.0f}%\n'
                            f'Buy above:            ${buy_above:.3f}\n'
                            f'Buy Below:            ${buy_below:.3f}\n'
                            f'----------------------------------------------\n'
                            f'Day Max Range (lstpx):    ${current_range:.3f}\n'
                            f'Potential profit(lstpx):  {current_potential:.0f}%\n'
                            f'Potential max profit:     {current_max_potential:.0f}%\n'
                            f'Potential min profit:     {current_min_potential:.0f}%\n'
                            f'Buy above (lstpx):        ${current_buy_above:.3f}\n'
                            f'Buy Below(lstpx):         ${current_buy_below:.3f}\n'
                            f'Movement:                 {movement:.2f}%\n'
                            f'----------------------------------------------\n'
                            f'{Custom_Fields}'
                            f'----------------------------------------------\n'
                            f'Last Update:               {datetime.now()}\n'
                            )
                        print (MarketData)            
                        print ("-------MACD--------")
                        print(f'\nCoin:           {symbol}\n'
                            f'macd1m:             {macd1m}\n'
                            f'macd5m:             {macd5m}\n'
                            f'macd15m:            {macd15m}\n'
                            f'macd4h:             {macd4h}\n'
                            f'macd1d:             {macd1d}\n'
                            )
                        print (MarketPriceFrames)            
                        print ("-------Bitcoin--------")
                        print (f"get_histbtc:   {get_histbtc}")

            
            if block_info:
                print(f'{str(datetime.now())}: Total Coins Scanned: {CoinsCounter} Skipped:{CoinsSkippedCounter} Reviewed:{CoinsCounter - (CoinsSkippedCounter + CoinsBuyCounter)} Bought:{CoinsBuyCounter}')

            time.sleep(3)
            
    except Exception as e:
        print(str(e))
        print("Error on line {}".format(sys.exc_info()[-1].tb_lineno))
        
        #only pushing data from dataframe to help debug 
        print(f'\nCoin:            {symbol}\n'
            f'Price:            ${last_price:.3f}\n'
            f'Bid:            ${bid_price:.3f}\n'
            f'Ask:            ${ask_price:.3f}\n'
            f'High:             ${high_price:.3f}\n'
            f'Low:             ${low_price:.3f}\n'
            f'Close:             ${close_price:.3f}\n'
            f'macd1m:             {macd1m}\n'
            f'macd5m:             {macd5m}\n'
            f'macd15m:            {macd15m}\n'
            f'macd4h:             {macd4h}\n'
            f'macd1d:             {macd1d}\n'
            )

        web_socket_app.close()
    except KeyboardInterrupt:
        web_socket_app.close()
