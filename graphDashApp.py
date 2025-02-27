
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
import requests
import json
from time import sleep

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Finnhub API key - REPLACE THIS WITH YOUR ACTUAL API KEY
FINNHUB_API_KEY = "cv0bht1r01qo8ssfr960cv0bht1r01qo8ssfr96g"  # Get this by signing up at finnhub.io

# Initialize Dash app
app = dash.Dash(__name__)

# List of options for time interval and timeframe
time_intervals = ['1m', '5m', '15m', '30m', '1h', '1d', '1wk', '1mo']
timeframes = ['1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', 'max']

# Cache for storing API responses to minimize requests
data_cache = {}
CACHE_DURATION = 300  # Cache duration in seconds (5 minutes)

# Layout of the app
app.layout = html.Div([
    html.H1('Real-Time Stock-Option Pair Dashboard', style={'textAlign': 'center'}),
    
    html.Div([
        html.Div([
            html.H2('Stock'),
            dcc.Input(id='stock-ticker-input', type='text', value='NVDA', placeholder='Enter Stock Ticker Symbol (e.g., AAPL)', style={'width': '50%'}),
            dcc.Dropdown(id='stock-timeframe-dropdown', options=[{'label': i, 'value': i} for i in timeframes], value='1d', placeholder='Select Timeframe', style={'width': '50%'}),
            dcc.Dropdown(id='stock-interval-dropdown', options=[{'label': i, 'value': i} for i in time_intervals], value='15m', placeholder='Select Interval', style={'width': '50%'}),
            html.Div(id='alerts-container'),
            dcc.Graph(id='stock-plot', style={'height': '70vh', 'width': '100%'}),
        ], style={'width': '60%', 'display': 'inline-block', 'vertical-align': 'top'}),
        
        html.Div([
            html.H2('Option'),
            dcc.Input(id='option-ticker-input', type='text', value='NVDA', placeholder='Enter Stock Ticker (e.g., AAPL)', style={'width': '90%'}),
            dcc.Input(id='option-type-input', type='text', value='c', placeholder='Enter Option Type (c or p)', style={'width': '90%'}),
            dcc.Input(id='option-expiry-input', type='text', placeholder='Enter Expiry Date (YYYY-MM-DD)', style={'width': '90%'}),
            dcc.Input(id='option-strike-input', type='number', placeholder='Enter Strike Price', style={'width': '90%'}),
            dcc.Dropdown(id='option-timeframe-dropdown', options=[{'label': i, 'value': i} for i in timeframes], value='1d', placeholder='Select Timeframe', style={'width': '90%'}),
            dcc.Dropdown(id='option-interval-dropdown', options=[{'label': i, 'value': i} for i in time_intervals], value='15m', placeholder='Select Interval', style={'width': '90%'}),
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
        html.P("Data provided by Finnhub.io", style={'textAlign': 'center', 'color': 'gray', 'fontSize': '12px'}),
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

def convert_timeframe_to_seconds(timeframe):
    """Convert timeframe string to seconds for Finnhub API"""
    if timeframe == '1d':
        return 60 * 60 * 24
    elif timeframe == '5d':
        return 60 * 60 * 24 * 5
    elif timeframe == '1mo':
        return 60 * 60 * 24 * 30
    elif timeframe == '3mo':
        return 60 * 60 * 24 * 90
    elif timeframe == '6mo':
        return 60 * 60 * 24 * 180
    elif timeframe == '1y':
        return 60 * 60 * 24 * 365
    elif timeframe == '2y':
        return 60 * 60 * 24 * 365 * 2
    elif timeframe == '5y':
        return 60 * 60 * 24 * 365 * 5
    elif timeframe == 'max':
        return 60 * 60 * 24 * 365 * 20  # 20 years should be enough for most stocks
    return 60 * 60 * 24  # Default to 1 day

def convert_interval_to_seconds(interval):
    """Convert interval string to seconds for Finnhub API"""
    if interval == '1m':
        return 60
    elif interval == '5m':
        return 300
    elif interval == '15m':
        return 900
    elif interval == '30m':
        return 1800
    elif interval == '1h':
        return 3600
    elif interval == '1d':
        return 86400
    elif interval == '1wk':
        return 604800
    elif interval == '1mo':
        return 2592000
    return 900  # Default to 15m

def get_finnhub_resolution(interval):
    """Convert our interval format to Finnhub's resolution format"""
    interval_map = {
        '1m': '1',
        '5m': '5',
        '15m': '15',
        '30m': '30',
        '1h': '60',
        '1d': 'D',
        '1wk': 'W',
        '1mo': 'M'
    }
    return interval_map.get(interval, '15')  # Default to 15 min if not found

def get_stock_data(ticker, timeframe='1d', interval='15m'):
    """
    Get stock data from Finnhub API
    """
    cache_key = get_cache_key("stock_data", ticker, timeframe, interval)
    cached_data = get_cached_data(cache_key)
    if cached_data is not None:
        return cached_data
    
    try:
        resolution = get_finnhub_resolution(interval)
        
        # Calculate time range
        end_time = int(datetime.now().timestamp())
        start_time = end_time - convert_timeframe_to_seconds(timeframe)
        
        # Make API request
        url = f"https://finnhub.io/api/v1/stock/candle"
        params = {
            'symbol': ticker.upper(),
            'resolution': resolution,
            'from': start_time,
            'to': end_time,
            'token': FINNHUB_API_KEY
        }
        
        response = requests.get(url, params=params)
        
        # Check for rate limiting (429 status)
        if response.status_code == 429:
            logging.warning("Rate limit hit, waiting 60 seconds...")
            sleep(60)  # Wait and try again
            response = requests.get(url, params=params)
        
        data = response.json()
        
        # Check if valid data returned
        if data.get('s') == 'ok' and len(data.get('c', [])) > 0:
            # Convert to pandas DataFrame
            df = pd.DataFrame({
                'Open': data['o'],
                'High': data['h'],
                'Low': data['l'],
                'Close': data['c'],
                'Volume': data['v'],
            }, index=pd.to_datetime([datetime.fromtimestamp(ts) for ts in data['t']]))
            
            set_cached_data(cache_key, df)
            return df
        else:
            logging.error(f"No data returned for {ticker}: {data.get('s')}")
            return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])
            
    except Exception as e:
        logging.error(f"Error getting stock data for {ticker}: {str(e)}")
        return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])

def get_option_expirations(ticker):
    """
    Get available option expiration dates for a ticker from Finnhub
    """
    cache_key = get_cache_key("option_expirations", ticker)
    cached_data = get_cached_data(cache_key)
    if cached_data is not None:
        return cached_data
    
    try:
        url = f"https://finnhub.io/api/v1/stock/option-chain"
        params = {
            'symbol': ticker.upper(),
            'token': FINNHUB_API_KEY
        }
        
        response = requests.get(url, params=params)
        data = response.json()
        
        # Get all expiration dates
        if 'data' in data and len(data['data']) > 0:
            expirations = [exp['expirationDate'] for exp in data['data']]
            set_cached_data(cache_key, expirations)
            return expirations
        else:
            logging.error(f"No option expiration dates found for {ticker}")
            return []
            
    except Exception as e:
        logging.error(f"Error getting option expirations for {ticker}: {str(e)}")
        return []

def get_option_chain(ticker, expiry):
    """
    Get option chain for a specific expiration date
    """
    cache_key = get_cache_key("option_chain", ticker, expiry)
    cached_data = get_cached_data(cache_key)
    if cached_data is not None:
        return cached_data
    
    try:
        url = f"https://finnhub.io/api/v1/stock/option-chain"
        params = {
            'symbol': ticker.upper(),
            'token': FINNHUB_API_KEY
        }
        
        response = requests.get(url, params=params)
        data = response.json()
        
        # Find the specific expiration date in the data
        option_data = None
        for exp_data in data.get('data', []):
            if exp_data['expirationDate'] == expiry:
                option_data = exp_data
                break
        
        if option_data:
            set_cached_data(cache_key, option_data)
            return option_data
        else:
            logging.error(f"No options found for {ticker} with expiry {expiry}")
            return None
            
    except Exception as e:
        logging.error(f"Error getting option chain for {ticker} with expiry {expiry}: {str(e)}")
        return None

def get_option_price_history(ticker, option_symbol, timeframe='1d', interval='15m'):
    """
    Simulate option price history based on stock data since Finnhub free tier 
    doesn't provide historical option prices
    """
    # In the free tier, Finnhub doesn't provide historical option prices
    # This is a simplified simulation based on stock price movement
    # You would replace this with actual option price history in a paid API
    
    try:
        # Get the stock price history
        stock_data = get_stock_data(ticker, timeframe, interval)
        
        if stock_data.empty:
            return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])
        
        # Create a simulated option price DataFrame
        # This is a very simplified model - real option prices have complex determinants
        option_data = pd.DataFrame(index=stock_data.index)
        
        # Determine if call or put based on option symbol (simplified)
        is_call = 'C' in option_symbol.upper()
        
        # Get the current stock price and option strike from the symbol
        # Parsing the option symbol - this is a simplified example
        parts = option_symbol.split('_')
        if len(parts) >= 2:
            try:
                strike = float(parts[1])
            except:
                # Default to slightly OTM option
                current_price = stock_data['Close'].iloc[-1]
                strike = round(current_price * (1.05 if is_call else 0.95), 1)
        else:
            # Default to slightly OTM option
            current_price = stock_data['Close'].iloc[-1]
            strike = round(current_price * (1.05 if is_call else 0.95), 1)
        
        # Very simplified option pricing model based on intrinsic value + time value
        # This is NOT an accurate model, just for visualization purposes
        for idx in stock_data.index:
            stock_price = stock_data.loc[idx, 'Close']
            days_to_expiry = 30  # Assumed constant days to expiry for simplicity
            
            # Intrinsic value
            if is_call:
                intrinsic = max(0, stock_price - strike)
            else:
                intrinsic = max(0, strike - stock_price)
            
            # Simplified time value (decreases as expiry approaches)
            time_value = stock_price * 0.05 * (days_to_expiry / 365)
            
            # Option price = intrinsic value + time value
            option_price = intrinsic + time_value
            
            # Add some volatility based on stock movement
            if idx > stock_data.index[0]:
                prev_stock_price = stock_data.loc[stock_data.index[stock_data.index.get_loc(idx) - 1], 'Close']
                pct_change = (stock_price - prev_stock_price) / prev_stock_price
                option_data.loc[idx, 'Open'] = option_price * (1 - pct_change * 2)
                option_data.loc[idx, 'High'] = option_price * (1 + abs(pct_change) * 3)
                option_data.loc[idx, 'Low'] = option_price * (1 - abs(pct_change) * 3)
                option_data.loc[idx, 'Close'] = option_price
            else:
                option_data.loc[idx, 'Open'] = option_price * 0.98
                option_data.loc[idx, 'High'] = option_price * 1.02
                option_data.loc[idx, 'Low'] = option_price * 0.97
                option_data.loc[idx, 'Close'] = option_price
            
            # Simulated volume - proportional to stock volume
            option_data.loc[idx, 'Volume'] = stock_data.loc[idx, 'Volume'] // 100
        
        return option_data
        
    except Exception as e:
        logging.error(f"Error simulating option price history: {str(e)}")
        return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])

