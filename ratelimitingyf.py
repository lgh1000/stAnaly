# Enhanced version with strict rate limiting and consistent UI
import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output, State
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, time, timedelta
import holidays
import os
import logging
import yfinance as yf
import time as time_module
import traceback
import random
from functools import lru_cache
import requests
from fake_useragent import UserAgent  # For better user agent rotation
import backoff  # For exponential backoff

# Configure logging to see detailed errors
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

# Initialize Dash app
app = dash.Dash(__name__)
server = app.server  # Important for Render deployment

# List of options for time interval and timeframe
time_intervals = ['1m', '2m', '5m', '15m', '30m', '1h', '1d', '5d', '1wk', '1mo', '3mo']
timeframes = ['1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'max']

# Cache for storing API responses to minimize requests
data_cache = {}
CACHE_DURATION = 3600  # Cache duration: 1 hour
# Track the last used ticker
last_used_ticker = ""
# --- ENHANCED RATE LIMITING ---

# Generate a dynamic list of user agents
try:
    ua = UserAgent()
    USER_AGENTS = [ua.chrome for _ in range(5)] + [ua.firefox for _ in range(5)] + [ua.safari for _ in range(5)]
except Exception as e:
    # Fallback user agents if fake_useragent fails
    logging.warning(f"Failed to initialize UserAgent: {e}. Using fallback user agents.")
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
        # Add more diverse user agents
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 12_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.2 Safari/605.1.15',
        'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:97.0) Gecko/20100101 Firefox/97.0',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 15_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.3 Mobile/15E148 Safari/604.1'
    ]

# Track the timestamp of the last successful request globally
# This makes sure even different ticker requests respect the same delay
last_request_time = 0

# --- ENHANCED SESSION MANAGEMENT ---
# Store sessions for reuse to maintain cookies
sessions = {}

def get_session(use_new=False):
    """Get a session with random user agent and optional proxy"""
    global sessions
    
    # Create a new session if requested or if no sessions exist
    if use_new or not sessions:
        user_agent = random.choice(USER_AGENTS)
        session = requests.Session()
        
        # Set headers to appear more like a normal browser
        session.headers.update({
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'DNT': '1',  # Do Not Track
            'Cache-Control': 'max-age=0'
        })
        
        # Store the session with its user agent as key
        sessions[user_agent] = session
        return session
    
    # Return a random existing session
    return random.choice(list(sessions.values()))

def normalize_ticker(ticker):
    """Convert ticker to uppercase and strip any whitespace"""
    if ticker:
        return ticker.strip().upper()
    return ticker

# --- ENHANCED RATE LIMITING ---
def rate_limit_request(is_new_ticker=False):
    """
    Apply rate limiting with different rules for new tickers vs. refreshes
    Returns True if a request is allowed, False if it should be blocked
    """
    global last_request_time
    
    current_time = time_module.time()
    elapsed = current_time - last_request_time
    
    # If this is a new ticker, use a shorter interval (6 seconds)
    # This allows up to 10 API calls per minute for new tickers
    if is_new_ticker:
        min_interval = 6.0 + random.uniform(0, 2.0)
    else:
        # Regular refresh interval (60-70 seconds)
        min_interval = 60.0 + random.uniform(0, 10.0)
    
    # Check if enough time has passed since the last request
    if elapsed < min_interval:
        logging.warning(f"Rate limit enforced: Only {elapsed:.1f}s elapsed since last request. "
                      f"Must wait {min_interval - elapsed:.1f}s more."
                      f" ({'New ticker' if is_new_ticker else 'Refresh'})")
        return False
    
    # Update last request time
    last_request_time = current_time
    logging.info(f"Request allowed after {elapsed:.1f}s. Next request will wait ~{min_interval:.1f}s")
    return True
# def rate_limit_request():
#     """
#     Apply strict rate limiting with random delays between 60-70 seconds
#     Returns True if a request is allowed, False if it should be blocked
#     """
#     global last_request_time
    
#     current_time = time_module.time()
#     elapsed = current_time - last_request_time
    
#     # Minimum wait time is 60 seconds plus a random amount (0-10 seconds)
#     min_interval = 60.0 + random.uniform(0, 10.0)
    
#     # Check if at least min_interval seconds have passed since the last request
#     if elapsed < min_interval:
#         logging.warning(f"Rate limit enforced: Only {elapsed:.1f}s elapsed since last request. "
#                         f"Must wait {min_interval - elapsed:.1f}s more.")
#         return False
    
