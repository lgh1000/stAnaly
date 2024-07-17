
# STILL HAVE TO CHANGE BEAUTIFUL SOUP TO SELENIUM.


import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output, State
app = dash.Dash(__name__)
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import datetime
from datetime import datetime, time, timedelta
import holidays
import requests
from requests.exceptions import RequestException
from bs4 import BeautifulSoup

import pandas_datareader as pdr
import threading
import multiprocessing

# import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')





#make sure only SMA 10, 20 in options plot

# Initialize Dash app
app = dash.Dash(__name__)

# List of options for time interval and timeframe
time_intervals = ['1m', '2m', '5m', '15m', '30m', '1h', '1d', '5d', '1wk', '1mo', '3mo']
timeframes = ['1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'max']
screener_data = []

# Layout of the app
app.layout = html.Div([
    html.H1('Real-Time Stock-Option Pair Dashboard', style={'textAlign': 'center'}),
    
    html.Div([
        html.Div([
            html.H2('Stock'),
            dcc.Input(id='stock-ticker-input', type='text', placeholder='Enter Stock Ticker Symbol (e.g., aapl)', style={'width': '50%'}),
            dcc.Dropdown(id='stock-timeframe-dropdown', options=[{'label': i, 'value': i} for i in timeframes], value='1d', placeholder='Select Timeframe', style={'width': '50%'}),
            dcc.Dropdown(id='stock-interval-dropdown', options=[{'label': i, 'value': i} for i in time_intervals], value='1m', placeholder='Select Interval', style={'width': '50%'}),
            html.Div(id='alerts-container'),
            dcc.Graph(id='stock-plot', style={'height': '70vh'}),
            # html.Div(id='stock-table-container', children=[
            #     html.H2('Stock Data Table'),
            #     dash_table.DataTable(
            #         id='stock-table',
            #         columns=[{"name": i, "id": i} for i in ['Date', 'Close', 'Volume']],
            #         data=[],
            #         style_table={'overflowX': 'scroll'},
            #         style_cell={'whiteSpace': 'normal'},
            #         style_data={'minWidth': '10%', 'maxWidth': '30%'}
            #     ),
            # ]),
            html.Div(id='stock-screener-container', children=[
                html.H2('Stock Screener'),
                dash_table.DataTable(
                    id='stock-screener-table',
                    columns=[
                        {"name": "Ticker", "id": "Ticker"},
                        {"name": "Close", "id": "Close"},
                        {"name": "Market Cap", "id": "Market Cap"},
                    ],
                    data=[],
                    style_table={'overflowX': 'scroll'},
                    style_cell={'whiteSpace': 'normal'},
                    style_data={'minWidth': '10%', 'maxWidth': '30%'},
                    row_selectable='single',  # Enable row selection
                ),
            ]),

            

        ], style={'width': '70%', 'display': 'inline-block', 'vertical-align': 'top'}),
        
        html.Div([
            html.H2('Option'),
            dcc.Input(id='option-ticker-input', type='text', placeholder='Enter Stock Ticker (e.g., aapl)', style={'width': '90%'}),
            dcc.Input(id='option-type-input', type='text', placeholder='Enter Option Type (c or p)', style={'width': '90%'}),
            dcc.Input(id='option-expiry-input', type='text', placeholder='Enter Expiry Date (YYYY-MM-DD)', style={'width': '90%'}),
            dcc.Input(id='option-strike-input', type='number', placeholder='Enter Strike Price', style={'width': '90%'}),
            dcc.Dropdown(id='option-timeframe-dropdown', options=[{'label': i, 'value': i} for i in timeframes], value='1d', placeholder='Select Timeframe', style={'width': '90%'}),
            dcc.Dropdown(id='option-interval-dropdown', options=[{'label': i, 'value': i} for i in time_intervals], value='1m', placeholder='Select Interval', style={'width': '90%'}),
            dcc.Graph(id='option-plot', style={'height': '65vh', 'width': '100%'}),
            html.Div(id='option-table-container', children=[
                html.H2('Option Data Table'),
                dash_table.DataTable(
                    id='option-table',
                    columns=[{"name": i, "id": i} for i in ['Date', 'Close', 'Volume']],
                    data=[],
                    style_table={'overflowX': 'scroll'},
                    style_cell={'minWidth': '0px', 'maxWidth': '180px', 'whiteSpace': 'normal'},
                ),
            ]),


        ], style={'width': '28%', 'display': 'inline-block', 'vertical-align': 'top'}),
    ]),
    
    dcc.Interval(
        id='interval-component',
        interval=60*1000,  # in milliseconds (default update every minute)
        n_intervals=0
    )
])


# def get_all_stock_tickers():
#     url = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=most_actives&count=100&start=0"
#     response = requests.get(url)
#     data = response.json()
#     tickers = [stock['symbol'] for stock in data['finance']['result'][0]['quotes'] if stock['marketCap'] > 100000000]
#     if len(tickers) > 0:
#         tickers.sort(key=lambda x: get_market_cap(x), reverse=True)
#         print("Debug: Number of tickers found", len(tickers))
#     else:
#         print("Debug: No tickers found.")
#     return tickers

# def get_all_stock_tickers():
#     url = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=most_actives&count=100&start=0"
#     max_retries = 5
#     retry_delay = 60  # Delay in seconds between retries

#     for retry in range(max_retries):
#         try:
#             response = requests.get(url)
#             response.raise_for_status()  # Raise an exception for non-2xx status codes
#             data = response.json()
#             tickers = [stock['symbol'] for stock in data['finance']['result'][0]['quotes'] if stock['marketCap'] > 100000000]
#             if len(tickers) > 0:
#                 tickers.sort(key=lambda x: get_market_cap(x), reverse=True)
#                 print("Debug: Number of tickers found", len(tickers))
#             else:
#                 print("Debug: No tickers found.")
#             return tickers
#         except RequestException as e:
#             if retry < max_retries - 1:
#                 print(f"Error fetching stock tickers: {e}. Retrying in {retry_delay} seconds...")
#                 time.sleep(retry_delay)
#             else:
#                 print(f"Error fetching stock tickers: {e}. Maximum retries exceeded.")
#                 return []
#         except (KeyError, IndexError, ValueError) as e:
#             print(f"Error parsing API response: {e}")
#             return []

# def fetch_tickers_process():
#     try:
#         # Freeze support for multiprocessing on Windows
#         multiprocessing.freeze_support()

#         url = "https://www.nasdaq.com/market-activity/stocks/screener"
#         response = requests.get(url)
#         soup = BeautifulSoup(response.text, "html.parser")

#         tickers = []
#         table = soup.find("table", {"class": "nasdaq-screener__table"})
#         if table:
#             rows = table.find_all("tr", {"class": "nasdaq-screener__row"})
#             for row in rows[1:]:  # Skip the header row
#                 symbol_cell = row.find("th", {"class": "nasdaq-screener__cell"})
#                 if symbol_cell:
#                     symbol = symbol_cell.find("a").text.strip()
#                     tickers.append(symbol)

#         return tickers
#     except Exception as e:
#         print(f"Error fetching tickers: {e}")
#         return []
def fetch_tickers_process():
    try:
        # Freeze support for multiprocessing on Windows
        multiprocessing.freeze_support()

        url = "https://www.nasdaq.com/market-activity/stocks/screener"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, "html.parser")

        # Print response text for debugging
        print(soup.prettify())

        tickers = []
        table = soup.find("table", {"class": "nasdaq-screener__table"})
        if table:
            rows = table.find_all("tr", {"class": "nasdaq-screener__row"})
            for row in rows:
                symbol_cell = row.find("th", {"scope": "row", "class": "nasdaq-screener__cell"})
                if symbol_cell:
                    symbol = symbol_cell.find("a", {"class": "firstCell"}).text.strip()
                    tickers.append(symbol)

        return tickers
    except Exception as e:
        print(f"Error fetching tickers: {e}")
        return []


