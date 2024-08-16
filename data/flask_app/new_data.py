from flask import Flask
from config import Config
from models import db, Stock, StockHistory
import yfinance as yf

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

 
#Given a stock that exists in our database this functions adds in the the last 5 days of  stockhistory is if it exists
def import_past_5_days_data():
    
    # Fetch stock data from yfinance for the last 5 days  
    # Start a transaction block 
    with app.app_context():
        with db.session.begin(): 

            stocks = Stock.query.all() 
            for stock in stocks: 
                    print(stock.symbol) 
                    last_Five_days = yf.download(stock.symbol, period="2y")  
                    relevant = last_Five_days[['Open', 'High', 'Low', 'Close', 'Volume']]
                    for index, row in relevant.iterrows():
                        timestamp = index
                        open_price =float(row['Open']) 
                        high_price = float(row['High'])
                        low_price = float(row['Low'])
                        close_price = float(row['Close'])
                        volume = float(row['Volume'])
                        
                        # Check if the stock history already exists
                        stock_history = db.session.query(StockHistory).filter_by(symbol=stock.symbol, timestamp=timestamp).first()
                        if not stock_history:
                            new_history = StockHistory(
                                symbol=stock.symbol,
                                timestamp=timestamp,
                                high=high_price,
                                low=low_price,
                                open=open_price,
                                close=close_price,
                                volume=volume
                            )
                            db.session.add(new_history)
            db.session.commit()

if __name__ == '__main__':
    import_past_5_days_data()

