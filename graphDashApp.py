
# STILL HAVE TO CHANGE BEAUTIFUL SOUP TO SELENIUM.

import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output, State
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, time, timedelta
import holidays
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize Dash app
app = dash.Dash(__name__)

# List of options for time interval and timeframe
time_intervals = ['1m', '2m', '5m', '15m', '30m', '1h', '1d', '5d', '1wk', '1mo', '3mo']
timeframes = ['1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'max']

# Layout of the app
app.layout = html.Div([
    html.H1('Real-Time Stock-Option Pair Dashboard', style={'textAlign': 'center'}),
    
    html.Div([
        html.Div([
            html.H2('Stock'),
            dcc.Input(id='stock-ticker-input', type='text', value='NVDA', placeholder='Enter Stock Ticker Symbol (e.g., aapl)', style={'width': '50%'}),
            dcc.Dropdown(id='stock-timeframe-dropdown', options=[{'label': i, 'value': i} for i in timeframes], value='1d', placeholder='Select Timeframe', style={'width': '50%'}),
            dcc.Dropdown(id='stock-interval-dropdown', options=[{'label': i, 'value': i} for i in time_intervals], value='1m', placeholder='Select Interval', style={'width': '50%'}),
            html.Div(id='alerts-container'),
            dcc.Graph(id='stock-plot', style={'height': '70vh', 'width': '100%'}),
        ], style={'width': '60%', 'display': 'inline-block', 'vertical-align': 'top'}),
        
        html.Div([
            html.H2('Option'),
            dcc.Input(id='option-ticker-input', type='text', value='NVDA', placeholder='Enter Stock Ticker (e.g., aapl)', style={'width': '90%'}),
            dcc.Input(id='option-type-input', type='text', value ='c', placeholder='Enter Option Type (c or p)', style={'width': '90%'}),
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
        ], style={'width': '40%', 'display': 'inline-block', 'vertical-align': 'top'}),
    ]),
    
    dcc.Interval(
        id='interval-component',
        interval=60*1000,  # in milliseconds (default update every minute)
        n_intervals=0
    )
])

def is_market_open():
    current_time = datetime.now()
    market_open_time = time(9, 30) # Market opens at 9:30 AM
    market_close_time = time(16, 0) # Market closes at 4:00 PM
    
    us_holidays = holidays.US()  # Initialize US holidays
    
    if current_time.date() in us_holidays:
        return False
    if current_time.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
        return False
    if market_open_time <= current_time.time() <= market_close_time:
        return True
    return False

def get_stock_data(ticker, period='1d', interval='1m'):
    """
    Get stock data with error handling and retries
    """
    try:
        stock = yf.Ticker(ticker)
        stock_data = stock.history(period=period, interval=interval)
        
        # Check if data is empty and try with a different period if needed
        if stock_data.empty and period == '1d':
            logging.warning(f"No data found for {ticker} with period=1d, trying with period=5d")
            stock_data = stock.history(period='5d', interval=interval)
        
        # If still empty, try with a different interval
        if stock_data.empty and interval == '1m':
            logging.warning(f"No data found for {ticker} with interval=1m, trying with interval=1h")
            stock_data = stock.history(period=period, interval='1h')
        
        # Last resort, get any available data
        if stock_data.empty:
            logging.warning(f"No data found for {ticker} with specified parameters, getting any available data")
            stock_data = stock.history(period='1mo', interval='1d')
            
        if stock_data.empty:
            logging.error(f"Could not get any data for ticker {ticker}")
            # Return an empty DataFrame with the expected columns
            return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])
            
        return stock_data
    
    except Exception as e:
        logging.error(f"Error getting data for {ticker}: {e}")
        # Return an empty DataFrame with the expected columns
        return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])

