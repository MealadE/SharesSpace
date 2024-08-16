import os

class Config:
    # Secret key for session management and security
    # Use a more secure key for production
    SECRET_KEY = os.environ.get('SECRET_KEY', 'my_very_secret_key_that_is_long_and_random')

    # Database configuration
    # Adjust the database URL as needed. Example for PostgreSQL.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'postgresql://postgres:postgres@localhost:5432/mydb', 'postgresql://postgres:postgres@localhost:5432/mydb'
    )
    
    # Disable Flask-SQLAlchemy event system to avoid unnecessary overhead
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # For development, you might want to set this to True to get detailed error messages
    DEBUG = True

    # For production, you should set this to False
    TESTING = False

    # If you want to configure logging, you can add more settings here
    LOGGING_LEVEL = os.environ.get('LOGGING_LEVEL', 'DEBUG')

# Additional configuration can be added here
# For example, you might want to configure email settings or other services
