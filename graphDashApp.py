
# STILL HAVE TO CHANGE BEAUTIFUL SOUP TO SELENIUM.
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
CACHE_DURATION = 300  # Cache duration in seconds (5 minutes)

# Define a custom user agent rotation to avoid blocks
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36'
]

# Track rate limits to avoid being blocked
last_request_time = 0
MIN_REQUEST_INTERVAL = 1.0  # Minimum time between requests in seconds

# Layout of the app
app.layout = html.Div([
    html.H1('Real-Time Stock-Option Pair Dashboard', style={'textAlign': 'center'}),
    
    html.Div([
        html.Div([
            html.H2('Stock'),
            dcc.Input(id='stock-ticker-input', type='text', value='AAPL', placeholder='Enter Stock Ticker Symbol (e.g., AAPL)', style={'width': '50%'}),
            dcc.Dropdown(id='stock-timeframe-dropdown', options=[{'label': i, 'value': i} for i in timeframes], value='1d', placeholder='Select Timeframe', style={'width': '50%'}),
            dcc.Dropdown(id='stock-interval-dropdown', options=[{'label': i, 'value': i} for i in time_intervals], value='5m', placeholder='Select Interval', style={'width': '50%'}),
            html.Div(id='alerts-container'),
            dcc.Graph(id='stock-plot', style={'height': '70vh', 'width': '100%'}),
        ], style={'width': '60%', 'display': 'inline-block', 'vertical-align': 'top'}),
        
        html.Div([
            html.H2('Option'),
            dcc.Input(id='option-ticker-input', type='text', value='AAPL', placeholder='Enter Stock Ticker (e.g., AAPL)', style={'width': '90%'}),
            dcc.Input(id='option-type-input', type='text', value='c', placeholder='Enter Option Type (c or p)', style={'width': '90%'}),
            dcc.Input(id='option-expiry-input', type='text', placeholder='Enter Expiry Date (YYYY-MM-DD)', style={'width': '90%'}),
            dcc.Input(id='option-strike-input', type='number', placeholder='Enter Strike Price', style={'width': '90%'}),
            dcc.Dropdown(id='option-timeframe-dropdown', options=[{'label': i, 'value': i} for i in timeframes], value='1d', placeholder='Select Timeframe', style={'width': '90%'}),
            dcc.Dropdown(id='option-interval-dropdown', options=[{'label': i, 'value': i} for i in time_intervals], value='5m', placeholder='Select Interval', style={'width': '90%'}),
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
        ], style={'width': '40%', 'display': 'inline-block', 'vertical-align': 'top'}),
    ]),
    
    html.Div([
        html.P("Dashboard with enhanced error handling and caching", 
               style={'textAlign': 'center', 'color': 'gray', 'fontSize': '12px'}),
    ]),
    
    dcc.Interval(
        id='interval-component',
        interval=60*1000,  # in milliseconds (default update every minute)
        n_intervals=0
    )
])

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

def rate_limit_request():
    """Apply rate limiting to avoid being blocked"""
    global last_request_time
    
    current_time = time_module.time()
    elapsed = current_time - last_request_time
    
    if elapsed < MIN_REQUEST_INTERVAL:
        sleep_time = MIN_REQUEST_INTERVAL - elapsed
        time_module.sleep(sleep_time)
    
    last_request_time = time_module.time()

def apply_proxy_settings():
    """
    Configure yfinance with random user agent and session settings
    This helps avoid blocks from Yahoo Finance
    """
    user_agent = random.choice(USER_AGENTS)
    
    # Set a custom session with headers
    session = requests.Session()
    session.headers.update({
        'User-Agent': user_agent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'TE': 'Trailers'
    })
    
    return session

