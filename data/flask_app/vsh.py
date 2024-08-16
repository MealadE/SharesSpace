from sqlalchemy import create_engine, text
from sqlalchemy.engine import reflection
from config import Config

# Create an engine instance using the database URL from the config
engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)

# Create an inspector instance to inspect database schema
inspector = reflection.Inspector.from_engine(engine)

# Define the table to include
include_table = 'stockhistory'

# Print the table contents based on the ticker code
def print_table_contents(ticker_code):
    with engine.connect() as connection:
        # Execute a query to get all data from the table for the specific ticker code
        result = connection.execute(text(f"SELECT * FROM {include_table} WHERE symbol = :ticker_code"),
                                    {'ticker_code': ticker_code})
        rows = result.fetchall()
        print(f"\nContents of table '{include_table}' for ticker '{ticker_code}':")
        if rows:
            # Get column names
            columns = result.keys()
            # Print column names
            print(f"{' | '.join(columns)}")
            print('-' * (len(' | '.join(columns))))
            # Print rows
            for row in rows:
                print(' | '.join(map(str, row)))
        else:
            print("No data found for the specified ticker code.")

# Prompt the user for a ticker code
ticker_code = input("Enter the ticker code to display: ").strip()

# Print the contents of the specific table for the ticker code
print_table_contents(ticker_code)
