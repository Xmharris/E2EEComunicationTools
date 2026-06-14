import sqlite3
import os

DB_NAME = "na_meetings.db"

def get_connection():
    return sqlite3.connect(DB_NAME)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Create regions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS regions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            website TEXT UNIQUE,
            distance REAL
        )
    ''')
    
    # Create meetings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            region_id INTEGER,
            meeting_name TEXT,
            day TEXT,
            time TEXT,
            address TEXT,
            source_url TEXT,
            FOREIGN KEY (region_id) REFERENCES regions (id)
        )
    ''')
    
    conn.commit()
    conn.close()

def insert_region(name, website, distance):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO regions (name, website, distance)
            VALUES (?, ?, ?)
        ''', (name, website, distance))
        region_id = cursor.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        # If it already exists, fetch the id
        cursor.execute('SELECT id FROM regions WHERE website = ?', (website,))
        region_id = cursor.fetchone()[0]
    finally:
        conn.close()
    return region_id

def insert_meeting(region_id, meeting_name, day, time, address, source_url):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO meetings (region_id, meeting_name, day, time, address, source_url)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (region_id, meeting_name, day, time, address, source_url))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized.")