@lru_cache(maxsize=32)
def get_stock_data(ticker, period='1d', interval='5m', retry_count=0):
    """
    Get stock data with error handling and retries
    
    Args:
        ticker: Stock ticker symbol
        period: Time period (1d, 5d, 1mo, etc.)
        interval: Time interval between data points (1m, 5m, 1d, etc.)
        retry_count: Number of retries attempted so far
    
    Returns:
        Pandas DataFrame with stock data
    """
    cache_key = get_cache_key("stock_data", ticker, period, interval)
    cached_data = get_cached_data(cache_key)
    if cached_data is not None:
        logging.info(f"Using cached data for {ticker} {period} {interval}")
        return cached_data
    
    # Maximum number of retries
    max_retries = 3
    
    # Apply rate limiting
    rate_limit_request()
    
    try:
        logging.info(f"Fetching stock data for {ticker} with period={period}, interval={interval}")
        
        # Create a ticker object
        stock = yf.Ticker(ticker)
        
        # Try to get history with the requested parameters
        stock_data = stock.history(period=period, interval=interval)
        
        # If we got no data, try with different parameters
        if stock_data.empty and retry_count < max_retries:
            if interval == '1m' or interval == '2m' or interval == '5m':
                # Try with a less granular interval
                logging.warning(f"No data for {ticker} with interval={interval}, trying with interval=15m")
                return get_stock_data(ticker, period, '15m', retry_count + 1)
            
            elif period == '1d':
                # Try with a longer period
                logging.warning(f"No data for {ticker} with period=1d, trying with period=5d")
                return get_stock_data(ticker, '5d', interval, retry_count + 1)
            
            else:
                # Try daily data as a last resort
                logging.warning(f"No data for {ticker}, falling back to daily data")
                return get_stock_data(ticker, '1mo', '1d', retry_count + 1)
        
        # Cache and return the data if not empty
        if not stock_data.empty:
            set_cached_data(cache_key, stock_data)
            return stock_data
        else:
            logging.error(f"No data available for {ticker} after multiple retries")
            return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])
        
    except Exception as e:
        logging.error(f"Error fetching data for {ticker}: {str(e)}")
        
        # If we haven't reached the maximum retries, try again with different parameters
        if retry_count < max_retries:
            logging.info(f"Retrying with different parameters (attempt {retry_count + 1}/{max_retries})")
            time_module.sleep(2)  # Wait a bit before retrying
            
            if 'connection' in str(e).lower() or 'timeout' in str(e).lower():
                # Network issue, just retry with the same parameters
                return get_stock_data(ticker, period, interval, retry_count + 1)
            else:
                # Try with different parameters
                if interval in ['1m', '2m', '5m']:
                    return get_stock_data(ticker, period, '15m', retry_count + 1)
                elif period == '1d':
                    return get_stock_data(ticker, '5d', '1h', retry_count + 1)
                else:
                    return get_stock_data(ticker, '1mo', '1d', retry_count + 1)
        else:
            logging.error(f"Maximum retries reached for {ticker}")
            return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])

def get_option_expirations(ticker):
    """Get available option expiration dates for a ticker"""
    cache_key = get_cache_key("option_expirations", ticker)
    cached_data = get_cached_data(cache_key)
    if cached_data is not None:
        return cached_data
    
    # Apply rate limiting
    rate_limit_request()
    
    try:
        stock = yf.Ticker(ticker)
        expirations = stock.options
        
        if expirations:
            set_cached_data(cache_key, expirations)
            return expirations
        else:
            logging.warning(f"No option expiration dates found for {ticker}")
            return []
    except Exception as e:
        logging.error(f"Error getting option expirations for {ticker}: {str(e)}")
        return []

def get_option_chain(ticker, expiry):
    """Get option chain for a specific expiration date"""
    cache_key = get_cache_key("option_chain", ticker, expiry)
    cached_data = get_cached_data(cache_key)
    if cached_data is not None:
        return cached_data
    
    # Apply rate limiting
    rate_limit_request()
    
    try:
        stock = yf.Ticker(ticker)
        option_chain = stock.option_chain(expiry)
        
        if option_chain:
            set_cached_data(cache_key, option_chain)
            return option_chain
        else:
            logging.warning(f"No options found for {ticker} with expiry {expiry}")
            return None
    except Exception as e:
        logging.error(f"Error getting option chain for {ticker} with expiry {expiry}: {str(e)}")
        return None

