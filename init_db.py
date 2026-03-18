import sqlite3
import os
from passlib.context import CryptContext

DB_PATH = "data/system.db"
pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL
    )
    ''')
    
    # Chat History table (Isolated per user)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        message TEXT NOT NULL,
        response TEXT NOT NULL,
        mode TEXT DEFAULT 'local',
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Knowledge Index table (FTS5 for fast Retrieval)
    cursor.execute('''
    CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_index USING fts5(
        file_name,
        content
    )
    ''')
    
    # Track which files are already indexed
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS indexed_files (
        file_name TEXT PRIMARY KEY,
        mtime REAL
    )
    ''')
    
    # Ensure admin exists
    cursor.execute("SELECT * FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        hashed_pw = pwd_context.hash("admin")
        cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", 
                       ("admin", hashed_pw, "admin"))
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    if not os.path.exists("data"):
        os.makedirs("data")
    init_db()
    print("Database initialized.")
