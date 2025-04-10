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
import os

import pandas_datareader as pdr
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize Dash app
app = dash.Dash(__name__)

# List of options for time interval and timeframe
time_intervals = ['1m', '2m', '5m', '15m', '30m', '1h', '1d', '5d', '1wk', '1mo', '3mo']
timeframes = ['1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'max']

# Layout of the app
app.layout = html.Div([
    html.H1('Real-Time Stock Dashboard', style={'textAlign': 'center'}),
    
    html.Div([
        html.Div([
            # Removed the html.H2('Stock') component
            dcc.Input(
                id='stock-ticker-input', 
                type='text', 
                value='NVDA', 
                placeholder='Enter Stock Ticker Symbol (e.g., aapl)', 
                style={'width': '50%', 'margin': '10px auto', 'display': 'block', 'height': '36px'}
            ),
            dcc.Dropdown(
                id='stock-timeframe-dropdown', 
                options=[{'label': i, 'value': i} for i in timeframes], 
                value='1d', 
                placeholder='Select Timeframe', 
                style={'width': '50%', 'margin': '10px auto'}
            ),
            dcc.Dropdown(
                id='stock-interval-dropdown', 
                options=[{'label': i, 'value': i} for i in time_intervals], 
                value='1m', 
                placeholder='Select Interval', 
                style={'width': '50%', 'margin': '10px auto'}
            ),
            html.Div(id='alerts-container', style={'margin': '10px auto', 'textAlign': 'center'}),
            dcc.Graph(id='stock-plot', style={'height': '70vh', 'width': '100%'}),
        ], style={'width': '80%', 'margin': '0 auto', 'display': 'block'}),
    ]),
    
    dcc.Interval(
        id='interval-component',
        interval=60*1000,  # in milliseconds (default update every minute)
        n_intervals=0
    )
])

def get_stock_data(ticker, period='1y', interval='1d'):
    stock = yf.Ticker(ticker)
    stock_data = stock.history(period=period, interval=interval)
    return stock_data

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

def plot_data(data, title):
    fig = go.Figure()
    if 'Close' in data.columns:
        if len(data) > 0:  # Check if data is not empty
            color = 'green' if data['Close'].iloc[-1] >= data['Close'].iloc[0] else 'red'
            fig.add_trace(go.Scatter(x=data.index, y=data['Close'], mode='lines+markers', line=dict(color=color), name='Close'))

            # Adding simple moving averages (SMAs)
            data['SMA_10'] = data['Close'].rolling(window=10).mean()
            data['SMA_20'] = data['Close'].rolling(window=20).mean()
            data['SMA_7'] = data['Close'].rolling(window=7).mean()
            data['SMA_50'] = data['Close'].rolling(window=50).mean()

            fig.add_trace(go.Scatter(x=data.index, y=data['SMA_7'], mode='lines', line=dict(color='blue'), name='SMA 7'))
            fig.add_trace(go.Scatter(x=data.index, y=data['SMA_50'], mode='lines', line=dict(color='purple'), name='SMA 50'))
            fig.add_trace(go.Scatter(x=data.index, y=data['SMA_10'], mode='lines', line=dict(color='pink'), name='SMA 10'))
            fig.add_trace(go.Scatter(x=data.index, y=data['SMA_20'], mode='lines', line=dict(color='black'), name='SMA 20'))

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
        xaxis_rangeslider_visible=False,  # Remove the range slider
        xaxis_range=[data.index[0], data.index[-1]],  # Set the x-axis range to the data range
        yaxis_title='Price',
        margin=dict(l=50, r=20, t=50, b=50),  # Adjust the margins
        autosize=True,  # Automatically size the plot area
    )
    
    return fig

@app.callback(
    Output('stock-interval-dropdown', 'options'),
    Input('stock-timeframe-dropdown', 'value'),
)
def update_intervals(stock_timeframe):
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
    
    return stock_intervals

@app.callback(
    Output('stock-plot', 'figure'),
    Output('alerts-container', 'children'),
    Output('interval-component', 'interval'),

    Input('interval-component', 'n_intervals'),
    Input('stock-ticker-input', 'value'),
    Input('stock-timeframe-dropdown', 'value'),
    Input('stock-interval-dropdown', 'value'),
)

def update_data_and_plot(n_intervals, stock_ticker, stock_timeframe, stock_interval):
    
    ctx = dash.callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None

    # Initialize outputs
    stock_fig = go.Figure()
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
    stock_interval = stock_interval or default_intervals.get(stock_timeframe)
    
    # Determine if the market is open
    market_open = is_market_open()
    
    # Set interval based on market status
    if market_open:
        update_interval = 60000  # 1 minute interval when market is open
    else:
        update_interval = 259200000  # 3 day interval when market is closed

    # Only update data if user input changed or if market is open and interval update triggered
    if triggered_id != 'interval-component' or (triggered_id == 'interval-component' and market_open):
        if stock_ticker:
            stock_data = get_stock_data(stock_ticker, stock_timeframe, stock_interval)
            stock_data['SMA_50'] = stock_data['Close'].rolling(window=50).mean()  # Ensure SMA_50 is calculated
            stock_data['SMA_20'] = stock_data['Close'].rolling(window=20).mean()
            stock_data['SMA_7'] = stock_data['Close'].rolling(window=7).mean()
            stock_data['HMA_6'] = ((2 * stock_data['Close'].rolling(window=3).mean() - stock_data['Close'].rolling(window=6).mean()).rolling(window=int(6**0.5)).mean())

            stock_fig = plot_data(stock_data, 'Stock')
            
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

    # Ensure alerts is not empty even if there are no alerts
    alerts_content = html.Div(alerts) if alerts else []

    return stock_fig, alerts_content, update_interval

# Run the Dash app
if __name__ == '__main__':
    app.run_server(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
else:
    server = app.server