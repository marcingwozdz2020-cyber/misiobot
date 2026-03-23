# Updated bot.py

import logging
import sqlite3

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Connect to the database
conn = sqlite3.connect('tweets.db')
cursor = conn.cursor()

# Create table for storing tweets
cursor.execute('''CREATE TABLE IF NOT EXISTS tweets (id INTEGER PRIMARY KEY, tweet TEXT, created_at TIMESTAMP)''')

# Function to log and save tweets

def log_tweet(tweet):
    logging.info(f'Tweet Logged: {tweet}')
    cursor.execute('INSERT INTO tweets (tweet, created_at) VALUES (?, ?)', (tweet, datetime.now()))
    conn.commit()

# Function to get statistics

def get_tweet_statistics():
    cursor.execute('SELECT COUNT(*) FROM tweets')
    count = cursor.fetchone()[0]
    logging.info(f'Total Tweets: {count}')

# Example of logging a tweet
log_tweet('This is a sample tweet')
get_tweet_statistics()  

# Don't forget to close the connection
conn.close()