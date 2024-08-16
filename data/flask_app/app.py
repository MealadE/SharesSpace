from flask import Flask, request, redirect, url_for, render_template, flash, session, jsonify
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, FloatField, IntegerField
from wtforms.validators import DataRequired, Length, EqualTo, NumberRange
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Portfolio, CashAccount, StockList, SLOwners, PortfolioHolding, SLConsists, Stock, StockHistory, Friends, PortfolioRecords, SharedSL, SLReviews  # Add Friends model
from config import Config
from sqlalchemy import extract, text, func
from flask_migrate import Migrate
from decimal import Decimal, getcontext
import yfinance as yf
from datetime import datetime, timedelta
from sklearn.linear_model import LinearRegression
import numpy as np
import pandas as pd
from sqlalchemy.orm import joinedload, sessionmaker
from flask_caching import Cache
from collections import defaultdict

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)
app.config['CACHE_TYPE'] = 'simple'  # Use 'redis' or 'filesystem' for production
app.config['CACHE_DEFAULT_TIMEOUT'] = 3600  # Cache timeout in seconds

cache = Cache(app)
migrate = Migrate(app, db)


def get_date_range(period):
    end_date = datetime.now()
    
    if period == '1w':
        start_date = end_date - timedelta(weeks=1)
    elif period == '1m':
        start_date = end_date - timedelta(days=30)
    elif period == '3m':
        start_date = end_date - timedelta(days=90)
    elif period == '1y':
        start_date = end_date - timedelta(days=365)
    elif period == '5y':
        start_date = end_date - timedelta(days=1825)
    else:
        start_date = None
    
    return start_date, end_date

@cache.memoize(timeout=3600)
def get_stock_cv(symbol):
    # Fetch the historical closing prices
    prices = db.session.query(StockHistory.close).filter_by(symbol=symbol).all()
    prices = [float(price[0]) for price in prices]  # Convert Decimal to float

    if not prices:
        return None
    
    mean_price = np.mean(prices)
    stddev = np.std(prices)
    
    if mean_price == 0:  # Avoid division by zero
        return None
    
    cv = stddev / mean_price
    return cv

@cache.memoize(timeout=3600)
def fetch_index_data(index_symbol='^GSPC', start_date=None, end_date=None):
    index_data = yf.download(index_symbol, start=start_date, end=end_date)
    index_data = index_data['Close']
    return index_data

@cache.memoize(timeout=3600)
def calculate_beta(stock_symbol, period='1y', index_symbol='^GSPC'):
    start_date, end_date = get_date_range(period)
    
    # Fetch stock data
    stock_data = db.session.query(StockHistory.timestamp, StockHistory.close).filter_by(symbol=stock_symbol).filter(StockHistory.timestamp >= start_date, StockHistory.timestamp <= end_date).all()
    stock_data = {timestamp: float(close) for timestamp, close in stock_data}

    if not stock_data:
        return None

    # Fetch index data
    index_data = fetch_index_data(index_symbol, start_date, end_date)
    if index_data.empty:
        return None

    # Align stock data with index data
    stock_prices = []
    index_prices = []
    for date in sorted(stock_data.keys()):
        date_str = date.strftime('%Y-%m-%d')
        if date_str in index_data:
            stock_prices.append(stock_data[date])
            index_prices.append(index_data[date_str])

    if len(stock_prices) < 2 or len(index_prices) < 2:
        return None

    # Calculate returns
    stock_returns = np.diff(stock_prices) / stock_prices[:-1]
    index_returns = np.diff(index_prices) / index_prices[:-1]

    # Calculate covariance and variance
    covariance = np.cov(stock_returns, index_returns)[0, 1]
    variance_index = np.var(index_returns)

    if variance_index == 0:
        return None

    beta = covariance / variance_index
    return beta

@cache.memoize(timeout=3600)
def get_aligned_prices(stock_symbols):
    stock_prices = {}
    all_dates = set()

    for symbol in stock_symbols:
        data = db.session.query(StockHistory.timestamp, StockHistory.close).filter_by(symbol=symbol).all()
        stock_prices[symbol] = {timestamp: float(close) for timestamp, close in data}
        all_dates.update(stock_prices[symbol].keys())

    all_dates = sorted(all_dates)
    aligned_prices = {symbol: [] for symbol in stock_symbols}

    for date in all_dates:
        for symbol in stock_symbols:
            aligned_prices[symbol].append(stock_prices[symbol].get(date, np.nan))

    return aligned_prices, all_dates

@cache.memoize(timeout=3600)
def get_covariance_matrix(stock_symbols):
    aligned_prices, _ = get_aligned_prices(stock_symbols)
    price_matrix = np.array([aligned_prices[symbol] for symbol in stock_symbols])
    return np.cov(price_matrix)

@cache.memoize(timeout=3600)
def get_correlation_matrix(cov_matrix):
    if cov_matrix is None or cov_matrix.size == 0:
        return None
    return np.corrcoef(cov_matrix)

def get_portfolio_statistics_data(portfolio_id, period='1y'):
    # Fetch portfolio details
    portfolio = Portfolio.query.get_or_404(portfolio_id)
    
    # Fetch stock holdings
    stock_holdings = db.session.query(
        PortfolioHolding.symbol,
        Stock.name,
        PortfolioHolding.volume
    ).join(Stock, Stock.symbol == PortfolioHolding.symbol).filter(
        PortfolioHolding.pid == portfolio_id
    ).all()
    
    if not stock_holdings:
        return portfolio, [], {}, {}

    stock_symbols = [holding.symbol for holding in stock_holdings]
    coefficient_of_variation = {symbol: get_stock_cv(symbol) for symbol in stock_symbols}
    beta_values = {symbol: calculate_beta(symbol, period) for symbol in stock_symbols}

    return portfolio, stock_holdings, coefficient_of_variation, beta_values



def check_db_connection():
    try:
        with app.app_context():
            db.session.execute(text('SELECT 1'))
            print("Database connection successful!")
    except Exception as e:
        print(f"Error connecting to the database: {e}")