# Test the function
tickers = fetch_tickers_process()
print(tickers)


def get_all_stock_tickers():
    if __name__ == '__main__':
        # Start the separate process to fetch tickers
        tickers_process = multiprocessing.Process(target=fetch_tickers_process)
        tickers_process.start()

    # Return an empty list initially
    return []



# def get_all_stock_tickers():
#     try:
#         tickers = pd.read_csv('ftp://ftp.nasdaqtrader.com/SymbolDirectory/nasdaqtraded.txt', sep='|', usecols=[0], header=None)
#          = tickers.squeeze()  # Converttickers Series to a one-dimensional array
#         tickers = tickers.str.upper()  # Convert tickers to uppercase
#         tickers = tickers.tolist()  # Convert to list
#         return tickers
#     except Exception as e:
#         print(f"Error fetching NASDAQ tickers: {e}")
#         return []

# def get_all_stock_tickers():
#     try:
#         tickers = yf.tickers_nasdaq()
#         return tickers
#     except Exception as e:
#         print(f"Error fetching NASDAQ tickers: {e}")
#         return []


def get_market_cap(ticker):
    stock = yf.Ticker(ticker)
    market_cap = stock.info.get("marketCap")
    return market_cap
# screener_data_cache = []

def get_stock_data(ticker, period='1y', interval='1d'):
    stock = yf.Ticker(ticker)
    stock_data = stock.history(period=period, interval=interval)
    return stock_data

