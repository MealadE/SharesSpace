from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    username = db.Column(db.String(64), primary_key=True)
    full_name = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(128), unique=True, nullable=False)
    password = db.Column(db.String(512), nullable=False)

class Portfolio(db.Model):
    __tablename__ = 'portfolio'
    pid = db.Column(db.Integer, primary_key=True)
    pname = db.Column(db.String(128), nullable=False)
    userid = db.Column(db.String(64), db.ForeignKey('users.username'), nullable=False)
    user = db.relationship('User', backref=db.backref('portfolios', lazy=True))
    
    # Adjust the foreign_keys argument to resolve ambiguity
    records = db.relationship('PortfolioRecords', 
                              foreign_keys='PortfolioRecords.pid',
                              back_populates='portfolio')

class Stock(db.Model):
    __tablename__ = 'stock'
    symbol = db.Column(db.String(10), primary_key=True)
    name = db.Column(db.String(128), nullable=False)

class PortfolioHolding(db.Model):
    __tablename__ = 'portfolioholding'
    pid = db.Column(db.Integer, db.ForeignKey('portfolio.pid'), primary_key=True)
    symbol = db.Column(db.String(10), db.ForeignKey('stock.symbol'), primary_key=True)
    volume = db.Column(db.Integer, nullable=False)
    portfolio = db.relationship('Portfolio', backref=db.backref('holdings', lazy=True))
    stock = db.relationship('Stock', backref=db.backref('holdings', lazy=True))
    
class CashAccount(db.Model):
    __tablename__ = 'cashaccount'
    pid = db.Column(db.Integer, db.ForeignKey('portfolio.pid'), primary_key=True)
    balance = db.Column(db.Numeric(15, 3), nullable=False)
    username = db.Column(db.String(64), db.ForeignKey('users.username'), primary_key=True)
    portfolio = db.relationship('Portfolio', backref=db.backref('cash_account', uselist=False))
    user = db.relationship('User', backref=db.backref('cash_account', uselist=False))

    def __init__(self, pid, balance, username):
        self.pid = pid
        self.balance = round(balance, 3)
        self.username = username

class StockList(db.Model):
    __tablename__ = 'stocklist'
    slid = db.Column(db.Integer, primary_key=True)
    slname = db.Column(db.String(128), nullable=False)
    publicity = db.Column(db.String(64), nullable=False)

class SLOwners(db.Model):
    __tablename__ = 'slowners'
    slid = db.Column(db.Integer, db.ForeignKey('stocklist.slid'), primary_key=True)
    username = db.Column(db.String(64), db.ForeignKey('users.username'), primary_key=True)
    stock_list = db.relationship('StockList', backref=db.backref('owners', lazy=True))
    user = db.relationship('User', backref=db.backref('stock_list_owners', lazy=True))

class SLConsists(db.Model):
    __tablename__ = 'slconsists'
    slid = db.Column(db.Integer, db.ForeignKey('stocklist.slid'), primary_key=True)
    symbol = db.Column(db.String(10), db.ForeignKey('stock.symbol'), primary_key=True)
    volume = db.Column(db.Integer, nullable=False)
    stock_list = db.relationship('StockList', backref=db.backref('stock_consists', lazy=True))
    stock = db.relationship('Stock', backref=db.backref('stock_lists', lazy=True))
    
class StockHistory(db.Model):
    __tablename__ = 'stockhistory'
    symbol = db.Column(db.String(10), db.ForeignKey('stock.symbol'), primary_key=True)
    timestamp = db.Column(db.DateTime, primary_key=True)
    high = db.Column(db.Numeric)
    low = db.Column(db.Numeric)
    open = db.Column(db.Numeric)
    close = db.Column(db.Numeric)
    volume = db.Column(db.Numeric)
    stock = db.relationship('Stock', backref=db.backref('historical_data', lazy=True))

class Friends(db.Model):
    __tablename__ = 'friends'
    user_id1 = db.Column(db.String(64), db.ForeignKey('users.username'), primary_key=True)
    user_id2 = db.Column(db.String(64), db.ForeignKey('users.username'), primary_key=True)
    type = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)

    # Ensure consistent ordering of UserID1 and UserID2
    __table_args__ = (db.UniqueConstraint('user_id1', 'user_id2', name='unique_friendship'),)

    user1 = db.relationship('User', foreign_keys=[user_id1], backref=db.backref('friends1', lazy='dynamic'))
    user2 = db.relationship('User', foreign_keys=[user_id2], backref=db.backref('friends2', lazy='dynamic'))

class PortfolioRecords(db.Model):
    __tablename__ = 'portfoliorecords'
    record_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    pid = db.Column(db.Integer, db.ForeignKey('portfolio.pid'), nullable=False)
    action_type = db.Column(db.String(64), nullable=False)
    symbol = db.Column(db.String(10), db.ForeignKey('stock.symbol'), nullable=True)
    volume = db.Column(db.Integer, nullable=True)
    amount = db.Column(db.Numeric(15, 3), nullable=True)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp(), nullable=False)
    destination_pid = db.Column(db.Integer, db.ForeignKey('portfolio.pid'), nullable=True)
    
    # Specify foreign_keys for each relationship
    portfolio = db.relationship('Portfolio', 
                                foreign_keys=[pid], 
                                back_populates='records')
    stock = db.relationship('Stock', backref=db.backref('records', lazy=True))
    destination_portfolio = db.relationship('Portfolio', 
                                            foreign_keys=[destination_pid], 
                                            backref='incoming_records')

class SharedSL(db.Model):
    __tablename__ = 'sharedsl'
    slid = db.Column(db.Integer, db.ForeignKey('stocklist.slid'), primary_key=True)
    username = db.Column(db.String(64), db.ForeignKey('users.username'), primary_key=True)
    stock_list = db.relationship('StockList', backref=db.backref('shared_with', lazy=True))
    user = db.relationship('User', backref=db.backref('shared_stock_lists', lazy=True))

class SLReviews(db.Model):
    __tablename__ = 'slreviews'
    slid = db.Column(db.Integer, db.ForeignKey('stocklist.slid'), primary_key=True)
    username = db.Column(db.String(64), db.ForeignKey('users.username'), primary_key=True)
    review = db.Column(db.Text, nullable=False)
    rating = db.Column(db.Numeric(3, 1), nullable=False)  # Rating out of 10 with one decimal place

    # Relationships
    stock_list = db.relationship('StockList', backref=db.backref('reviews', lazy=True))
    user = db.relationship('User', backref=db.backref('reviews', lazy=True))