def get_option_data(ticker, option_type, expiry=None, strike=None, timeframe='1d', interval='15m'):
    """
    Get option data with fallbacks and error handling
    """
    try:
        # If no expiry provided, get the nearest expiration date
        if not expiry:
            expirations = get_option_expirations(ticker)
            if not expirations:
                logging.warning(f"No option expiration dates found for {ticker}")
                return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])
            
            # Sort and get the nearest expiration
            expirations.sort()
            expiry = expirations[0]
            logging.info(f"Using nearest expiry date: {expiry}")
        
        # Get option chain for this expiry
        option_chain = get_option_chain(ticker, expiry)
        if not option_chain:
            return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])
        
        # Filter by option type
        if option_type.lower() == 'c':
            options = option_chain.get('call', [])
        elif option_type.lower() == 'p':
            options = option_chain.get('put', [])
        else:
            logging.error(f"Invalid option type: {option_type}")
            return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])
        
        # If no options found
        if not options:
            logging.warning(f"No {option_type} options found for {ticker} with expiry {expiry}")
            return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])
        
        # If no strike specified, find ATM option
        if not strike:
            # Get current stock price
            stock_data = get_stock_data(ticker, '1d', '15m')
            if not stock_data.empty:
                current_price = stock_data['Close'].iloc[-1]
                
                # Find closest strike to current price
                closest_option = min(options, key=lambda x: abs(float(x.get('strike', 0)) - current_price))
                strike = float(closest_option.get('strike', 0))
                logging.info(f"Using closest strike to current price: {strike}")
            else:
                # If we can't get current price, use the middle strike
                strikes = [float(opt.get('strike', 0)) for opt in options]
                strike = strikes[len(strikes) // 2]
                logging.info(f"Using middle strike: {strike}")
        
        # Find the option with the specified strike
        option = None
        for opt in options:
            if float(opt.get('strike', 0)) == float(strike):
                option = opt
                break
        
        if not option:
            logging.warning(f"No option found with strike {strike}")
            closest_option = min(options, key=lambda x: abs(float(x.get('strike', 0)) - float(strike)))
            option = closest_option
            strike = float(option.get('strike', 0))
            logging.info(f"Using closest available strike: {strike}")
        
        # Get the option symbol
        option_symbol = option.get('contractName', f"{ticker}_{strike}_{option_type}_{expiry}")
        
        # Get option price history (simulated in free tier)
        option_data = get_option_price_history(ticker, option_symbol, timeframe, interval)
        
        return option_data
        
    except Exception as e:
        logging.error(f"Error getting option data: {str(e)}")
        return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])