#     # Update last request time
#     last_request_time = current_time
#     logging.info(f"Request allowed after {elapsed:.1f}s. Next request will wait ~{min_interval:.1f}s")
#     return True

def get_cache_key(func_name, *args):
    """Generate a cache key based on function name and arguments"""
    return f"{func_name}:{':'.join(str(arg) for arg in args)}"

def get_cached_data(cache_key):
    """Get data from cache if it exists and is not expired"""
    if cache_key in data_cache:
        data, timestamp = data_cache[cache_key]
        if datetime.now().timestamp() - timestamp < CACHE_DURATION:
            return data
    return None

def set_cached_data(cache_key, data):
    """Store data in cache with current timestamp"""
    data_cache[cache_key] = (data, datetime.now().timestamp())

def is_market_open():
    """Check if the US stock market is currently open"""
    current_time = datetime.now()
    market_open_time = time(9, 30)  # Market opens at 9:30 AM ET
    market_close_time = time(16, 0)  # Market closes at 4:00 PM ET
    
    us_holidays = holidays.US()  # Initialize US holidays
    
    if current_time.date() in us_holidays:
        return False
    if current_time.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
        return False
    if market_open_time <= current_time.time() <= market_close_time:
        return True
    return False

# --- ENHANCED STOCK DATA FUNCTION ---
@lru_cache(maxsize=64)
# --- MODIFIED STOCK DATA FUNCTION ---
# def get_stock_data(ticker, period='1d', interval='5m', retry_count=0):
#     """
#     Get stock data with strict rate limiting
#     """
#     if not ticker:
#         return pd.DataFrame()
        
#     cache_key = f"stock_data:{ticker}:{period}:{interval}"
#     cached_data = get_cached_data(cache_key)
#     if cached_data is not None:
#         logging.info(f"Using cached data for {ticker} {period} {interval}")
#         return cached_data
    
#     # Check if we're allowed to make a request (respects global rate limit)
#     if not rate_limit_request():
#         # Return empty DataFrame with message logged
#         logging.warning("Rate limit enforced - returning empty data")
#         return pd.DataFrame()
    
#     # Maximum number of retries
#     max_retries = 3
    
#     try:
#         logging.info(f"Fetching stock data for {ticker} with period={period}, interval={interval}")
        
#         # Get a session (new session on retry)
#         session = get_session(use_new=(retry_count > 0))
        
#         try:
#             # Fetch the stock data
#             stock = yf.Ticker(ticker, session=session)
#             stock_data = stock.history(period=period, interval=interval)
            
#             # Cache and return the data if not empty
#             if not stock_data.empty:
#                 set_cached_data(cache_key, stock_data)
#                 return stock_data
#             else:
#                 logging.warning(f"Empty data returned for {ticker}")
                
#                 # If we've exhausted retries, return empty DataFrame
#                 if retry_count >= max_retries:
#                     return pd.DataFrame()
                
#                 # Wait before retry (with exponential backoff)
#                 wait_time = 2 ** retry_count
#                 logging.info(f"Waiting {wait_time}s before retry {retry_count+1}/{max_retries}")
#                 time_module.sleep(wait_time)
                
#                 # Instead of recursive calls, set up fallback parameters to try in next iteration
#                 # *** THE KEY CHANGE: Remove recursive calls and use a fallback mechanism ***
#                 if interval in ['1m', '2m', '5m']:
#                     logging.warning(f"Next attempt will use less granular interval: 15m")
#                     return pd.DataFrame()  # Return empty now, next attempt will use different params
#                 elif period == '1d':
#                     logging.warning(f"Next attempt will use longer period: 5d")
#                     return pd.DataFrame()  # Return empty now, next attempt will use different params
#                 else:
#                     logging.warning(f"Next attempt will use daily data")
#                     return pd.DataFrame()  # Return empty now, next attempt will use different params
                
#         except Exception as e:
#             logging.error(f"Error fetching data for {ticker}: {str(e)}")
#             return pd.DataFrame()
            