# def get_stock_data(ticker, period='1y', interval='1d'):
#     end_date = pd.to_datetime('today')
    
#     if period == '1y':
#         start_date = end_date - timedelta(days=365)
#     elif period == '3mo':
#         start_date = end_date - timedelta(days=90)
#     elif period == '6mo':
#         start_date = end_date - timedelta(days=180)
#     else:
#         raise ValueError(f"Invalid period: {period}")
    
#     if interval == '1d':
#         interval = 'd'
#     elif interval == '1m':
#         interval = 'm'
    
#     stock_data = pdr.get_data_yahoo(ticker, start=start_date, end=end_date, interval=interval)
#     return stock_data

# def get_stock_data(ticker, period='1y', interval='1d'):
#     end_date = pd.to_datetime('today')
#     start_date = end_date - pd.Timedelta(period)
#     stock_data = pdr.get_data_yahoo(ticker, start=start_date, end=end_date, interval=interval)
#     return stock_data

def fetch_screener_data():
    global screener_data
    tickers = get_all_stock_tickers()
    screener_data = []
    logging.info(f"Fetched {len(tickers)} tickers from NASDAQ")
    skipped_tickers = []
    processed_tickers = []


    for ticker in tickers:
        if ticker == 'Y':
            logging.warning(f"Skipping ticker 'Y' due to known issue")
            skipped_tickers.append(ticker)
            continue

        try:
            stock_data = get_stock_data(ticker, '1y', '1d')
            if not stock_data.empty:
                stock_data['SMA_50'] = stock_data['Close'].rolling(window=50).mean()
                stock_data['SMA_20'] = stock_data['Close'].rolling(window=20).mean()
                stock_data['SMA_7'] = stock_data['Close'].rolling(window=7).mean()
                stock_data['HMA_6'] = ((2 * stock_data['Close'].rolling(window=3).mean() - stock_data['Close'].rolling(window=6).mean()).rolling(window=int(6**0.5)).mean())

                market_cap = get_market_cap(ticker)
                close = stock_data['Close'].iloc[-1]
                sma_50 = stock_data['SMA_50'].iloc[-1]
                sma_20 = stock_data['SMA_20'].iloc[-1]
                sma_7 = stock_data['SMA_7'].iloc[-1]
                hma_6 = stock_data['HMA_6'].iloc[-1]

                if (close > sma_50 and close > sma_20 and close > sma_7 and
                    hma_6 > sma_7 and
                    0.13 <= (close - sma_50) / sma_50 <= 0.20):
                    screener_data.append({'Ticker': ticker, 'Close': close, 'Market Cap': market_cap})
                    processed_tickers.append(ticker)
            else:
                logging.warning(f"No data found for ticker {ticker}")
        except Exception as e:
            logging.error(f"Error fetching data for ticker {ticker}: {e}")
            skipped_tickers.append(ticker)

    screener_data = sorted(screener_data, key=lambda x: x['Market Cap'], reverse=True)
    logging.info(f"Screener data updated with {len(screener_data)} tickers")
    logging.info(f"Skipped {len(skipped_tickers)} tickers due to errors: {', '.join(skipped_tickers)}")
    logging.info(f"Processed tickers: {', '.join(processed_tickers[:10])}")  # Log the first 10 processed tickers
    return screener_data

# update screener data asynchronously so that the restr of teh app still loads:
def update_screener_data():
    global screener_data
    # tickers = get_all_stock_tickers()
    screener_data = fetch_screener_data()

