import requests
import json
import os
import time

SIGNAL_NAME = 'dragoncity'
SIGNAL_TYPE = 'pause'
#SIGNAL_TYPE = 'buy'
#SIGNAL_TYPE = 'sell'

def analyse_btc(symbol):

    
    #option 2: from ticker
    binance = "https://api.binance.com"
    avg_price = "/api/v1/ticker/24hr"
    response = requests.get(binance + avg_price + "?symbol=" + symbol)
    response_dict = json.loads(response.text)
    
    #print('calc from ticker=' + response_dict['priceChangePercent'])
    if float(response_dict['priceChangePercent']) <= -5.0: 
        a = True
    else: 
        a = False

    return a 

#Swap do_work and __main__
def do_work():
#if __name__ == '__main__':	
    symbol = "BTCUSDT"

    while True:
        result = analyse_btc(symbol)
        if result:
            with open(f'signals/{SIGNAL_NAME}.{SIGNAL_TYPE}', 'a+') as f:
                f.write(symbol)
            print(f"Bot {SIGNAL_TYPE} by " + SIGNAL_NAME)
        else:
            if os.path.isfile(f'signals/{SIGNAL_NAME}.{SIGNAL_TYPE}'):
                os.remove(f'signals/{SIGNAL_NAME}.{SIGNAL_TYPE}')
                print(f"Bot remove by " + SIGNAL_NAME)
        time.sleep(60)