def get_option_data(ticker, option_type, expiry, strike, timeframe='1d', interval='1m'):
    """
    Get option data with error handling
    """
    try:
        stock = yf.Ticker(ticker)
        
        # Get all available option expiry dates if none provided
        if not expiry:
            expirations = stock.options
            if not expirations:
                logging.error(f"No options available for {ticker}")
                return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])
            expiry = expirations[0]  # Use the first available date
            
        option_chain = stock.option_chain(expiry)
        
        if option_type.lower() == 'c':
            options = option_chain.calls
        elif option_type.lower() == 'p':
            options = option_chain.puts
        else:
            logging.error("Option type must be 'c' for call or 'p' for put")
            return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])
        
        # If no strike provided or strike not in options, use the closest to current price
        if not strike or not options[options['strike'] == strike].shape[0]:
            current_price = stock.info.get('regularMarketPrice', stock.info.get('currentPrice', 0))
            if current_price == 0:
                # If we can't get current price, try to get it from history
                stock_data = stock.history(period='1d')
                if not stock_data.empty:
                    current_price = stock_data['Close'].iloc[-1]
            
            # Find closest strike
            if current_price > 0:
                options['diff'] = abs(options['strike'] - current_price)
                strike = options.loc[options['diff'].idxmin(), 'strike']
                options = options[options['strike'] == strike]
            else:
                # If still no valid price, use the middle option
                if not options.empty:
                    middle_idx = len(options) // 2
                    strike = options.iloc[middle_idx]['strike']
                    options = options[options['strike'] == strike]
        else:
            options = options[options['strike'] == strike]
        
        if options.empty:
            logging.error(f"No option found for ticker {ticker} with strike {strike}")
            return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])
        
        option = options.iloc[0]
        option_symbol = option['contractSymbol']
        
        try:
            option_data = yf.Ticker(option_symbol).history(period=timeframe, interval=interval)
            
            # If data is empty, try with different parameters
            if option_data.empty:
                option_data = yf.Ticker(option_symbol).history(period='1mo', interval='1d')
                
            return option_data
        except Exception as e:
            logging.error(f"Error getting option data for {option_symbol}: {e}")
            return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])
    
    except Exception as e:
        logging.error(f"Error getting option chain for {ticker}: {e}")
        return pd.DataFrame(columns=['Open', 'High', 'Low', 'Close', 'Volume'])

def prepare_table_data(data):
    table_data = []
    if not data.empty:
        for idx, row in data.iterrows():
            table_data.append({
                'Date': idx.strftime('%Y-%m-%d %H:%M:%S'),
                'Close': row['Close'] if 'Close' in row else 'N/A',
                'Volume': row['Volume'] if 'Volume' in row else 'N/A'
            })
        # Sort by most recent first
        table_data.sort(key=lambda x: x['Date'], reverse=True)
    return table_data

def plot_data(data, title, is_option=False):
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
        data['SMA_10'] = data['Close'].rolling(window=10).mean()
        fig.add_trace(go.Scatter(x=data.index, y=data['SMA_10'], mode='lines', line=dict(color='pink'), name='SMA 10'))
    
    if len(data) >= 20:
        data['SMA_20'] = data['Close'].rolling(window=20).mean()
        fig.add_trace(go.Scatter(x=data.index, y=data['SMA_20'], mode='lines', line=dict(color='black'), name='SMA 20'))

    if not is_option:  # For stock plot
        if len(data) >= 7:
            data['SMA_7'] = data['Close'].rolling(window=7).mean()
            fig.add_trace(go.Scatter(x=data.index, y=data['SMA_7'], mode='lines', line=dict(color='blue'), name='SMA 7'))
        
        if len(data) >= 50:
            data['SMA_50'] = data['Close'].rolling(window=50).mean()
            fig.add_trace(go.Scatter(x=data.index, y=data['SMA_50'], mode='lines', line=dict(color='purple'), name='SMA 50'))

        # Calculate Hull Moving Average (HMA) if enough data
        if len(data) >= 6:
            wma_half = data['Close'].rolling(window=3).mean()
            wma_full = data['Close'].rolling(window=6).mean()
            hma = (2 * wma_half - wma_full).rolling(window=int(6**0.5)).mean()
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
    
    stock_intervals = interval_options.get(stock_timeframe, [{'label': i, 'value': i} for i in time_intervals])
    option_intervals = interval_options.get(option_timeframe, [{'label': i, 'value': i} for i in time_intervals])
    
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
    
    ctx = dash.callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None

    # Initialize outputs
    stock_fig = go.Figure()
    option_fig = go.Figure()
    option_table_data = []
    alerts = []  # Initialize alerts list
    
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
    stock_interval = stock_interval or default_intervals.get(stock_timeframe, '1d')
    option_interval = option_interval or default_intervals.get(option_timeframe, '1d')
    
    # Determine if the market is open
    market_open = is_market_open()
    
    # Set interval based on market status
    if market_open:
        update_interval = 60000  # 1 minute interval when market is open
    else:
        update_interval = 3600000  # 1 hour interval when market is closed
        alerts.append(html.Div('Market is currently closed - updates less frequent', style={'color': 'orange'}))
    
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
                        alerts.append(html.Div(f'Enter expiry date and strike price for options', style={'color': 'orange'}))
            except Exception as e:
                logging.error(f"Error processing option data: {e}")
                option_fig = plot_data(pd.DataFrame(columns=['Close']), f'Error loading option data')
                alerts.append(html.Div(f'Error loading options: {str(e)}', style={'color': 'red'}))

    # Ensure alerts is not empty even if there are no alerts
    alerts_content = html.Div(alerts) if alerts else []

    return stock_fig, option_fig, option_table_data, alerts_content, update_interval

# Run the Dash app
if __name__ == '__main__':
    app.run_server(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
else:
    server = app.server