# Get all stock tickers and fetch screener data on app start

tickers = get_all_stock_tickers()
screener_data_thread = threading.Thread(target=update_screener_data)
screener_data_thread.start()

def is_market_open():
    current_time = datetime.now()
    market_open_time = time(9, 30) # Market opens at 9:30 AM
    market_close_time = time(16, 0) # Market closes at 4:00 PM
    
    us_holidays = holidays.US()# Initialize US holidays
    
    if current_time.date() in us_holidays:
        return False
    if current_time.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
        return False
    if market_open_time <= current_time.time() <= market_close_time:
        return True
    return False


# def get_stock_data(ticker, timeframe, interval):
#     stock = yf.Ticker(ticker)
    
#     if timeframe == '1y':
#         start_date = datetime.datetime.now() - datetime.timedelta(days=365)
#     else:
#         start_date = datetime.datetime.now() - pd.Timedelta(timeframe)
    
#     end_date = datetime.datetime.now()
    
#     stock_data = stock.history(start=start_date.strftime('%Y-%m-%d'), end=end_date.strftime('%Y-%m-%d'), interval=interval, actions=False)
#     return stock_data

# def get_stock_data(ticker, timeframe='1d', interval='1m'):
#     stock = yf.Ticker(ticker)
    
#     # if timeframe == '1y':
#     #     start_date = datetime.datetime.now() - datetime.timedelta(days=365)
#     # else:
#     #     start_date = datetime.datetime.now() - pd.Timedelta(timeframe)
    
#     # end_date = datetime.datetime.now()
    
#     stock_data = stock.history(timeframe=timeframe, interval=interval)
#     return stock_data

# def get_stock_data(ticker, period='3mo', interval='1d'):
#     stock = yf.Ticker(ticker)
#     stock_data = stock.history(period=period, interval=interval)
#     return stock_data



def get_option_data(ticker, option_type, expiry, strike, timeframe='1d', interval='1m'):
    stock = yf.Ticker(ticker)
    option_chain = stock.option_chain(expiry)
    
    if option_type.lower() == 'c':
        options = option_chain.calls
    elif option_type.lower() == 'p':
        options = option_chain.puts
    else:
        raise ValueError("Option type must be 'c' for call or 'p' for put")
    
    option = options[options['strike'] == strike].iloc[0]
    option_symbol = option['contractSymbol']
    option_data = yf.Ticker(option_symbol).history(period=timeframe, interval=interval, actions=False)
    
    # # If the market is closed, get the last available data point
    # if option_data.empty or option_data.index[-1].date() != datetime.now().date():
    #     option_data = yf.Ticker(option_symbol).history(start=(datetime.now() - pd.Timedelta(timeframe)).strftime('%Y-%m-%d'), end=datetime.now().strftime('%Y-%m-%d'), interval=interval, actions=False)

    return option_data


def prepare_table_data(data):
    table_data = []
    if not data.empty:
        for idx, row in data.iterrows():
            table_data.append({
                'Date': idx.strftime('%Y-%m-%d %H:%M:%S'),
                'Close': row['Close'],
                'Volume': row['Volume']
            })
            # Sort by most recent first
    table_data.sort(key=lambda x: x['Date'], reverse=True)
    return table_data