#     except Exception as e:
#         logging.error(f"Unhandled error for {ticker}: {str(e)}")
#         logging.error(traceback.format_exc())
#         return pd.DataFrame()
def get_stock_data(ticker, period='1d', interval='5m', retry_count=0, is_new_ticker=False):
    """
    Get stock data with strict rate limiting
    """
    if not ticker:
        return pd.DataFrame()
        
    cache_key = f"stock_data:{ticker}:{period}:{interval}"
    cached_data = get_cached_data(cache_key)
    if cached_data is not None:
        logging.info(f"Using cached data for {ticker} {period} {interval}")
        return cached_data
    
    # Check if we're allowed to make a request (respects global rate limit)
    if not rate_limit_request(is_new_ticker):
        # Return empty DataFrame with message logged
        logging.warning("Rate limit enforced - returning empty data")
        return pd.DataFrame()
    
    # Maximum number of retries
    max_retries = 3
    
    try:
        logging.info(f"Fetching stock data for {ticker} with period={period}, interval={interval}")
        
        # Get a session (new session on retry)
        session = get_session(use_new=(retry_count > 0))
        
        try:
            # Fetch the stock data
            stock = yf.Ticker(ticker, session=session)
            stock_data = stock.history(period=period, interval=interval)
            
            # Cache and return the data if not empty
            if not stock_data.empty:
                set_cached_data(cache_key, stock_data)
                return stock_data
            else:
                logging.warning(f"Empty data returned for {ticker}")
                
                # If we've exhausted retries, return empty DataFrame
                if retry_count >= max_retries:
                    return pd.DataFrame()
                
                # Wait before retry (with exponential backoff)
                wait_time = 2 ** retry_count
                logging.info(f"Waiting {wait_time}s before retry {retry_count+1}/{max_retries}")
                time_module.sleep(wait_time)
                
                # # Try with different parameters based on the error
                # if interval in ['1m', '2m', '5m']:
                #     logging.warning(f"Retrying with less granular interval: 15m")
                #     return get_stock_data(ticker, period, '15m', retry_count + 1)
                # elif period == '1d':
                #     logging.warning(f"Retrying with longer period: 5d")
                #     return get_stock_data(ticker, '5d', interval, retry_count + 1)
                # else:
                #     logging.warning(f"Falling back to daily data")
                #     return get_stock_data(ticker, '1mo', '1d', retry_count + 1)
                # Log what parameters might work, but DON'T make recursive API calls
                logging.warning(f"Empty data returned for {ticker} - returning empty DataFrame")
                return pd.DataFrame()

        except Exception as e:
            logging.error(f"Error fetching data for {ticker}: {str(e)}")
            return pd.DataFrame()
            
    except Exception as e:
        logging.error(f"Unhandled error for {ticker}: {str(e)}")
        logging.error(traceback.format_exc())
        return pd.DataFrame()

# --- OPTION FUNCTIONS ---
def get_option_expirations(ticker):
    """
    Get option expiration dates with rate limiting
    """
    if not ticker:
        return []

    cache_key = f"option_expirations:{ticker}"
    cached_data = get_cached_data(cache_key)
    if cached_data is not None:
        logging.info(f"Using cached option expirations for {ticker}")
        return cached_data
    
    # Check if we're allowed to make a request
    if not rate_limit_request():
        logging.warning("Rate limit enforced - returning empty option expirations")
        return []
    
    try:
        stock = yf.Ticker(ticker)
        expirations = stock.options
        
        if expirations:
            set_cached_data(cache_key, expirations)
            return expirations
        return []
        
    except Exception as e:
        logging.error(f"Error getting option expirations for {ticker}: {str(e)}")
        return []

def get_option_chain(ticker, expiry):
    """
    Get option chain data with rate limiting
    """
    if not ticker or not expiry:
        return None

    cache_key = f"option_chain:{ticker}:{expiry}"
    cached_data = get_cached_data(cache_key)
    if cached_data is not None:
        logging.info(f"Using cached option chain for {ticker} {expiry}")
        return cached_data
    
    # Check if we're allowed to make a request
    if not rate_limit_request():
        logging.warning("Rate limit enforced - returning empty option chain")
        return None
    
    try:
        stock = yf.Ticker(ticker)
        option_chain = stock.option_chain(expiry)
        
        if option_chain:
            set_cached_data(cache_key, option_chain)
            return option_chain
        return None
        
    except Exception as e:
        logging.error(f"Error getting option chain for {ticker} {expiry}: {str(e)}")
        return None

