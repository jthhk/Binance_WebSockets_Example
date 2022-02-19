
import ccxt
import pandas as pd
import time
import datetime
from datetime import datetime

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view


symbol = 'ETH/BTC'
exchange = ccxt.binance()
timeframes = ['5m']
list_of_coins = {}

for item in timeframes:	
    data  = exchange.fetch_ohlcv(symbol, timeframe=item, limit=50)
    df1  = pd.DataFrame(data , columns=['time', 'open', 'high', 'low', 'close', 'volume'])
    df1['time'] = pd.to_datetime(df1['time'],unit='ms')
    df1.set_index('time', inplace=True)
    list_of_coins[symbol + '_' + item] = df1
    #print(df1)


    #Add Row
    epoch_time = 1643382176000 / 1000.0
    #time1 = datetime.fromtimestamp(epoch_time).strftime('%Y-%m-%d %H:%M:%S')
    time1 = datetime.utcfromtimestamp(epoch_time)
    df2 = [ 0.888888,  0.888888,  0.888888,  0.888888,   86.888888]
    df1.loc[time1] = df2
    print(df1)

    #Calc TA
    df1 = df1.tail(10)
    print(df1)

    #Resample
    df3 = df1.resample('10T').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'})
    print(df3)

    
                            """
                            Used to check the TA numbers vs my sliding window
                            timeframe = calc_item
                            timeframe= timeframe.replace("T","m")
                            macd1 = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=36)
                            df1 = pd.DataFrame(macd1, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
                            macd1 = df1.ta.macd(fast=12, slow=26)
                            get_hist1 = macd1.iloc[35, 1]
                        
                            if (get_hist1 - get_macd) > 1:
                                print( str(symbol) + " problem:" + str(get_hist1) + " from fetch_ohlcv " + str(timeframe) + " !=" + str(get_macd) + " from Jim Dataframe " + str(calc_item))
                                f = open("historyTA.txt", "a")
                                f.write( str(symbol) + " problem:" + str(get_hist1) + " from fetch_ohlcv " + str(timeframe) + " !=" + str(get_macd) + " from Jim Dataframe " + str(calc_item))
                                f.write("\n")
                                f.close()
                        """                        

