import os
import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from flask import Flask
from config import Config
from models import db, Stock, StockHistory
import yfinance as yf

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

def get_stock_name(symbol):
    try:
        stock_info = yf.Ticker(symbol).info
        return stock_info.get('shortName', symbol)  # Fallback to symbol if name is not available
    except Exception as e:
        print(f"Error fetching stock name for {symbol}: {e}")
        return symbol

def import_data():
    csv_file_path = os.path.join(os.path.dirname(__file__), 'SP500History.csv')
    with open(csv_file_path, 'r') as file:
        reader = csv.reader(file)
        next(reader)  # Skip header row
        for row in reader:
            timestamp_str, open_price, high_price, low_price, close_price, volume, symbol = row
            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d')
            
            # Handle missing values and convert to Decimal or None
            try:
                open_price = Decimal(open_price) if open_price else None
                high_price = Decimal(high_price) if high_price else None
                low_price = Decimal(low_price) if low_price else None
                close_price = Decimal(close_price) if close_price else None
            except InvalidOperation:
                open_price = high_price = low_price = close_price = None

            # Start a transaction block
            with db.session.begin():
                # Use Session.get() instead of Query.get()
                stock = db.session.get(Stock, symbol)
                if not stock:
                    stock_name = get_stock_name(symbol)
                    stock = Stock(symbol=symbol, name=stock_name)
                    db.session.add(stock)

                # Check if the stock history already exists
                stock_history = db.session.query(StockHistory).filter_by(symbol=symbol, timestamp=timestamp).first()
                if not stock_history:
                    stock_history = StockHistory(
                        symbol=symbol,
                        timestamp=timestamp,
                        high=high_price,
                        low=low_price,
                        open=open_price,
                        close=close_price,
                        volume=volume if volume else None
                    )
                    db.session.add(stock_history)

    db.session.commit()

if __name__ == '__main__':
    with app.app_context():
        import_data()