def get_option_data(ticker, option_type, expiry=None, strike=None, period='1d', interval='5m'):
    """
    Get option data with rate limiting
    """
    if not ticker or not option_type:
        return pd.DataFrame()
        
    cache_key = f"option_data:{ticker}:{option_type}:{expiry}:{strike}:{period}:{interval}"
    cached_data = get_cached_data(cache_key)
    if cached_data is not None:
        logging.info(f"Using cached option data")
        return cached_data
    
    # If no expiry provided, get the nearest expiration date
    if not expiry:
        expirations = get_option_expirations(ticker)
        if not expirations:
            logging.warning(f"No option expiration dates found for {ticker}")
            return pd.DataFrame()
        
        # Sort and get the nearest expiration
        expiry = expirations[0]
        logging.info(f"Using nearest expiry date: {expiry}")
    
    # Get option chain
    option_chain = get_option_chain(ticker, expiry)
    if not option_chain:
        logging.warning(f"No option chain available for {ticker} {expiry}")
        return pd.DataFrame()
    
    # Select calls or puts
    if option_type.lower() in ['c', 'call', 'calls']:
        options = option_chain.calls
    else:
        options = option_chain.puts
    
    # If no options found
    if options.empty:
        logging.warning(f"No {option_type} options found for {ticker} with expiry {expiry}")
        return pd.DataFrame()
    
    # If no strike specified, find ATM option
    if not strike:
        # Get current stock price
        stock_data = get_stock_data(ticker, '1d', '15m')
        if not stock_data.empty and 'Close' in stock_data.columns:
            current_price = stock_data['Close'].iloc[-1]
            
            # Find closest strike to current price
            options['diff'] = abs(options['strike'] - current_price)
            closest_option = options.loc[options['diff'].idxmin()]
            strike = closest_option['strike']
            logging.info(f"Using closest strike to current price: {strike}")
        else:
            # If we can't get current price, use the middle strike
            strike = options['strike'].median()
            logging.info(f"Using middle strike: {strike}")
    
    # Filter by strike if provided
    try:
        strike_float = float(strike)
        option = options[options['strike'] == strike_float]
        
        if option.empty:
            options['diff'] = abs(options['strike'] - strike_float)
            closest_option = options.loc[options['diff'].idxmin()]
            strike = closest_option['strike']
            option = options[options['strike'] == strike]
            logging.info(f"Using closest available strike: {strike}")
    except (ValueError, TypeError):
        logging.warning(f"Invalid strike price: {strike}")
        return pd.DataFrame()
    
    if option.empty:
        logging.warning(f"No matching options found")
        return pd.DataFrame()
    
    # Get the option symbol
    option_symbol = option['contractSymbol'].iloc[0]
    
    # Check if we're allowed to make a request
    if not rate_limit_request():
        logging.warning("Rate limit enforced - returning empty option data")
        return pd.DataFrame()
    
    try:
        # Get option price history
        option_data = yf.Ticker(option_symbol).history(period=period, interval=interval)
        
        # If we have data, cache and return it
        if not option_data.empty:
            set_cached_data(cache_key, option_data)
            return option_data
        else:
            logging.warning(f"No option data available for {option_symbol}")
            return pd.DataFrame()
            
    except Exception as e:
        logging.error(f"Error getting option data for {option_symbol}: {str(e)}")
        return pd.DataFrame()

def prepare_table_data(data):
    """Format data for the Dash DataTable"""
    table_data = []
    if not data.empty and 'Close' in data.columns:
        for idx, row in data.iterrows():
            table_data.append({
                'Date': idx.strftime('%Y-%m-%d %H:%M:%S'),
                'Close': round(row['Close'], 2) if 'Close' in row and not pd.isna(row['Close']) else 'N/A',
                'Volume': int(row['Volume']) if 'Volume' in row and not pd.isna(row['Volume']) else 'N/A'
            })
        # Sort by most recent first
        table_data.sort(key=lambda x: x['Date'], reverse=True)
    return table_data

