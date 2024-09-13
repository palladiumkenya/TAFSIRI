from pymongo import MongoClient, mongo_client
import pymongo
from sqlalchemy import create_engine, text, MetaData, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from settings import settings


# MongoDB Connections
print('Connecting to MongoDB...')
client = mongo_client.MongoClient(settings.MONGODB_URL)
print('Connected to MongoDB...')

mongo_db = client[settings.DATABASE_NAME]
TafsiriResp = mongo_db.tafsiri_responses
# TafsiriResp.create_index([("created_at", pymongo.ASCENDING)], unique=False)

# MSSQL Connections
DB_PASSWORD = settings.REPORTING_PASSWORD
DB_HOST_PORT = settings.REPORTING_HOST
DB = settings.REPORTING_DB
USER = settings.REPORTING_USER

# Construct the connection string
SQL_DATABASE_URL = f'mssql+pymssql://{USER}:{DB_PASSWORD}@{DB_HOST_PORT}/{DB}'

# Create an engine instance
engine = create_engine(
    SQL_DATABASE_URL, connect_args={}, echo=False
)
metadata = MetaData()
metadata.reflect(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
inspector = inspect(engine)

# Function to get a MongoDB collection
def get_mongo_collection(collection_name):
    client = MongoClient(settings.MONGODB_URL)
    db = client[settings.DATABASE_NAME]
    return db[collection_name]

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
