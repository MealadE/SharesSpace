from sqlalchemy import create_engine, text
from sqlalchemy.engine import reflection
from config import Config

# Create an engine instance using the database URL from the config
engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)

# Create an inspector instance to inspect database schema
inspector = reflection.Inspector.from_engine(engine)

# Fetch the list of tables
tables = inspector.get_table_names()

# Define the table to exclude
exclude_table = 'stockhistory'
exclude = 'stock'


# Print the table names and their contents
def print_table_contents(table_name):
    if table_name == exclude_table or table_name == exclude:
        return  # Skip this table

    with engine.connect() as connection:
        # Execute a query to get all data from the table
        result = connection.execute(text(f"SELECT * FROM {table_name}"))
        rows = result.fetchall()
        print(f"\nContents of table '{table_name}':")
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
            print("Table is empty.")

print("Tables in the database:")
for table in tables:
    print(f"- {table}")
    print_table_contents(table)