def plot_data(data, title, is_option=False):
    """Create a plotly figure from the price data"""
    fig = go.Figure()
    
    # Handle empty data case
    if data.empty or 'Close' not in data.columns:
        fig.update_layout(
            title=f'{title} Prices - No data available',
            xaxis_title='Time',
            yaxis_title='Price',
            annotations=[{
                'text': 'No data available for the selected parameters',
                'showarrow': False,
                'font': {'size': 20}
            }]
        )
        return fig
    
    # Normal case with data
    color = 'green' if data['Close'].iloc[-1] >= data['Close'].iloc[0] else 'red'
    fig.add_trace(go.Scatter(x=data.index, y=data['Close'], mode='lines+markers', line=dict(color=color), name='Close'))

    # Adding simple moving averages (SMAs)
    if len(data) >= 10:
        data['SMA_10'] = data['Close'].rolling(window=min(10, len(data)), min_periods=1).mean()
        fig.add_trace(go.Scatter(x=data.index, y=data['SMA_10'], mode='lines', line=dict(color='pink'), name='SMA 10'))
    
    if len(data) >= 20:
        data['SMA_20'] = data['Close'].rolling(window=min(20, len(data)), min_periods=1).mean()
        fig.add_trace(go.Scatter(x=data.index, y=data['SMA_20'], mode='lines', line=dict(color='black'), name='SMA 20'))

    if not is_option:  # For stock plot
        if len(data) >= 7:
            data['SMA_7'] = data['Close'].rolling(window=min(7, len(data)), min_periods=1).mean()
            fig.add_trace(go.Scatter(x=data.index, y=data['SMA_7'], mode='lines', line=dict(color='blue'), name='SMA 7'))
        
        if len(data) >= 50:
            data['SMA_50'] = data['Close'].rolling(window=min(50, len(data)), min_periods=1).mean()
            fig.add_trace(go.Scatter(x=data.index, y=data['SMA_50'], mode='lines', line=dict(color='purple'), name='SMA 50'))

        # Calculate Hull Moving Average (HMA) if enough data
        if len(data) >= 6:
            wma_half = data['Close'].rolling(window=min(3, len(data)), min_periods=1).mean()
            wma_full = data['Close'].rolling(window=min(6, len(data)), min_periods=1).mean()
            hma = (2 * wma_half - wma_full).rolling(window=max(1, int(min(6, len(data))**0.5)), min_periods=1).mean()
            data['HMA_6'] = hma
            fig.add_trace(go.Scatter(x=data.index, y=data['HMA_6'], mode='lines', line=dict(color='orange'), name='HMA 6'))

    fig.update_layout(
        title=f'{title} Prices',
        xaxis_title='Time',
        xaxis_rangeslider_visible=False,  # Remove the range slider
        yaxis_title='Price',
        margin=dict(l=50, r=20, t=50, b=50),  # Adjust the margins
        autosize=True  # Automatically size the plot area
    )
    
    # Only set x-axis range if there's data
    if not data.empty and len(data.index) > 0:
        fig.update_layout(xaxis_range=[data.index[0], data.index[-1]])
    
    return fig

# Layout of the app
app.layout = html.Div([
    html.H1('Real-Time Stock-Option Pair Dashboard', style={'textAlign': 'center'}),
    
    html.Div([
        html.Div([
            html.H2('Stock'),
            dcc.Input(id='stock-ticker-input', type='text', value='AAPL', placeholder='Enter Stock Ticker Symbol (e.g., AAPL)', style={'width': '50%'}),
            dcc.Dropdown(
                id='stock-timeframe-dropdown',
                options=[{'label': tf, 'value': tf} for tf in timeframes],
                value='1mo',
                placeholder='Select Timeframe',
                style={'width': '50%'}
            ),
            dcc.Dropdown(
                id='stock-interval-dropdown',
                options=[{'label': ti, 'value': ti} for ti in time_intervals],
                value='1d',
                placeholder='Select Interval',
                style={'width': '50%'}
            ),
            html.Div(id='alerts-container'),
            dcc.Graph(id='stock-plot', style={'height': '70vh', 'width': '100%'})
        ], style={'width': '60%', 'display': 'inline-block', 'vertical-align': 'top'}),
        
        html.Div([
            html.H2('Option'),
            dcc.Input(id='option-ticker-input', type='text', value='AAPL', placeholder='Enter Option Ticker Symbol (e.g., AAPL)', style={'width': '90%'}),
            dcc.Input(id='option-type-input', type='text', value='c', placeholder='C for Call, P for Put', style={'width': '90%'}),
            dcc.Input(id='option-expiry-input', type='text', placeholder='Enter Expiry Date (YYYY-MM-DD) or leave blank for nearest', style={'width': '90%'}),
            dcc.Input(id='option-strike-input', type='number', placeholder='Enter Strike Price or leave blank for ATM', style={'width': '90%'}),
            dcc.Dropdown(
                id='option-timeframe-dropdown',
                options=[{'label': tf, 'value': tf} for tf in timeframes],
                value='1mo',
                placeholder='Select Timeframe',
                style={'width': '90%'}
            ),
            dcc.Dropdown(
                id='option-interval-dropdown',
                options=[{'label': ti, 'value': ti} for ti in time_intervals],
                value='1d',
                placeholder='Select Interval',
                style={'width': '90%'}
            ),
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
        ], style={'width': '40%', 'display': 'inline-block', 'vertical-align': 'top', 'padding-left': '20px'}),
    ]),
    
    html.Div([
        html.P("Dashboard with enhanced error handling and strict rate limiting (1 request per minute)", 
               style={'textAlign': 'center', 'color': 'gray', 'fontSize': '12px'}),
        html.P("If you see 'No Data Available', please wait at least 60-70 seconds before the next refresh.",
               style={'textAlign': 'center', 'color': 'gray', 'fontSize': '12px'})
    ]),
    
    dcc.Interval(
        id='interval-component',
        interval=60*1000,  # in milliseconds (default update every minute)
        n_intervals=0
    )
])