with app.app_context():
    check_db_connection()

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    full_name = StringField('Full Name', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class CreatePortfolioForm(FlaskForm):
    portfolio_name = StringField('Portfolio Name', validators=[DataRequired()])
    submit = SubmitField('Create Portfolio')

class CreateStockListForm(FlaskForm):
    stock_list_name = StringField('Stock List Name', validators=[DataRequired()])
    submit = SubmitField('Create Stock List')

class StockSelectionForm(FlaskForm):
    stock_symbol = SelectField('Stock', choices=[], validators=[DataRequired()])
    submit = SubmitField('View History')

class AddFriendForm(FlaskForm):
    friend_username = StringField('Friend Username', validators=[DataRequired()])
    submit = SubmitField('Add Friend')

class BuySellStockForm(FlaskForm):
    stock_symbol = SelectField('Stock', choices=[], validators=[DataRequired()])
    amount = FloatField('Amount', validators=[DataRequired(), NumberRange(min=0)])
    sell_stock_symbol = SelectField('Sell Stock', choices=[], validators=[DataRequired()])  # Add this line
    submit = SubmitField('Submit')

class SellStockForm(FlaskForm):
    sell_stock_symbol = SelectField('Stock Symbol', coerce=str, validators=[DataRequired()])
    amount = IntegerField('Amount', validators=[DataRequired(), NumberRange(min=1)])
    submit = SubmitField('Sell')

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        try:
            user = User.query.filter_by(username=form.username.data).first()
            if user and check_password_hash(user.password, form.password.data):
                session['username'] = user.username  # Store username in session
                flash('Login successful!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Login failed. Check username and/or password.', 'danger')
        except Exception as e:
            flash(f'An error occurred while logging in: {e}', 'danger')
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        existing_user = User.query.filter_by(username=form.username.data).first()
        if existing_user:
            flash('Username already exists. Please choose a different one.', 'danger')
        else:
            hashed_password = generate_password_hash(form.password.data)
            new_user = User(username=form.username.data, full_name=form.full_name.data,
                            email=form.email.data, password=hashed_password)
            db.session.add(new_user)
            db.session.commit()

            # Create initial portfolio
            portfolio_name = request.form.get('portfolio_name')
            new_portfolio = Portfolio(pname=portfolio_name, userid=new_user.username)
            db.session.add(new_portfolio)
            db.session.commit()

            # Create cash account
            new_cash_account = CashAccount(pid=new_portfolio.pid, balance=0, username=new_user.username)
            db.session.add(new_cash_account)
            db.session.commit()

            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/create_portfolio', methods=['GET', 'POST'])
def create_portfolio():
    form = CreatePortfolioForm()
    if form.validate_on_submit():
        username = session.get('username')
        user = User.query.filter_by(username=username).first()
        if user:
            new_portfolio = Portfolio(pname=form.portfolio_name.data, userid=user.username)
            db.session.add(new_portfolio)
            db.session.commit()

            # Create cash account for the new portfolio
            new_cash_account = CashAccount(pid=new_portfolio.pid, balance=0, username=user.username)
            db.session.add(new_cash_account)
            db.session.commit()

            flash('Portfolio created successfully!', 'success')
            return redirect(url_for('dashboard', username=user.username))
        else:
            flash('User not found.', 'danger')
    return render_template('create_portfolio.html', form=form)

@app.route('/create_stock_list', methods=['GET', 'POST'])
def create_stock_list():
    form = CreateStockListForm()
    if form.validate_on_submit():
        username = session.get('username')
        user = User.query.filter_by(username=username).first()
        if user:
            new_stock_list = StockList(slname=form.stock_list_name.data, publicity='Private')
            db.session.add(new_stock_list)
            db.session.commit()

            # Add entry to SLOwners table
            new_sl_owner = SLOwners(slid=new_stock_list.slid, username=user.username)
            db.session.add(new_sl_owner)
            db.session.commit()

            flash('Stock list created successfully!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('User not found.', 'danger')
    return render_template('create_stock_list.html', form=form)

@app.route('/dashboard', methods=['GET'])
def dashboard():
    username = session.get('username')
    if not username:
        flash('You need to log in first.', 'warning')
        return redirect(url_for('login'))

    user = User.query.filter_by(username=username).first_or_404()
    return render_template('dashboard.html', user=user)

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/stock_history', methods=['GET', 'POST'])
def stock_history():
    form = StockSelectionForm()
    stocks = Stock.query.all()  # Get all stock objects

    form.stock_symbol.choices = [
        (stock.symbol, stock.name if stock.name == stock.symbol else f"{stock.name} - {stock.symbol}")
        for stock in stocks
    ]

    if form.validate_on_submit():
        if 'submit' in request.form:
            stock_symbol = form.stock_symbol.data
            return redirect(url_for('view_stock_history', symbol=stock_symbol))
        elif 'future_prediction' in request.form:
            future_stock_symbol = request.form.get('future_stock_symbol')
            print(f"Future prediction requested for stock symbol: {future_stock_symbol}")  # Debugging statement
            if future_stock_symbol:
                return redirect(url_for('stock_future_prediction', symbol=future_stock_symbol))

    return render_template('stock_history.html', form=form, stocks=stocks)


@app.route('/view_stock_history/<symbol>', methods=['GET'])
def view_stock_history(symbol):
    stock = Stock.query.filter_by(symbol=symbol).first_or_404()
    interval = request.args.get('interval', 'All')

    def get_interval_dates(interval):
        now = datetime.now()
        if interval == 'week':
            return now - timedelta(weeks=1)
        elif interval == 'month':
            return now - timedelta(days=30)
        elif interval == 'quarter':
            return now - timedelta(days=90)
        elif interval == 'year':
            return now - timedelta(days=365)
        elif interval == 'five_years':
            return now - timedelta(days=5*365)
        else:
            return None

    interval_date = get_interval_dates(interval)

    if interval_date:
        history = StockHistory.query.filter(
            StockHistory.symbol == symbol,
            StockHistory.timestamp >= interval_date
        ).order_by(StockHistory.timestamp.desc()).all()
    else:
        history = StockHistory.query.filter_by(symbol=symbol).order_by(StockHistory.timestamp.desc()).all()

    # Order years in descending order
    years = db.session.query(db.extract('year', StockHistory.timestamp).label('year')).distinct().order_by(db.desc('year')).all()
    years = [y.year for y in years]

    # Convert history to JSON
    history_json = [{
        'timestamp': record.timestamp.strftime('%Y-%m-%d'),
        'open': record.open,
        'high': record.high,
        'low': record.low,
        'close': record.close,
        'volume': record.volume
    } for record in history]

    return render_template('view_stock_history.html', stock=stock, history_json=history_json, years=years, selected_interval=interval)

@app.template_filter('number_format')
def number_format(value, decimal_places=2):
    try:
        return f"{float(value):,.{decimal_places}f}"
    except (ValueError, TypeError):
        return value

@app.route('/portfolios', methods=['GET'])
def portfolios():
    username = session.get('username')
    if not username:
        flash('You need to log in first.', 'warning')
        return redirect(url_for('login'))

    user = User.query.filter_by(username=username).first_or_404()
    portfolios = Portfolio.query.filter_by(userid=username).all()
    selected_portfolio_id = request.args.get('portfolio_id')
    selected_portfolio = Portfolio.query.get(selected_portfolio_id) if selected_portfolio_id else None
    cash_account = None
    stock_holdings = []
    portfolio_value = Decimal('0.00')

    if selected_portfolio:
        cash_account = CashAccount.query.filter_by(pid=selected_portfolio.pid).first()

        # Fetch stock holdings
        stock_holdings = db.session.query(
            PortfolioHolding.volume,
            Stock.name,
            Stock.symbol
        ).join(Stock, Stock.symbol == PortfolioHolding.symbol).filter(
            PortfolioHolding.pid == selected_portfolio.pid
        ).all()

        # Calculate portfolio value
        for holding in stock_holdings:
            stock = yf.Ticker(holding.symbol)
            current_price = stock.history(period='1d').tail(1)['Close'].iloc[0]
            portfolio_value += Decimal(current_price) * Decimal(holding.volume)
        
        if cash_account:
            portfolio_value += Decimal(cash_account.balance)

    return render_template('portfolios.html', user=user, portfolios=portfolios,
                           selected_portfolio=selected_portfolio, cash_account=cash_account,
                           stock_holdings=stock_holdings, portfolio_value=portfolio_value)


@app.route('/stocklists', methods=['GET'])
def stocklists():
    username = session.get('username')
    if not username:
        flash('You need to log in first.', 'warning')
        return redirect(url_for('login'))

    user = User.query.filter_by(username=username).first_or_404()

    # Fetch the stock lists owned by the user
    stock_lists = StockList.query.join(SLOwners).filter(SLOwners.username == username).all()

    # Fetch the stock lists shared with the user and include owner information
    shared_stock_lists_query = (db.session.query(StockList, User.username.label('owner_username'))
                                .join(SharedSL, StockList.slid == SharedSL.slid)
                                .join(SLOwners, StockList.slid == SLOwners.slid)
                                .join(User, SLOwners.username == User.username)
                                .filter(SharedSL.username == username)
                                .all())

    # Create a list of tuples (stock_list, owner_username) from the query results
    shared_stock_lists = [(sl, owner_username) for sl, owner_username in shared_stock_lists_query]

    selected_stock_list_id = request.args.get('stock_list_id')
    selected_stock_list = StockList.query.get(selected_stock_list_id) if selected_stock_list_id else None

    # Determine if the user is a viewer or an owner of the selected stock list
    is_owner = selected_stock_list and any(sl.slid == selected_stock_list.slid for sl in stock_lists)
    is_shared = selected_stock_list and any(sl.slid == selected_stock_list.slid for sl, _ in shared_stock_lists)

    # Fetch the owner of the shared stock list if applicable
    shared_owner = None
    if is_shared:
        for sl, owner in shared_stock_lists:
            if sl.slid == selected_stock_list.slid:
                shared_owner = owner
                break

    return render_template('stocklists.html', user=user, stock_lists=stock_lists,
                           shared_stock_lists=shared_stock_lists,
                           selected_stock_list=selected_stock_list,
                           is_owner=is_owner,
                           is_shared=is_shared,
                           shared_owner=shared_owner)




@app.route('/toggle_publicity/<int:stock_list_id>', methods=['POST'])
def toggle_publicity(stock_list_id):
    stock_list = StockList.query.get_or_404(stock_list_id)
    if stock_list.publicity == 'Public':
        stock_list.publicity = 'Private'
        # Remove all users from SharedSL table where the stock list ID matches
        SharedSL.query.filter_by(slid=stock_list_id).delete()
    else:
        stock_list.publicity = 'Public'
    
    db.session.commit()
    return redirect(url_for('stocklists', stock_list_id=stock_list_id))



@app.route('/share_stock_list/<int:stock_list_id>', methods=['GET', 'POST'])
def share_stock_list(stock_list_id):
    username = session.get('username')
    if not username:
        flash('You need to log in first.', 'warning')
        return redirect(url_for('login'))

    stock_list = StockList.query.get_or_404(stock_list_id)
    user = User.query.filter_by(username=username).first_or_404()

    if request.method == 'POST':
        friend_username = request.form['friend_username']
        friend = User.query.filter_by(username=friend_username).first_or_404()
        if not SharedSL.query.filter_by(slid=stock_list_id, username=friend_username).first():
            shared_entry = SharedSL(slid=stock_list_id, username=friend_username)
            db.session.add(shared_entry)
            db.session.commit()
            flash('Stock list shared successfully!', 'success')
        else:
            flash('Stock list already shared with this user.', 'info')
        return redirect(url_for('share_stock_list', stock_list_id=stock_list_id))

    # Get the list of users with whom the stock list has been shared
    shared_users = SharedSL.query.filter_by(slid=stock_list_id).all()
    shared_usernames = {entry.username for entry in shared_users}

    # Get the list of friends
    friends = Friends.query.filter(
        (Friends.user_id1 == username) | (Friends.user_id2 == username),
        Friends.type == 'Friend'
    ).all()

    # Create a list of friends excluding those with whom the stock list has already been shared
    friends_list = [friend.user2 if friend.user_id1 == username else friend.user1 for friend in friends]
    friends_list = [friend for friend in friends_list if friend.username not in shared_usernames]

    # Get the list of users with whom the stock list has been shared
    shared_friends_list = [User.query.filter_by(username=entry.username).first() for entry in shared_users]

    return render_template('share_stock_list.html', stock_list=stock_list, friends=friends_list, shared_friends=shared_friends_list)

@app.route('/remove_friend/<string:friend_username>', methods=['POST'])
def remove_friend(friend_username):
    current_user = session.get('username')

    # Find the friendship entry
    friendship = Friends.query.filter(
        ((Friends.user_id1 == current_user) & (Friends.user_id2 == friend_username)) |
        ((Friends.user_id1 == friend_username) & (Friends.user_id2 == current_user))
    ).first()

    if friendship:
        # Update the status to 'Deleted'
        friendship.status = 'Deleted'
        friendship.timestamp = db.func.current_timestamp()
        db.session.commit()
        flash(f'You have removed {friend_username} from your friends list.', 'success')
    else:
        flash(f'Friendship with {friend_username} does not exist.', 'danger')

    return redirect(url_for('friends'))


@app.route('/transactions', methods=['GET', 'POST'])
def transactions():
    username = session.get('username')
    if not username:
        flash('You need to log in first.', 'warning')
        return redirect(url_for('login'))

    # Fetch portfolios and their cash accounts for the logged-in user
    portfolios = Portfolio.query.filter_by(userid=username).all()
    portfolios_cash = {
        p.pid: {
            'Balance': db.session.execute(text('SELECT Balance FROM CashAccount WHERE PID = :pid'), {'pid': p.pid}).scalar() or 0
        }
        for p in portfolios
    }

    # Initialize balance display
    from_balance = 0
    to_balance = 0

    if request.method == 'POST':
        action = request.form.get('action')
        from_pid = request.form.get('from_portfolio')
        to_pid = request.form.get('to_portfolio')
        amount = float(request.form.get('amount'))

        if action == 'deposit':
            if amount <= 10000:
                db.session.execute(
                    text('UPDATE CashAccount SET Balance = Balance + :amount WHERE PID = :pid'),
                    {'amount': amount, 'pid': from_pid}
                )
                db.session.commit()
                flash('Deposit successful', 'success')

                # Record the deposit action
                record = PortfolioRecords(pid=from_pid, action_type='deposit', amount=amount)
                db.session.add(record)
                db.session.commit()
            else:
                flash('Deposit amount exceeds the limit of $10,000', 'error')
        
        elif action == 'withdraw':
            current_balance = db.session.execute(
                text('SELECT Balance FROM CashAccount WHERE PID = :pid'),
                {'pid': from_pid}
            ).scalar() or 0
            if amount <= current_balance:
                db.session.execute(
                    text('UPDATE CashAccount SET Balance = Balance - :amount WHERE PID = :pid'),
                    {'amount': amount, 'pid': from_pid}
                )
                db.session.commit()
                flash('Withdrawal successful', 'success')

                # Record the withdraw action
                record = PortfolioRecords(pid=from_pid, action_type='withdraw', amount=amount)
                db.session.add(record)
                db.session.commit()
            else:
                flash('Insufficient funds for withdrawal', 'error')
        
        elif action == 'transfer':
            from_balance = db.session.execute(
                text('SELECT Balance FROM CashAccount WHERE PID = :pid'),
                {'pid': from_pid}
            ).scalar() or 0
            if amount <= from_balance:
                db.session.execute(
                    text('UPDATE CashAccount SET Balance = Balance - :amount WHERE PID = :pid'),
                    {'amount': amount, 'pid': from_pid}
                )
                db.session.execute(
                    text('UPDATE CashAccount SET Balance = Balance + :amount WHERE PID = :pid'),
                    {'amount': amount, 'pid': to_pid}
                )
                db.session.commit()
                flash('Transfer successful', 'success')

                # Record the transfer action
                record = PortfolioRecords(pid=from_pid, action_type='transfer', amount=amount, destination_pid=to_pid)
                db.session.add(record)
                db.session.commit()
            else:
                flash('Insufficient funds for transfer', 'error')
        
        # Re-fetch updated balances after transactions
        portfolios_cash = {
            p.pid: {
                'Balance': db.session.execute(text('SELECT Balance FROM CashAccount WHERE PID = :pid'), {'pid': p.pid}).scalar() or 0
            }
            for p in portfolios
        }

        from_balance = portfolios_cash.get(from_pid, {}).get('Balance', 0)
        to_balance = portfolios_cash.get(to_pid, {}).get('Balance', 0)

    return render_template(
        'transactions.html',
        portfolios=portfolios,
        portfolios_cash=portfolios_cash,
        from_balance=from_balance,
        to_balance=to_balance
    )

#so all i need to do here is that i need to add another checker that if you are sendin a friend request it checks
#if you already have one that is rejected and the timestamp is more than 5 minutes ago which it then goes and changes
# changes that to have a status of pending adn the timestamp to the new friend request or it deletes the old entry and adds a whole new one

@app.route('/friends', methods=['GET', 'POST'])
def friends():
    form = AddFriendForm()
    current_user = session.get('username')

    if form.validate_on_submit():
        friend_username = form.friend_username.data
        existing_user = User.query.filter_by(username=friend_username).first()

        # Check if the user is trying to add themselves
        if friend_username == current_user:
            flash('You cannot send a friend request to yourself.', 'danger')
        # Check if the user exists
        elif not existing_user:
            flash(f'User {friend_username} does not exist or is invalid', 'danger')
        else:
            # Check if the friend relationship already exists or if a request was already sent
            existing_request = Friends.query.filter(
                ((Friends.user_id1 == current_user) & (Friends.user_id2 == friend_username)) |
                ((Friends.user_id1 == friend_username) & (Friends.user_id2 == current_user))
            ).first()

            if existing_request:
                if existing_request.status == 'Pending':
                    flash(f'You have already sent a request to {friend_username} or received one from them.', 'warning')
                elif existing_request.type == 'Friend' and existing_request.status == 'Accepted':
                    flash(f'You are already friends with {friend_username}.', 'warning')
                elif existing_request.status == 'Rejected' or (existing_request.status == 'Deleted' and existing_request.type == 'Friend'):
                    event = db.session.query(
                                            (extract('epoch', db.func.current_timestamp()) - extract('epoch', existing_request.timestamp)).label('time_diff')
                                                ).first() 
                    if event.time_diff > 5*60:
                        existing_request.status = 'Pending'
                        existing_request.timestamp =  db.func.current_timestamp() # Update to current timestamp
                        db.session.commit()
                        flash(f'Friend request re-sent to {friend_username}', 'success')
                    else:
                        flash('You cannot send a friend request to this user at this moment. Please try again later.', 'warning')
            else:
                # Create a new friend request
                new_request = Friends(user_id1=current_user, user_id2=friend_username, type='Request', status='Pending')
                db.session.add(new_request)
                db.session.commit()
                flash(f'Friend request sent to {friend_username}', 'success')

    # Retrieve sent and received friend requests
    sent_requests = Friends.query.filter_by(user_id1=current_user, status='Pending').all()
    received_requests = Friends.query.filter_by(user_id2=current_user, status='Pending').all()
    
    # Retrieve friends list (only 'Friend' type entries)
    friends_list = Friends.query.filter(
        ((Friends.user_id1 == current_user) & (Friends.type == 'Friend') & (Friends.status == 'Accepted')) |
        ((Friends.user_id2 == current_user) & (Friends.type == 'Friend') & (Friends.status == 'Accepted'))
    ).all()

    # Filter friends list to show only the corresponding user
    friends_list_display = []
    for friendship in friends_list:
        if friendship.user_id1 == current_user:
            friends_list_display.append(friendship.user_id2)
        else:
            friends_list_display.append(friendship.user_id1)

    return render_template('friends.html', form=form, sent_requests=sent_requests, received_requests=received_requests, friends_list=friends_list_display)

@app.route('/respond_to_request', methods=['POST'])
def respond_to_request():
    request_id1 = request.form.get('request_id1')
    request_id2 = request.form.get('request_id2')
    action = request.form.get('action')
    current_user = session.get('username')

    # Use filter to query with composite primary key
    friend_request = Friends.query.filter_by(user_id1=request_id1, user_id2=request_id2).first()
    
    if friend_request:
        if action == 'accept':
            # Update status to 'Accepted' and type to 'Friend'
            friend_request.status = 'Accepted'
            friend_request.type = 'Friend'
            db.session.commit()

            flash('Friend request accepted', 'success')
        elif action == 'decline':
            # Update the request to 'Rejected' and update the timestamp
            friend_request.status = 'Rejected'
            friend_request.timestamp = db.func.current_timestamp()
            db.session.commit()
            flash('Friend request declined', 'success')
    else:
        flash('Friend request not found', 'danger')

    return redirect(url_for('friends'))




@app.route('/stocks', methods=['GET']) 
def stocks(): 
    # want to define three things which are the stock symbol, stock name and a potential price last close price  
    # want to also make a search bar that will refilter the stocks based on the names put into the search bar
    search_query = request.args.get('search', '')

    # If there is a search query, filter the stocks by name or symbol
    if search_query:
        stocks = Stock.query.filter(
            (Stock.name.ilike(f'%{search_query}%')) | 
            (Stock.symbol.ilike(f'%{search_query}%'))
        ).all()
    else:
        stocks = Stock.query.all()  # Get all stocks if no search query
    
    return render_template('stocks.html', stocks=stocks, search_query=search_query)

@app.route('/buy_stock/<int:portfolio_id>', methods=['GET', 'POST'])
def buy_stock(portfolio_id):
    portfolio = Portfolio.query.get_or_404(portfolio_id)
    stocks = Stock.query.all()
    cash_account = CashAccount.query.filter_by(pid=portfolio_id).first()

    form = BuySellStockForm()
    
    # Populate choices for buying stocks
    form.stock_symbol.choices = [
        (stock.symbol, f"{stock.name} - {stock.symbol}" if stock.name != stock.symbol else stock.name)
        for stock in stocks
    ]

    if request.method == 'POST':
        stock_symbol = form.stock_symbol.data
        shares = int(form.amount.data)  # Number of shares

        # Get current stock price
        try:
            stock_info = yf.Ticker(stock_symbol).info
            current_price = stock_info.get('regularMarketPrice')
            if current_price is None:
                current_price = stock_info.get('previousClose')
            if current_price is None:
                flash('Stock price not available. Transaction cannot proceed.', 'danger')
                return redirect(url_for('buy_stock', portfolio_id=portfolio_id))
        except Exception as e:
            flash('Stock price not available. Transaction cannot proceed.', 'danger')
            return redirect(url_for('buy_stock', portfolio_id=portfolio_id))

        total_cost = Decimal(current_price) * shares

        if cash_account.balance >= total_cost:
            portfolio_holding = PortfolioHolding.query.filter_by(pid=portfolio_id, symbol=stock_symbol).first()
            if portfolio_holding:
                portfolio_holding.volume += shares
            else:
                new_holding = PortfolioHolding(pid=portfolio_id, symbol=stock_symbol, volume=shares)
                db.session.add(new_holding)
            cash_account.balance = round(cash_account.balance - total_cost, 3)
            db.session.commit()
            flash(f'Stock purchased successfully! Total Cost: ${total_cost}', 'success')

            # Record the stock purchase action
            record = PortfolioRecords(pid=portfolio_id, action_type='buy', symbol=stock_symbol, volume=shares, amount=total_cost)
            db.session.add(record)
            db.session.commit()
        else:
            flash('Insufficient funds to purchase stock.', 'danger')

        return redirect(url_for('buy_stock', portfolio_id=portfolio_id))

    return render_template('buy_stock.html', form=form, portfolio=portfolio, cash_account=cash_account)

@app.route('/sell_stock/<int:portfolio_id>', methods=['GET', 'POST'])
def sell_stock(portfolio_id):
    portfolio = Portfolio.query.get_or_404(portfolio_id)
    cash_account = CashAccount.query.filter_by(pid=portfolio_id).first()
    portfolio_holdings = PortfolioHolding.query.filter_by(pid=portfolio_id).all()
    holdings = {h.symbol: h.volume for h in portfolio_holdings}
    form = SellStockForm()

    form.sell_stock_symbol.choices = [
        (symbol, f"{symbol} - {holdings[symbol]} shares")
        for symbol in holdings
    ]

    stock_prices = {}
    for symbol in holdings:
        try:
            stock_info = yf.Ticker(symbol).info
            current_price = stock_info.get('regularMarketPrice')
            if current_price is None:
                current_price = stock_info.get('previousClose')
            if current_price is not None:
                stock_prices[symbol] = current_price
        except Exception:
            stock_prices[symbol] = 'N/A'

    if request.method == 'POST':
        stock_symbol = form.sell_stock_symbol.data
        shares = int(form.amount.data)  # Number of shares

        if stock_symbol in stock_prices:
            current_price = stock_prices[stock_symbol]
            total_amount = Decimal(current_price) * shares

            if stock_symbol in holdings and holdings[stock_symbol] >= shares:
                portfolio_holding = PortfolioHolding.query.filter_by(pid=portfolio_id, symbol=stock_symbol).first()
                portfolio_holding.volume -= shares
                cash_account.balance = round(cash_account.balance + total_amount, 3)
                if portfolio_holding.volume == 0:
                    db.session.delete(portfolio_holding)
                db.session.commit()
                flash(f'Stock sold successfully! Total Earnings: ${total_amount}', 'success')

                # Record the stock sale action
                record = PortfolioRecords(pid=portfolio_id, action_type='sell', symbol=stock_symbol, volume=shares, amount=total_amount)
                db.session.add(record)
                db.session.commit()
            else:
                flash('Not enough stock to sell or stock not found in portfolio.', 'danger')
        else:
            flash('Stock price not available. Transaction cannot proceed.', 'danger')

        return redirect(url_for('sell_stock', portfolio_id=portfolio_id))

    return render_template(
        'sell_stock.html',
        form=form,
        portfolio=portfolio,
        cash_account=cash_account,
        holdings=holdings,
        stock_prices=stock_prices
    )


@app.route('/stock_price/<symbol>', methods=['GET'])
def stock_price(symbol):
    try:
        stock_info = yf.Ticker(symbol).info
        current_price = stock_info.get('regularMarketPrice')
        if current_price is None:
            current_price = stock_info.get('previousClose')
        if current_price is None:
            return jsonify({'error': 'Stock price not available.'}), 404
        return jsonify({'price': current_price})
    except Exception as e:
        return jsonify({'error': 'Stock price not available.'}), 404

@app.route('/portfolio_holdings/<int:portfolio_id>', methods=['GET'])
def portfolio_holdings(portfolio_id):
    holdings = PortfolioHolding.query.filter_by(pid=portfolio_id).all()
    stock_data = {}
    for holding in holdings:
        stock = Stock.query.filter_by(symbol=holding.symbol).first()
        if stock:
            stock_data[stock.symbol] = {
                'name': stock.name,
                'quantity': holding.volume
            }
    return jsonify(stock_data) 



@app.route('/coefficient_variation/<int:portfolio_id>')
def calc_coefficient_var(portfolio_id):
    query = text("""
    WITH stock_returns AS (
        SELECT
            sh.stock_symbol,
            (sh.close_price - LAG(sh.close_price) OVER (PARTITION BY sh.stock_symbol ORDER BY sh.date)) / LAG(sh.close_price) OVER (PARTITION BY sh.stock_symbol ORDER BY sh.date) AS return
        FROM StockHistory sh
        JOIN PortfolioStocks ps ON sh.stock_symbol = ps.stock_symbol
        WHERE ps.portfolio_id = :portfolio_id
    )
    SELECT
        stock_symbol,
        STDDEV(return) / AVG(return) AS coefficient_of_variation
    FROM stock_returns
    GROUP BY stock_symbol;
    """)

    # Execute the query
    result = db.session.execute(query, {'portfolio_id': portfolio_id})

    # Fetch all the results
    rows = result.fetchall()

    # Process and return the result as needed
    return str(rows)


# @app.route('/beta/<stock_id>')
# def beta(stock_id):
#     # need to calculate both variance and covariance and then divide covariance by variance
#     query = text("""
#     SELECT stock_symbol, AVG(close_price) AS average_price
#     FROM StockHistory
#     GROUP BY stock_symbol;
#     """)

#     # Execute the query
#     result = db.session.execute(query)

#     # Fetch all the results
#     rows = result.fetchall()

#     # Process and return the result as needed
#     return str(rows) 

#Returns the covariance matrix of the portfolio 
@app.route('/final_correlation_value/<int:portfolio_id>')
def final_correlation_value(portfolio_id):
    query = text("""
    WITH stock_returns AS (
        SELECT
            sh.stock_symbol,
            sh.date,
            (sh.close_price - LAG(sh.close_price) OVER (PARTITION BY sh.stock_symbol ORDER BY sh.date)) / LAG(sh.close_price) OVER (PARTITION BY sh.stock_symbol ORDER BY sh.date) AS return
        FROM StockHistory sh
        JOIN PortfolioStocks ps ON sh.stock_symbol = ps.stock_symbol
        WHERE ps.portfolio_id = :portfolio_id
    ),
    pivot_table AS (
        SELECT
            date,
            stock_symbol,
            return
        FROM stock_returns
    )
    SELECT
        s1.stock_symbol AS stock1,
        s2.stock_symbol AS stock2,
        CORR(s1.return, s2.return) AS correlation
    FROM pivot_table s1
    JOIN pivot_table s2 ON s1.date = s2.date
    WHERE s1.stock_symbol < s2.stock_symbol
    GROUP BY s1.stock_symbol, s2.stock_symbol
    ORDER BY s1.stock_symbol, s2.stock_symbol
    LIMIT 1 OFFSET (
        SELECT COUNT(*)
        FROM pivot_table s1
        JOIN pivot_table s2 ON s1.date = s2.date
        WHERE s1.stock_symbol < s2.stock_symbol
    ) - 1;
    """)

    # Execute the query
    result = db.session.execute(query, {'portfolio_id': portfolio_id})

    # Fetch the final result
    row = result.fetchone()

    # Return the final correlation value
    if row:
        return jsonify({
            'stock1': row.stock1,
            'stock2': row.stock2,
            'correlation': row.correlation
        })
    else:
        return jsonify({'error': 'No data found for the given portfolio'}), 404



@app.route('/insert_stock/<int:stock_list_id>', methods=['GET', 'POST'])
def insert_stock(stock_list_id):
    stock_list = StockList.query.get_or_404(stock_list_id)

    if request.method == 'POST':
        stock_symbol = request.form.get('stock_symbol')
        volume = request.form.get('volume', type=int)

        if not stock_symbol or volume is None:
            flash('Invalid input. Please provide both stock symbol and volume.', 'danger')
            return redirect(url_for('insert_stock', stock_list_id=stock_list_id))

        stock = Stock.query.filter_by(symbol=stock_symbol).first()
        if not stock:
            flash('Stock not found.', 'danger')
            return redirect(url_for('insert_stock', stock_list_id=stock_list_id))

        existing_stock = SLConsists.query.filter_by(slid=stock_list_id, symbol=stock_symbol).first()
        if existing_stock:
            # Update existing stock volume
            existing_stock.volume += volume
        else:
            # Add new stock to the list
            new_stock = SLConsists(slid=stock_list_id, symbol=stock_symbol, volume=volume)
            db.session.add(new_stock)

        db.session.commit()
        flash('Stock added to the list successfully!', 'success')
        return redirect(url_for('stocklists', stock_list_id=stock_list_id))

    return render_template('insert_stock.html', stock_list_id=stock_list_id)

@app.route('/remove_stock/<int:stock_list_id>', methods=['GET', 'POST'])
def remove_stock(stock_list_id):
    stock_list = StockList.query.get_or_404(stock_list_id)
    stock_list_stocks = SLConsists.query.filter_by(slid=stock_list_id).all()
    
    if request.method == 'POST':
        stock_symbol = request.form.get('stock_symbol')
        volume_to_remove = int(request.form.get('volume'))
        
        stock_consist = SLConsists.query.filter_by(slid=stock_list_id, symbol=stock_symbol).first()
        if stock_consist:
            if stock_consist.volume > volume_to_remove:
                stock_consist.volume -= volume_to_remove
                db.session.commit()
                flash('Stock volume updated successfully!', 'success')
            elif stock_consist.volume == volume_to_remove:
                db.session.delete(stock_consist)
                db.session.commit()
                flash('Stock removed from list successfully!', 'success')
            else:
                flash('Not enough volume to remove.', 'danger')
        else:
            flash('Stock not found in the list.', 'danger')
        
        return redirect(url_for('remove_stock', stock_list_id=stock_list_id))

    return render_template('remove_stock.html', stock_list_id=stock_list_id, stock_list_stocks=stock_list_stocks) 

@app.route('/stock/<string:symbol>/performance')
def stock_performance_graph(symbol):
    stock = Stock.query.get_or_404(symbol)
    history = StockHistory.query.filter_by(symbol=symbol).order_by(StockHistory.timestamp).all()  # Sort by timestamp

    # Convert history data to JSON
    history_json = [
        {
            'timestamp': record.timestamp.isoformat(),
            'open': record.open,
            'high': record.high,
            'low': record.low,
            'close': record.close,
            'volume': record.volume
        }
        for record in history
    ]
    
    # Extract years for the dropdown
    years = set(record.timestamp.year for record in history)
    years = sorted(years, reverse=True)

    # Pass selected filter (default to 'All')
    selected_filter = request.args.get('filter', 'All')

    return render_template(
        'stock_performance_graph.html',
        stock=stock,
        history_json=history_json,
        years=years,
        selected_filter=selected_filter
    )


@app.route('/portfolio_history/<int:portfolio_id>', methods=['GET'])
def portfolio_history(portfolio_id):
    portfolio = Portfolio.query.get_or_404(portfolio_id)

    # Cash transactions
    cash_transactions = PortfolioRecords.query.filter(
        PortfolioRecords.pid == portfolio_id,
        PortfolioRecords.action_type.in_(['deposit', 'withdraw'])
    ).all()

    # Transfers (both outgoing and incoming)
    transfers = PortfolioRecords.query.filter(
        (PortfolioRecords.pid == portfolio_id) | 
        (PortfolioRecords.destination_pid == portfolio_id),
        PortfolioRecords.action_type == 'transfer'
    ).all()

    # Stock transactions
    stock_transactions = PortfolioRecords.query.filter(
        PortfolioRecords.pid == portfolio_id,
        PortfolioRecords.action_type.in_(['buy', 'sell'])
    ).all()

    return render_template('portfolio_history.html', portfolio=portfolio,
                           cash_transactions=cash_transactions,
                           transfers=transfers,
                           stock_transactions=stock_transactions)




@app.route('/submit_review/<int:stock_list_id>', methods=['GET', 'POST'])
def submit_review(stock_list_id):
    username = session.get('username')
    if not username:
        flash('You need to log in first.', 'warning')
        return redirect(url_for('login'))

    stock_list = StockList.query.get_or_404(stock_list_id)
    existing_review = SLReviews.query.filter_by(slid=stock_list_id, username=username).first()

    if request.method == 'POST':
        review_text = request.form['review']
        rating = request.form['rating']
        
        if existing_review:
            # Update existing review
            existing_review.review = review_text
            existing_review.rating = rating
            db.session.commit()
            flash('Review updated successfully!', 'success')
        else:
            # Add new review
            new_review = SLReviews(slid=stock_list_id, username=username, review=review_text, rating=rating)
            db.session.add(new_review)
            db.session.commit()
            flash('Review submitted successfully!', 'success')

        return redirect(url_for('stocklists', stock_list_id=stock_list_id))

    return render_template('submit_review.html', stock_list=stock_list, existing_review=existing_review)


@app.route('/stock_future_prediction_form', methods=['GET', 'POST'])
def stock_future_prediction_form():
    if request.method == 'POST':
        stock_symbol = request.form.get('future_stock_symbol')
        if stock_symbol:
            return redirect(url_for('stock_future_prediction', symbol=stock_symbol))

    stocks = Stock.query.all()
    return render_template('stock_history.html', stocks=stocks)


@app.route('/stock/<string:symbol>/future_prediction', methods=['GET', 'POST'])
def stock_future_prediction(symbol):
    stock = Stock.query.get_or_404(symbol)
    interval = request.form.get('prediction_interval', 30)  # Default to 1 month if not provided

    # Retrieve stock data
    end_date = datetime.now()
    start_date = end_date - timedelta(days=730)  # Approx 2 years

    history = StockHistory.query.filter(StockHistory.symbol == symbol,
                                        StockHistory.timestamp >= start_date,
                                        StockHistory.timestamp <= end_date).order_by(StockHistory.timestamp).all()

    if not history:
        return render_template('stock_future_prediction.html', stock=stock, future_data=[], interval=interval)

    # Prepare data for prediction
    dates = np.array([record.timestamp.timestamp() for record in history])
    prices = np.array([float(record.close) for record in history])  # Convert Decimal to float

    # Simple linear regression for trend-based prediction
    def linear_trend(dates, prices):
        X = dates.reshape(-1, 1)
        Y = prices
        A = np.vstack([X.flatten(), np.ones(len(X))]).T
        m, c = np.linalg.lstsq(A, Y, rcond=None)[0]  # Linear regression
        return m, c

    def predict_future_prices(m, c, start_date, num_days):
        future_dates = np.arange(start_date + 86400, start_date + 86400 * (num_days + 1), 86400)
        future_prices = m * future_dates + c
        return future_dates, future_prices

    # Calculate trend
    if len(prices) > 1:
        m, c = linear_trend(dates, prices)
    else:
        m, c = 0, prices[-1]  # No trend if not enough data

    # Predict future prices
    future_dates, future_prices = predict_future_prices(m, c, end_date.timestamp(), int(interval))

    # Convert future dates and prices to a format suitable for the template
    future_data = [{
        'date': (datetime.fromtimestamp(date)).strftime('%Y-%m-%d'),
        'price': price
    } for date, price in zip(future_dates, future_prices)]

    # Map intervals to days
    interval_days = {
        7: '1 Week',
        30: '1 Month',
        90: '1 Quarter',
        365: '1 Year',
        1825: '5 Years'
    }

    return render_template('stock_future_prediction.html', stock=stock, future_data=future_data, interval=interval_days.get(int(interval), 'Unknown'))


@app.route('/delete_stock_list/<int:stock_list_id>', methods=['POST'])
def delete_stock_list(stock_list_id):
    username = session.get('username')
    if not username:
        flash('You need to log in first.', 'warning')
        return redirect(url_for('login'))

    stock_list = StockList.query.get_or_404(stock_list_id)

    # Ensure the user is the owner
    owner = SLOwners.query.filter_by(slid=stock_list_id, username=username).first()
    if not owner:
        flash('You are not authorized to delete this stock list.', 'danger')
        return redirect(url_for('stocklists'))

    # Delete related entries
    SharedSL.query.filter_by(slid=stock_list_id).delete()
    SLReviews.query.filter_by(slid=stock_list_id).delete()
    SLConsists.query.filter_by(slid=stock_list_id).delete()
    SLOwners.query.filter_by(slid=stock_list_id).delete()
    StockList.query.filter_by(slid=stock_list_id).delete()

    db.session.commit()
    flash('Stock list deleted successfully!', 'success')
    return redirect(url_for('stocklists'))


@app.route('/portfolio_statistics/<int:portfolio_id>', methods=['GET'])
def portfolio_statistics(portfolio_id):
    period = request.args.get('period', '1y')  # Default to 1 year if no period is specified
    portfolio, stock_holdings, coefficient_of_variation, beta_values = get_portfolio_statistics_data(portfolio_id, period)

    # Compute matrices dynamically to ensure up-to-date data
    stock_symbols = [holding.symbol for holding in stock_holdings]
    covariance_matrix = get_covariance_matrix(stock_symbols)
    correlation_matrix = get_correlation_matrix(covariance_matrix) if len(stock_symbols) > 1 else None

    return render_template('portfolio_statistics.html',
                          portfolio=portfolio,
                          stock_holdings=stock_holdings,
                          coefficient_of_variation=coefficient_of_variation,
                          beta_values=beta_values,
                          covariance_matrix=covariance_matrix,
                          correlation_matrix=correlation_matrix,
                          period=period)



@app.route('/stocklist_statistics/<int:stock_list_id>', methods=['GET'])
def stocklist_statistics(stock_list_id):
    period = request.args.get('period', '1y')  # Default to 1 year if no period is specified
    stock_list = StockList.query.get_or_404(stock_list_id)

    # Fetch stock holdings for the stock list
    stock_consists = SLConsists.query.filter_by(slid=stock_list_id).all()

    if not stock_consists:
        return render_template('stocklist_statistics.html',
                               stock_list=stock_list,
                               stock_consists=[],
                               coefficient_of_variation={},
                               beta_values={},
                               covariance_matrix=None,
                               correlation_matrix=None,
                               period=period)

    stock_symbols = [sc.symbol for sc in stock_consists]

    coefficient_of_variation = {symbol: get_stock_cv(symbol) for symbol in stock_symbols}
    beta_values = {symbol: calculate_beta(symbol, period) for symbol in stock_symbols}

    # Compute matrices dynamically
    covariance_matrix = get_covariance_matrix(stock_symbols)
    correlation_matrix = get_correlation_matrix(covariance_matrix) if len(stock_symbols) > 1 else None

    return render_template('stocklist_statistics.html',
                           stock_list=stock_list,
                           stock_consists=stock_consists,
                           coefficient_of_variation=coefficient_of_variation,
                           beta_values=beta_values,
                           covariance_matrix=covariance_matrix,
                           correlation_matrix=correlation_matrix,
                           period=period)



if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