def plot_data(data, title, is_option=False):
    fig = go.Figure()
    if 'Close' in data.columns:
        if len(data) > 0:  # Check if data is not empty
            color = 'green' if data['Close'].iloc[-1] >= data['Close'].iloc[0] else 'red'
            fig.add_trace(go.Scatter(x=data.index, y=data['Close'], mode='lines+markers', line=dict(color=color), name='Close'))

            # Adding simple moving averages (SMAs)
            data['SMA_10'] = data['Close'].rolling(window=10).mean()
            data['SMA_20'] = data['Close'].rolling(window=20).mean()

            if not is_option:  # For stock plot
                data['SMA_7'] = data['Close'].rolling(window=7).mean()
                data['SMA_50'] = data['Close'].rolling(window=50).mean()

                fig.add_trace(go.Scatter(x=data.index, y=data['SMA_7'], mode='lines', line=dict(color='blue'), name='SMA 7'))
                fig.add_trace(go.Scatter(x=data.index, y=data['SMA_50'], mode='lines', line=dict(color='purple'), name='SMA 50'))

            fig.add_trace(go.Scatter(x=data.index, y=data['SMA_10'], mode='lines', line=dict(color='pink'), name='SMA 10'))
            fig.add_trace(go.Scatter(x=data.index, y=data['SMA_20'], mode='lines', line=dict(color='black'), name='SMA 20'))

            if not is_option:  # For stock plot
                # Calculate Hull Moving Average (HMA)
                wma_half = data['Close'].rolling(window=3).mean()
                wma_full = data['Close'].rolling(window=6).mean()
                hma = (2 * wma_half - wma_full).rolling(window=int(6**0.5)).mean()
                data['HMA_6'] = hma

                fig.add_trace(go.Scatter(x=data.index, y=data['HMA_6'], mode='lines', line=dict(color='orange'), name='HMA 6'))
        else:
            print("Debug: Data is empty.")
    else:
        return go.Figure()  # Return empty figure if 'Close' column is not present

    fig.update_layout(
        title=f'{title} Prices',
        xaxis_title='Time',
        yaxis_title='Price',
        # legend_title='Price Type'
    )
    
    return fig


@app.callback(
    Output('stock-interval-dropdown', 'options'),
    Output('option-interval-dropdown', 'options'),
    Input('stock-timeframe-dropdown', 'value'),
    Input('option-timeframe-dropdown', 'value'),
)
def update_intervals(stock_timeframe, option_timeframe):
    interval_options = {
        '1d': [{'label': i, 'value': i} for i in ['1m', '2m', '5m', '15m', '30m', '1h', '1d']],
        '5d': [{'label': i, 'value': i} for i in ['1m', '2m', '5m', '15m', '30m', '1h', '1d', '5d']],
        '1mo': [{'label': i, 'value': i} for i in ['2m', '5m', '15m', '30m', '1h', '1d', '5d', '1mo']],
        '3mo': [{'label': i, 'value': i} for i in ['1h', '1d', '5d', '1mo', '3mo']],
        '6mo': [{'label': i, 'value': i} for i in ['1d', '5d', '1mo', '3mo']],
        '1y': [{'label': i, 'value': i} for i in ['1d', '5d', '1mo', '3mo']],
        '2y': [{'label': i, 'value': i} for i in ['1d', '5d', '1mo', '3mo']],
        '5y': [{'label': i, 'value': i} for i in ['1d', '5d', '1mo', '3mo']],
        '10y': [{'label': i, 'value': i} for i in ['1d', '5d', '1mo', '3mo']],
        'max': [{'label': i, 'value': i} for i in ['1d', '5d', '1mo', '3mo']],
    }
    
    stock_intervals = interval_options.get(stock_timeframe, [])
    option_intervals = interval_options.get(option_timeframe, [])
    
    return stock_intervals, option_intervals

    # Fetch all stock tickers from Yahoo Finance


    #     stock = yf.Ticker(ticker)
    #     data = stock.history(period='1d')
    #     if not data.empty:
    #         close_price = data['Close'].iloc[-1]
    #         market_cap = stock.info.get('marketCap', 'N/A')
    #         if market_cap and market_cap > 100000000:  # Ensure market cap is over $100 million
    #             screener_data_cache.append({
    #                 'Ticker': ticker,
    #                 'Close': close_price,
    #                 'Market Cap': market_cap
    #             })
    # screener_data_cache.sort(key=lambda x: x['Market Cap'], reverse=True)

# Define a function to fetch market cap

# # Screen stocks based on criteria (e.g., close price, volume, market cap)
# def screen_stocks(tickers):
#     screened_stocks = []
#     for ticker in tickers:
#         stock = yf.Ticker(ticker)
#         data = stock.history(period='1d')
#         if not data.empty:
#             close_price = data['Close'].iloc[-1]
#             volume = data['Volume'].iloc[-1]
#             market_cap = stock.info.get('marketCap', 'N/A')
#             screened_stocks.append({
#                 'Ticker': ticker,
#                 'Close': close_price,
#                 'Volume': volume,
#                 'Market Cap': market_cap
#             })
#     return screened_stocks