@app.callback(
    Output('stock-interval-dropdown', 'options'),
    Output('option-interval-dropdown', 'options'),
    Input('stock-timeframe-dropdown', 'value'),
    Input('option-timeframe-dropdown', 'value'),
)
def update_intervals(stock_timeframe, option_timeframe):
    """Update available intervals based on selected timeframe"""
    interval_options = {
        '1d': [{'label': i, 'value': i} for i in ['1m', '2m', '5m', '15m', '30m', '1h', '1d']],
        '5d': [{'label': i, 'value': i} for i in ['5m', '15m', '30m', '1h', '1d', '5d']],
        '1mo': [{'label': i, 'value': i} for i in ['15m', '30m', '1h', '1d', '1wk', '1mo']],
        '3mo': [{'label': i, 'value': i} for i in ['1h', '1d', '1wk', '1mo']],
        '6mo': [{'label': i, 'value': i} for i in ['1d', '1wk', '1mo']],
        '1y': [{'label': i, 'value': i} for i in ['1d', '1wk', '1mo']],
        '2y': [{'label': i, 'value': i} for i in ['1d', '1wk', '1mo']],
        '5y': [{'label': i, 'value': i} for i in ['1d', '1wk', '1mo']],
        '10y': [{'label': i, 'value': i} for i in ['1d', '1wk', '1mo']],
        'max': [{'label': i, 'value': i} for i in ['1d', '1wk', '1mo']],
    }
    
    stock_intervals = interval_options.get(stock_timeframe, [{'label': i, 'value': i} for i in ['5m', '15m', '1h', '1d']])
    option_intervals = interval_options.get(option_timeframe, [{'label': i, 'value': i} for i in ['5m', '15m', '1h', '1d']])
    
    return stock_intervals, option_intervals