def get_option_data(ticker, option_type, expiry=None, strike=None, period='1d', interval='5m', retry_count=0):
    """
    Get option data with error handling and retries
    """
    # Maximum number of retries
    max_retries = 3
    
    try:
        # If no expiry provided, get the nearest expiration date
        if not expiry:
            expirations = get_option_expirations(ticker)
            if not expirations:
                logging.warning(f"No option expiration dates found for {ticker}")
                return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])
            
            # Sort and get the nearest expiration
            expiry = expirations[0]
            logging.info(f"Using nearest expiry date: {expiry}")
        
        # Get option chain for this expiry
        option_chain = get_option_chain(ticker, expiry)
        if not option_chain:
            return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])
        
        # Filter by option type
        if option_type.lower() == 'c':
            options = option_chain.calls
        elif option_type.lower() == 'p':
            options = option_chain.puts
        else:
            logging.error(f"Invalid option type: {option_type}")
            return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])
        
        # If no options found
        if options.empty:
            logging.warning(f"No {option_type} options found for {ticker} with expiry {expiry}")
            return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])
        
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
        
        # Find the option with the specified strike
        option = options[options['strike'] == strike]
        
        if option.empty:
            logging.warning(f"No option found with strike {strike}")
            # Find closest available strike
            options['diff'] = abs(options['strike'] - strike)
            closest_option = options.loc[options['diff'].idxmin()]
            strike = closest_option['strike']
            option = options[options['strike'] == strike]
            logging.info(f"Using closest available strike: {strike}")
        
        # Get the option symbol
        option_symbol = option['contractSymbol'].iloc[0]
        
        # Apply rate limiting
        rate_limit_request()
        
        # Cache key for option data
        cache_key = get_cache_key("option_data", option_symbol, period, interval)
        cached_data = get_cached_data(cache_key)
        if cached_data is not None:
            return cached_data
        
        # Get option price history
        try:
            option_data = yf.Ticker(option_symbol).history(period=period, interval=interval)
            
            # If data is empty, try different parameters
            if option_data.empty and retry_count < max_retries:
                if interval in ['1m', '2m', '5m']:
                    logging.warning(f"No data for option {option_symbol} with interval={interval}, trying 15m")
                    return get_option_data(ticker, option_type, expiry, strike, period, '15m', retry_count + 1)
                elif period == '1d':
                    logging.warning(f"No data for option {option_symbol} with period=1d, trying 5d")
                    return get_option_data(ticker, option_type, expiry, strike, '5d', interval, retry_count + 1)
                else:
                    logging.warning(f"No data for option {option_symbol}, trying daily data")
                    return get_option_data(ticker, option_type, expiry, strike, '1mo', '1d', retry_count + 1)
            
            # If we have data, cache and return it
            if not option_data.empty:
                set_cached_data(cache_key, option_data)
                return option_data
            else:
                logging.error(f"No option data available for {option_symbol} after retries")
                return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])
                
        except Exception as e:
            logging.error(f"Error getting option data for {option_symbol}: {str(e)}")
            
            # Retry with different parameters if we haven't reached max retries
            if retry_count < max_retries:
                time_module.sleep(2)  # Wait before retrying
                if interval in ['1m', '2m', '5m']:
                    return get_option_data(ticker, option_type, expiry, strike, period, '15m', retry_count + 1)
                elif period == '1d':
                    return get_option_data(ticker, option_type, expiry, strike, '5d', '1h', retry_count + 1)
                else:
                    return get_option_data(ticker, option_type, expiry, strike, '1mo', '1d', retry_count + 1)
            else:
                return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])
        
    except Exception as e:
        logging.error(f"Error in get_option_data: {str(e)}")
        logging.error(traceback.format_exc())
        return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])

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
    """Main callback to update the dashboard"""
    try:
        # Initialize outputs
        stock_fig = go.Figure()
        option_fig = go.Figure()
        option_table_data = []
        alerts = []
            
        # Set default intervals if None
        stock_interval = stock_interval or '5m'
        option_interval = option_interval or '5m'
        
        # Determine if the market is open
        market_open = is_market_open()
        
        # Set interval based on market status
        if market_open:
            update_interval = 60000  # 1 minute interval when market is open
        else:
            update_interval = 300000  # 5 minutes interval when market is closed
            alerts.append(html.Div('Market is currently closed - updates less frequent', style={'color': 'orange'}))
        
        # Add info about data source and caching
        alerts.append(html.Div('Using Yahoo Finance data with caching and error handling', style={'color': 'blue'}))
        
        # Fetch stock data
        if stock_ticker:
            logging.info(f"Fetching data for {stock_ticker} with timeframe={stock_timeframe}, interval={stock_interval}")
            stock_data = get_stock_data(stock_ticker, stock_timeframe, stock_interval)
            
            if not stock_data.empty and 'Close' in stock_data.columns:
                # Calculate indicators for alerts
                min_periods = min(len(stock_data), 50)  # Adjust window size based on available data
                
                if len(stock_data) >= 7:
                    stock_data['SMA_7'] = stock_data['Close'].rolling(window=min(7, min_periods), min_periods=1).mean()
                if len(stock_data) >= 20:
                    stock_data['SMA_20'] = stock_data['Close'].rolling(window=min(20, min_periods), min_periods=1).mean()
                if len(stock_data) >= 50:
                    stock_data['SMA_50'] = stock_data['Close'].rolling(window=min(50, min_periods), min_periods=1).mean()
                
                # Calculate HMA only if we have enough data
                if len(stock_data) >= 6:
                    wma_half = stock_data['Close'].rolling(window=min(3, min_periods), min_periods=1).mean()
                    wma_full = stock_data['Close'].rolling(window=min(6, min_periods), min_periods=1).mean()
                    stock_data['HMA_6'] = (2 * wma_half - wma_full).rolling(window=int(min(6, min_periods)**0.5), min_periods=1).mean()
                
                stock_fig = plot_data(stock_data, 'Stock')
                
                # Generate alerts if we have enough data
                if len(stock_data) > 1:
                    close = stock_data['Close'].iloc[-1]
                    
                    if 'SMA_20' in stock_data.columns:
                        sma_20 = stock_data['SMA_20'].iloc[-1]
                        if close < sma_20:
                            alerts.append(html.Div('Sell Bear Alert: Close below SMA 20', style={'color': 'red'}))
                        elif close > sma_20:
                            alerts.append(html.Div('Buy Bull Alert: Close above SMA 20', style={'color': 'green'}))
                    
                    if 'SMA_7' in stock_data.columns:
                        sma_7 = stock_data['SMA_7'].iloc[-1]
                        if close < sma_7:
                            alerts.append(html.Div('Bear Alert: Close below SMA 7', style={'color': 'red'}))
                        elif close > sma_7:
                            alerts.append(html.Div('Bull Alert: Close above SMA 7', style={'color': 'green'}))
                    
                    if 'HMA_6' in stock_data.columns and 'SMA_7' in stock_data.columns:
                        hma_6 = stock_data['HMA_6'].iloc[-1]
                        sma_7 = stock_data['SMA_7'].iloc[-1]
                        if hma_6 < sma_7:
                            alerts.append(html.Div('Short Term Bear Alert: HMA 6 below SMA 7', style={'color': 'red'}))
                        elif hma_6 > sma_7:
                            alerts.append(html.Div('Short Term Bull Alert: HMA 6 above SMA 7', style={'color': 'green'}))
            else:
                # Create an empty plot with a message
                stock_fig = plot_data(pd.DataFrame(columns=['Close']), f'No data for {stock_ticker}')
                alerts.append(html.Div(f'No data available for {stock_ticker}', style={'color': 'red'}))
                
        # Fetch option data
        if option_ticker and option_type:
            try:
                logging.info(f"Fetching option data for {option_ticker} {option_type} with strike={option_strike}, expiry={option_expiry}")
                option_data = get_option_data(option_ticker, option_type, option_expiry, option_strike, option_timeframe, option_interval)
                
                if not option_data.empty and 'Close' in option_data.columns:
                    option_table_data = prepare_table_data(option_data)
                    option_fig = plot_data(option_data, 'Option', is_option=True)
                else:
                    option_fig = plot_data(pd.DataFrame(columns=['Close']), f'No option data for {option_ticker}')
                    if option_expiry and option_strike:
                        alerts.append(html.Div(f'No option data for {option_ticker} {option_type} {option_strike} {option_expiry}', style={'color': 'red'}))
                    else:
                        alerts.append(html.Div(f'Enter expiry date and strike price for options or system will try to find the nearest ones', style={'color': 'orange'}))
            except Exception as e:
                logging.error(f"Error processing option data: {e}")
                logging.error(traceback.format_exc())
                option_fig = plot_data(pd.DataFrame(columns=['Close']), f'Error loading option data')
                alerts.append(html.Div(f'Error loading options: {str(e)}', style={'color': 'red'}))
        else:
            option_fig = plot_data(pd.DataFrame(columns=['Close']), 'Option - Enter ticker and type')
            
        # Ensure alerts is not empty even if there are no alerts
        alerts_content = html.Div(alerts) if alerts else []

        return stock_fig, option_fig, option_table_data, alerts_content, update_interval
        
    except Exception as e:
        # Catch any unhandled exceptions to prevent callback from failing entirely
        logging.error(f"Unhandled exception in callback: {str(e)}")
        logging.error(traceback.format_exc())
        
        # Create empty figures with error message
        stock_fig = go.Figure()
        stock_fig.update_layout(
            title="Error in Dashboard",
            annotations=[{
                'text': f"An error occurred: {str(e)}",
                'showarrow': False,
                'font': {'size': 20, 'color': 'red'}
            }]
        )
        
        option_fig = go.Figure()
        option_fig.update_layout(
            title="Error in Dashboard",
            annotations=[{
                'text': "See console for details",
                'showarrow': False,
                'font': {'size': 20, 'color': 'red'}
            }]
        )
        
        alerts_content = html.Div([
            html.Div(f"ERROR: {str(e)}", style={'color': 'red', 'fontWeight': 'bold'})
        ])
        
        return stock_fig, option_fig, [], alerts_content, 300000  # 5-minute update interval