@app.callback(
    Output('stock-plot', 'figure'),
    Output('stock-screener-table', 'data'),
    Output('option-plot', 'figure'),
    Output('option-table', 'data'),
    Output('alerts-container', 'children'),
    Output('interval-component', 'interval'),

    Input('interval-component', 'n_intervals'),
    Input('stock-ticker-input', 'value'),
    Input('stock-timeframe-dropdown', 'value'),
    Input('stock-interval-dropdown', 'value'),
    Input('option-ticker-input', 'value'),
    Input('option-type-input', 'value'),
    Input('option-expiry-input', 'value'),
    Input('option-strike-input', 'value'),
    Input('option-timeframe-dropdown', 'value'),
    Input('option-interval-dropdown', 'value'),
    Input('stock-screener-table', 'selected_rows'),
    State('stock-screener-table', 'data'),
)



def update_data_and_plot(n_intervals,
                         stock_ticker, stock_timeframe, stock_interval,
                         option_ticker, option_type, option_expiry, option_strike,
                           option_timeframe, option_interval, selected_rows, screener_data):
    
    ctx = dash.callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
    # If screener_data is empty, start the separate process to fetch tickers
    if not screener_data:
        get_all_stock_tickers()

    # Initialize outputs
    stock_fig = go.Figure()
    # stock_table_data = []
    option_fig = go.Figure()
    option_table_data = []
    alerts = []  # Initialize alerts list
    # screener_data = []  # Data for stock screener

    
    # Set default intervals
    default_intervals = {
        '1d': '1m',
        '5d': '1h',
        '1mo': '1d',
        '3mo': '1d',
        '6mo': '1d',
        '1y': '1d',
        '2y': '1d',
        '5y': '1d',
        '10y': '1d',
        'max': '1d'
    }
    
    # Set default intervals if None
    stock_interval = stock_interval or default_intervals.get(stock_timeframe)
    option_interval = option_interval or default_intervals.get(option_timeframe)
    
   
   # Determine if the market is open
    market_open = is_market_open()
    
    # Set interval based on market status  tp prevent more frequent (unnecessary) callback triggers.
    if market_open:
        update_interval = 60000  # 1 minute interval when market is open
    else:
        update_interval = 259200000  # 3 day interval when market is closed
    
    # # Update screener data once a day at market close
    # if triggered_id == 'interval-component' and not market_open and n_intervals % (24 * 60) == 0:
    #     tickers = get_all_stock_tickers()
    #     screener_data = fetch_screener_data(tickers)

    #     if stock_ticker:
    #         stock_data = get_stock_data(stock_ticker, stock_timeframe, stock_interval)
    #         stock_data['SMA_50'] = stock_data['Close'].rolling(window=50).mean()  # Ensure SMA_50 is calculated
    #         stock_data['SMA_20'] = stock_data['Close'].rolling(window=20).mean()
    #         stock_data['SMA_7'] = stock_data['Close'].rolling(window=7).mean()
    #         stock_data['HMA_6'] = ((2 * stock_data['Close'].rolling(window=3).mean() - stock_data['Close'].rolling(window=6).mean()).rolling(window=int(6**0.5)).mean())

    #         stock_fig = plot_data(stock_data, 'Stock')

    #         if not stock_data.empty:
    #             close = stock_data['Close'].iloc[-1]
    #             sma_20 = stock_data['SMA_20'].iloc[-1]
    #             sma_7 = stock_data['SMA_7'].iloc[-1]
    #             hma_6 = stock_data['HMA_6'].iloc[-1]
                

    #             # Add alerts based on conditions
    #             if close < sma_20:
    #                 alerts.append(html.Div('Sell Bear Alert: Close below SMA 20', style={'color': 'red'}))
    #             if close < sma_7:
    #                 alerts.append(html.Div('Bear Alert: Close below SMA 7', style={'color': 'red'}))
    #             if hma_6 < sma_7:
    #                 alerts.append(html.Div('Short Term Bear Alert: HMA 6 below SMA 7', style={'color': 'red'}))
    #             if close > sma_20:
    #                 alerts.append(html.Div('Buy Bull Alert: Close above SMA 20', style={'color': 'green'}))
    #             if close > sma_7:
    #                 alerts.append(html.Div('Bull Alert: Close above SMA 7', style={'color': 'green'}))
    #             if hma_6 > sma_7:
    #                 alerts.append(html.Div('Short Term Bull Alert: HMA 6 above SMA 7', style={'color': 'green'}))
    #             if not market_open:
    #                 alerts.append(html.Div('Market closed - not updating', style={'color': 'orange'}))

    #     if option_ticker and option_type and option_expiry and option_strike:
    #         option_data = get_option_data(option_ticker, option_type, option_expiry, option_strike, option_timeframe, option_interval)
    #         if not option_data.empty:
    #             option_table_data = prepare_table_data(option_data)
    #             option_fig = plot_data(option_data, 'Option', is_option=True)
    #         else:
    #             print(f"Debug: Option data for {option_ticker} option is empty or has no 'Close' column.")
    #     # # Update stock screener
    #     # all_tickers = get_all_stock_tickers()
    #     # stock_screener_data = screen_stocks(all_tickers)


    # # Handle row selection in stock screener
    # if selected_rows is not None and screener_data:
    #     selected_ticker = screener_data[selected_rows[0]]['Ticker']
    #     stock_ticker = selected_ticker
    #     stock_timeframe = '1y'
    #     stock_interval = '1d'

    #     # Ensure alerts is not empty even if there are no alerts
    # alerts_content = html.Div(alerts) if alerts else []
    
    # return stock_fig, screener_data, option_fig, option_table_data, alerts, update_interval

    # Only update data if user input changed or if market is open and interval update triggered
    if triggered_id != 'interval-component' or (triggered_id == 'interval-component' and market_open):
        
    
    
        if stock_ticker:
            stock_data = get_stock_data(stock_ticker, stock_timeframe, stock_interval)
            stock_data['SMA_50'] = stock_data['Close'].rolling(window=50).mean()  # Ensure SMA_50 is calculated
            stock_data['SMA_20'] = stock_data['Close'].rolling(window=20).mean()
            stock_data['SMA_7'] = stock_data['Close'].rolling(window=7).mean()
            stock_data['HMA_6'] = ((2 * stock_data['Close'].rolling(window=3).mean() - stock_data['Close'].rolling(window=6).mean()).rolling(window=int(6**0.5)).mean())

            stock_fig = plot_data(stock_data, 'Stock')
            # stock_table_data = prepare_table_data(stock_data)
            
            if not stock_data.empty:
                close = stock_data['Close'].iloc[-1]
                sma_20 = stock_data['SMA_20'].iloc[-1]
                sma_7 = stock_data['SMA_7'].iloc[-1]
                hma_6 = stock_data['HMA_6'].iloc[-1]
                

                # Add alerts based on conditions
                if close < sma_20:
                    alerts.append(html.Div('Sell Bear Alert: Close below SMA 20', style={'color': 'red'}))
                if close < sma_7:
                    alerts.append(html.Div('Bear Alert: Close below SMA 7', style={'color': 'red'}))
                if hma_6 < sma_7:
                    alerts.append(html.Div('Short Term Bear Alert: HMA 6 below SMA 7', style={'color': 'red'}))
                if close > sma_20:
                    alerts.append(html.Div('Buy Bull Alert: Close above SMA 20', style={'color': 'green'}))
                if close > sma_7:
                    alerts.append(html.Div('Bull Alert: Close above SMA 7', style={'color': 'green'}))
                if hma_6 > sma_7:
                    alerts.append(html.Div('Short Term Bull Alert: HMA 6 above SMA 7', style={'color': 'green'}))
                if not market_open:
                    alerts.append(html.Div('Market closed - not updating', style={'color': 'orange'}))

        if option_ticker and option_type and option_expiry and option_strike:
            option_data = get_option_data(option_ticker, option_type, option_expiry, option_strike, option_timeframe, option_interval)
            if not option_data.empty:
                option_table_data = prepare_table_data(option_data)
                option_fig = plot_data(option_data, 'Option', is_option=True)
            else:
                print(f"Debug: Option data for {option_ticker} option is empty or has no 'Close' column.")
        # # Update stock screener
        # all_tickers = get_all_stock_tickers()
        # stock_screener_data = screen_stocks(all_tickers)

    # Ensure alerts is not empty even if there are no alerts
    alerts_content = html.Div(alerts) if alerts else []

    


    return stock_fig, list(screener_data), option_fig, option_table_data, alerts_content, update_interval

# Run the Dash app
if __name__ == '__main__':
    app.run_server(debug=True)
else:
    server = app.server