@app.callback(
    Output('stock-plot', 'figure'),
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
)
def update_data_and_plot(n_intervals,
                         stock_ticker, stock_timeframe, stock_interval,
                         option_ticker, option_type, option_expiry, option_strike,
                         option_timeframe, option_interval):
    """Main callback to update the dashboard with improved error handling"""
    global last_used_ticker
    
    """Main callback to update the dashboard with improved error handling"""
    try:
        # Normalize tickers to uppercase
        stock_ticker = normalize_ticker(stock_ticker)
        option_ticker = normalize_ticker(option_type)
        
        # Check if stock ticker has changed
        is_new_ticker = stock_ticker != last_used_ticker and stock_ticker
        # Initialize outputs
        stock_fig = go.Figure()
        option_fig = go.Figure()
        option_table_data = []
        alerts = []
        
        # Determine next update interval (random between 60-70 seconds)
        update_interval = int((60 + random.uniform(0, 10)) * 1000)
        
        # Set default intervals if None
        stock_interval = stock_interval or '5m'
        option_interval = option_interval or '5m'
        
        # Determine if the market is open
        market_open = is_market_open()

        # Add info about data source and caching
        if is_new_ticker:
            alerts.append(html.Div(f'New ticker detected: {stock_ticker} - Using faster rate limiting', style={'color': 'blue'}))
        
        # Add info about data source and caching
        alerts.append(html.Div('Using Yahoo Finance data with caching and strict rate limiting (1 request per minute)', style={'color': 'blue'}))
        
        if not market_open:
            alerts.append(html.Div('Market is currently closed - updates less frequent', style={'color': 'orange'}))
        
        # Fetch stock data
        if stock_ticker:
            logging.info(f"Fetching data for {stock_ticker} with timeframe={stock_timeframe}, interval={stock_interval}")
            stock_data = get_stock_data(stock_ticker, stock_timeframe, stock_interval)
            
            # Update the last used ticker after successful fetch
            if not stock_data.empty:
                last_used_ticker = stock_ticker

            # Check if we got stock data
            if stock_data.empty:
                stock_fig = go.Figure()
                stock_fig.update_layout(
                    title="No Data Available",
                    annotations=[{
                        'text': "Try refreshing in 1 minute to see data.",
                        'showarrow': False,
                        'font': {'size': 16, 'color': 'red'}
                    }]
                )
                
                alerts.append(html.Div(
                    'Try refreshing in 1 minute to see data.',
                    style={'color': 'red', 'fontWeight': 'bold'}
                ))
                
                # Set same empty message for option plot
                option_fig = go.Figure()
                option_fig.update_layout(
                    title="No Data Available",
                    annotations=[{
                        'text': "Please input option data to see graph.",
                        'showarrow': False,
                        'font': {'size': 16, 'color': 'red'}
                    }]
                )
                
                return stock_fig, option_fig, [], html.Div(alerts), update_interval
            
            # If we have data, use the plot_data function for visualization
            stock_fig = plot_data(stock_data, f'{stock_ticker} Stock')
            
            # Generate alerts if we have enough data
            if not stock_data.empty and len(stock_data) > 1 and 'Close' in stock_data.columns:
                # Calculate indicators for alerts
                min_periods = min(len(stock_data), 50)  # Adjust window size based on available data
                
                if len(stock_data) >= 7:
                    stock_data['SMA_7'] = stock_data['Close'].rolling(window=min(7, min_periods), min_periods=1).mean()
                if len(stock_data) >= 20:
                    stock_data['SMA_20'] = stock_data['Close'].rolling(window=min(20, min_periods), min_periods=1).mean()
                
                # Calculate HMA only if we have enough data
                if len(stock_data) >= 6:
                    wma_half = stock_data['Close'].rolling(window=min(3, min_periods), min_periods=1).mean()
                    wma_full = stock_data['Close'].rolling(window=min(6, min_periods), min_periods=1).mean()
                    stock_data['HMA_6'] = (2 * wma_half - wma_full).rolling(window=int(min(6, min_periods)**0.5), min_periods=1).mean()
                
                close = stock_data['Close'].iloc[-1]
                
                # Add technical analysis alerts
                if 'SMA_20' in stock_data.columns:
                    sma_20 = stock_data['SMA_20'].iloc[-1]
                    if close < sma_20:
                        alerts.append(html.Div('Sell Bear Alert: Close below SMA 20', style={'color': 'red'}))
                    elif close > sma_20:
                        alerts.append(html.Div('Buy Bull Alert: Close above SMA 20', style={'color': 'green'}))
                
                if 'SMA_7' in stock_data.columns and 'HMA_6' in stock_data.columns:
                    sma_7 = stock_data['SMA_7'].iloc[-1]
                    hma_6 = stock_data['HMA_6'].iloc[-1]
                    
                    if close < sma_7:
                        alerts.append(html.Div('Bear Alert: Close below SMA 7', style={'color': 'red'}))
                    elif close > sma_7:
                        alerts.append(html.Div('Bull Alert: Close above SMA 7', style={'color': 'green'}))
                    
                    if hma_6 < sma_7:
                        alerts.append(html.Div('Short Term Bear Alert: HMA 6 below SMA 7', style={'color': 'red'}))
                    elif hma_6 > sma_7:
                        alerts.append(html.Div('Short Term Bull Alert: HMA 6 above SMA 7', style={'color': 'green'}))
        
        # Try to fetch option data if stock data was successful
        if option_ticker and option_type and option_expiry and option_strike:
            try:
                option_data = get_option_data(
                    option_ticker, option_type, option_expiry, option_strike, 
                    option_timeframe, option_interval
                )
                
                if not option_data.empty and 'Close' in option_data.columns:
                    # Use the plot_data function for visualization
                    option_fig = plot_data(option_data, f'{option_ticker} {option_type} Options', is_option=True)
                    
                    # Format table data
                    option_table_data = prepare_table_data(option_data)
                else:
                    option_fig = plot_data(pd.DataFrame(columns=['Close']), f'No option data for {option_ticker}')
                    alerts.append(html.Div(f'No option data for {option_ticker} {option_type} {option_strike} {option_expiry}', 
                                        style={'color': 'red'}))
            except Exception as e:
                logging.error(f"Error processing option data: {e}")
                logging.error(traceback.format_exc())
                
                option_fig = plot_data(pd.DataFrame(columns=['Close']), f'Error loading option data')
                alerts.append(html.Div(f'Error loading options: {str(e)}', style={'color': 'red'}))
        else:
            # When we don't have all option parameters, just show a message
            option_fig = go.Figure()
            option_fig.update_layout(
                title="Option Data",
                annotations=[{
                    'text': "Enter ticker, type, expiry date, and strike price to view option data",
                    'showarrow': False,
                    'font': {'size': 14, 'color': 'gray'}
                }]
            )
            option_table_data = []  # Empty table data


        # if option_ticker and option_type:
        #     try:
        #         option_data = get_option_data(
        #             option_ticker, option_type, option_expiry, option_strike, 
        #             option_timeframe, option_interval
        #         )
                
        #         if not option_data.empty and 'Close' in option_data.columns:
        #             # Use the plot_data function for visualization
        #             option_fig = plot_data(option_data, f'{option_ticker} {option_type} Options', is_option=True)
                    
        #             # Format table data
        #             option_table_data = prepare_table_data(option_data)
        #         else:
        #             option_fig = plot_data(pd.DataFrame(columns=['Close']), f'No option data for {option_ticker}')
                    
        #             if option_expiry and option_strike:
        #                 alerts.append(html.Div(f'No option data for {option_ticker} {option_type} {option_strike} {option_expiry}', 
        #                                       style={'color': 'red'}))
        #             else:
        #                 alerts.append(html.Div(f'Enter expiry date and strike price for options or system will try to find the nearest ones', 
        #                                       style={'color': 'orange'}))
        #     except Exception as e:
        #         logging.error(f"Error processing option data: {e}")
        #         logging.error(traceback.format_exc())
                
        #         option_fig = plot_data(pd.DataFrame(columns=['Close']), f'Error loading option data')
        #         alerts.append(html.Div(f'Error loading options: {str(e)}', style={'color': 'red'}))
        # else:
        #     option_fig = plot_data(pd.DataFrame(columns=['Close']), 'Option - Enter ticker and type')
        
        # Add info on when data was last fetched
        last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        alerts.append(html.Div(f"Last data update: {last_update}", style={'color': 'gray', 'fontSize': '12px'}))
        
        # Add info on rate limiting
        time_since_last = time_module.time() - last_request_time
        if time_since_last < 60:
            alerts.append(html.Div(
                f"Rate limit: Need to wait {60 - int(time_since_last)} more seconds before next request", 
                style={'color': 'blue'}
            ))
        
        return stock_fig, option_fig, option_table_data, html.Div(alerts), update_interval
        
    except Exception as e:
        # Improved error handling
        logging.error(f"Unhandled exception in callback: {str(e)}")
        logging.error(traceback.format_exc())
        
        # Create error figures with style similar to modifiedyf.py
        stock_fig = go.Figure()
        stock_fig.update_layout(
            title="Error in Dashboard",
            annotations=[{
                'text': f"An error occurred: {str(e)[:100]}..." if len(str(e)) > 100 else str(e),
                'showarrow': False,
                'font': {'size': 20, 'color': 'red'}
            }]
        )
        
        option_fig = go.Figure()
        option_fig.update_layout(
            title="API Error",
            annotations=[{
                'text': "Yahoo Finance API is not working right now. Try again in some time.",
                'showarrow': False,
                'font': {'size': 20, 'color': 'red'}
            }]
        )
        
        alerts_content = html.Div([
            html.Div("ERROR: " + str(e), style={'color': 'red', 'fontWeight': 'bold'})
        ])
        
        # Keep the random delay between 60-70 seconds
        update_interval = int((60 + random.uniform(0, 10)) * 1000)
        
        return stock_fig, option_fig, [], alerts_content, update_interval

# Running the app
if __name__ == '__main__':
    # Set debug to False for production deployment
    app.run_server(debug=False)