def prepare_table_data(data):
    """Format data for the Dash DataTable"""
    table_data = []
    if not data.empty:
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
        '1d': [{'label': i, 'value': i} for i in ['1m', '5m', '15m', '30m', '1h', '1d']],
        '5d': [{'label': i, 'value': i} for i in ['5m', '15m', '30m', '1h', '1d']],
        '1mo': [{'label': i, 'value': i} for i in ['15m', '30m', '1h', '1d', '1wk']],
        '3mo': [{'label': i, 'value': i} for i in ['1h', '1d', '1wk']],
        '6mo': [{'label': i, 'value': i} for i in ['1d', '1wk']],
        '1y': [{'label': i, 'value': i} for i in ['1d', '1wk', '1mo']],
        '2y': [{'label': i, 'value': i} for i in ['1d', '1wk', '1mo']],
        '5y': [{'label': i, 'value': i} for i in ['1d', '1wk', '1mo']],
        'max': [{'label': i, 'value': i} for i in ['1d', '1wk', '1mo']],
    }
    
    stock_intervals = interval_options.get(stock_timeframe, [{'label': i, 'value': i} for i in ['15m', '1h', '1d']])
    option_intervals = interval_options.get(option_timeframe, [{'label': i, 'value': i} for i in ['15m', '1h', '1d']])
    
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
    
    ctx = dash.callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None

    # Initialize outputs
    stock_fig = go.Figure()
    option_fig = go.Figure()
    option_table_data = []
    alerts = []  # Initialize alerts list
    
    # Set default intervals if None
    stock_interval = stock_interval or '15m'
    option_interval = option_interval or '15m'
    
    # Determine if the market is open
    market_open = is_market_open()
    
    # Set interval based on market status
    if market_open:
        update_interval = 60000  # 1 minute interval when market is open
    else:
        update_interval = 300000  # 5 minutes interval when market is closed
        alerts.append(html.Div('Market is currently closed - updates less frequent', style={'color': 'orange'}))
    
    # Add API credit/usage warning
    alerts.append(html.Div('Using Finnhub API with rate limits (60 calls/minute)', style={'color': 'blue'}))
    
    # Only update data if user input changed or if market is open and interval update triggered
    if triggered_id != 'interval-component' or (triggered_id == 'interval-component' and market_open):
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