import sqlite3
import json
import logging
import os
import psycopg2
from psycopg2 import extras
from datetime import datetime, timezone

logger = logging.getLogger('discord_bot.database')

class CursorContext:
    def __init__(self, cursor):
        self.cursor = cursor
    def __enter__(self):
        return self.cursor
    def __exit__(self, exc_type, exc_val, exc_tb):
        if hasattr(self.cursor, 'close'):
            self.cursor.close()

class DatabaseManager:
    def __init__(self, db_path=None):
        self.db_url = os.getenv('DATABASE_URL')
        if self.db_url:
            if self.db_url.startswith("postgres://"):
                self.db_url = self.db_url.replace("postgres://", "postgresql://", 1)
            self.is_postgres = True
            logger.info("Using PostgreSQL database.")
        else:
            self.is_postgres = False
            if db_path is None:
                # Check environment variable for Railway/Docker volumes
                env_path = os.getenv('DATABASE_PATH')
                if env_path:
                    self.db_path = env_path
                else:
                    # Get the directory where database.py is located
                    base_dir = os.path.dirname(os.path.abspath(__file__))
                    self.db_path = os.path.join(base_dir, 'bot_memory.db')
            else:
                self.db_path = db_path
            
            # Ensure the directory for the database exists
            db_dir = os.path.dirname(os.path.abspath(self.db_path))
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
            logger.info(f"Using SQLite database at {self.db_path}")
            
        self.init_db()

    def get_cursor(self, conn):
        return CursorContext(conn.cursor())

    def get_connection(self):
        if self.is_postgres:
            return psycopg2.connect(self.db_url)
        else:
            return sqlite3.connect(self.db_path)

    def get_placeholder(self):
        return "%s" if self.is_postgres else "?"

    def init_db(self):
        """Initialize the database tables."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            
            # Helper for table creation
            def create_table(sql):
                if not self.is_postgres:
                    sql = sql.replace('SERIAL PRIMARY KEY', 'INTEGER PRIMARY KEY AUTOINCREMENT')
                    sql = sql.replace('BIGINT', 'INTEGER')
                cursor.execute(sql)

            # Table for conversation history
            create_table('''
                CREATE TABLE IF NOT EXISTS conversation_history (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    role TEXT,
                    content TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Table for user memory/profiles
            create_table('''
                CREATE TABLE IF NOT EXISTS user_memory (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    profile_summary TEXT,
                    vibe TEXT,
                    notes TEXT,
                    interaction_count INTEGER DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Table for Levels
            create_table('''
                CREATE TABLE IF NOT EXISTS user_levels (
                    user_id BIGINT PRIMARY KEY,
                    xp BIGINT DEFAULT 0,
                    level INTEGER DEFAULT 0
                )
            ''')

            # Table for Warnings
            create_table('''
                CREATE TABLE IF NOT EXISTS user_warnings (
                    user_id BIGINT PRIMARY KEY,
                    count INTEGER DEFAULT 0,
                    history TEXT -- JSON string
                )
            ''')

            # Table for YT Cooldowns
            create_table('''
                CREATE TABLE IF NOT EXISTS yt_cooldowns (
                    user_id BIGINT PRIMARY KEY,
                    expiry TIMESTAMP
                )
            ''')

            # Table for Guild Inviters
            create_table('''
                CREATE TABLE IF NOT EXISTS guild_inviters (
                    guild_id TEXT PRIMARY KEY,
                    user_id BIGINT
                )
            ''')

            # Table for Portfolios
            create_table('''
                CREATE TABLE IF NOT EXISTS user_portfolios (
                    user_id BIGINT PRIMARY KEY,
                    portfolio_data TEXT -- JSON string
                )
            ''')

            # Table for Captchas
            create_table('''
                CREATE TABLE IF NOT EXISTS active_captchas (
                    user_id BIGINT PRIMARY KEY,
                    code TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Table for Reminders
            create_table('''
                CREATE TABLE IF NOT EXISTS user_reminders (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    reminder_text TEXT,
                    delay INTEGER,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Table for Notes
            create_table('''
                CREATE TABLE IF NOT EXISTS user_notes (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    note_text TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            if not self.is_postgres:
                cursor.execute('PRAGMA journal_mode=WAL')
                cursor.execute('PRAGMA synchronous=NORMAL')
            
            conn.commit()
            logger.info("Database initialized successfully.")
        finally:
            conn.close()

    # --- Conversation History ---
    def save_message(self, user_id, role, content):
        p = self.get_placeholder()
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    cursor.execute(
                        f'INSERT INTO conversation_history (user_id, role, content) VALUES ({p}, {p}, {p})',
                        (user_id, role, content)
                    )
                conn.commit()
        except Exception as e:
            logger.error(f"Error saving message to DB: {e}")

    def get_history(self, user_id, limit=20):
        p = self.get_placeholder()
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    cursor.execute(
                        f'SELECT role, content FROM conversation_history WHERE user_id = {p} ORDER BY timestamp DESC LIMIT {p}',
                        (user_id, limit)
                    )
                    rows = cursor.fetchall()
                    return [{"role": row[0], "parts": [{"text": row[1]}]} for row in reversed(rows)]
        except Exception as e:
            logger.error(f"Error getting history from DB: {e}")
            return []

    # --- User Memory ---
    def get_user_memory(self, user_id):
        p = self.get_placeholder()
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    cursor.execute(
                        f'SELECT profile_summary, vibe, interaction_count FROM user_memory WHERE user_id = {p}',
                        (user_id,)
                    )
                    row = cursor.fetchone()
                    if row:
                        return {"profile_summary": row[0], "vibe": row[1], "interaction_count": row[2]}
                    return None
        except Exception as e:
            logger.error(f"Error getting user memory from DB: {e}")
            return None

    def update_user_memory(self, user_id, username, profile_summary=None, vibe=None, notes=None):
        p = self.get_placeholder()
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    cursor.execute(f'SELECT interaction_count FROM user_memory WHERE user_id = {p}', (user_id,))
                    row = cursor.fetchone()
                    
                    if row:
                        interaction_count = row[0] + 1
                        updates = ["interaction_count = %s", "last_updated = CURRENT_TIMESTAMP", "username = %s"]
                        if not self.is_postgres: updates = [u.replace('%s', '?') for u in updates]
                        
                        params = [interaction_count, username]
                        if profile_summary is not None: 
                            updates.append(f"profile_summary = {p}")
                            params.append(profile_summary)
                        if vibe is not None: 
                            updates.append(f"vibe = {p}")
                            params.append(vibe)
                        if notes is not None: 
                            updates.append(f"notes = {p}")
                            params.append(notes)
                        params.append(user_id)
                        
                        cursor.execute(f"UPDATE user_memory SET {', '.join(updates)} WHERE user_id = {p}", params)
                    else:
                        cursor.execute(
                            f'''INSERT INTO user_memory (user_id, username, profile_summary, vibe, notes, interaction_count) 
                               VALUES ({p}, {p}, {p}, {p}, {p}, 1)''',
                            (user_id, username, profile_summary or "New user", vibe or "neutral", notes or "")
                        )
                conn.commit()
        except Exception as e:
            logger.error(f"Error updating user memory: {e}")

    # --- Levels ---
    def get_levels(self):
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    cursor.execute('SELECT user_id, xp, level FROM user_levels')
                    return {row[0]: {"xp": row[1], "level": row[2]} for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"Error getting levels: {e}"); return {}

    def save_level(self, user_id, xp, level):
        p = self.get_placeholder()
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    if self.is_postgres:
                        cursor.execute(
                            'INSERT INTO user_levels (user_id, xp, level) VALUES (%s, %s, %s) ON CONFLICT (user_id) DO UPDATE SET xp = EXCLUDED.xp, level = EXCLUDED.level',
                            (user_id, xp, level)
                        )
                    else:
                        cursor.execute(
                            'INSERT OR REPLACE INTO user_levels (user_id, xp, level) VALUES (?, ?, ?)',
                            (user_id, xp, level)
                        )
                conn.commit()
        except Exception as e:
            logger.error(f"Error saving level: {e}")

    # --- Warnings ---
    def get_warnings(self):
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    cursor.execute('SELECT user_id, count, history FROM user_warnings')
                    return {str(row[0]): {"count": row[1], "history": json.loads(row[2])} for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"Error getting warnings: {e}"); return {}

    def save_warning(self, user_id, count, history):
        p = self.get_placeholder()
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    if self.is_postgres:
                        cursor.execute(
                            'INSERT INTO user_warnings (user_id, count, history) VALUES (%s, %s, %s) ON CONFLICT (user_id) DO UPDATE SET count = EXCLUDED.count, history = EXCLUDED.history',
                            (int(user_id), count, json.dumps(history))
                        )
                    else:
                        cursor.execute(
                            'INSERT OR REPLACE INTO user_warnings (user_id, count, history) VALUES (?, ?, ?)',
                            (int(user_id), count, json.dumps(history))
                        )
                conn.commit()
        except Exception as e:
            logger.error(f"Error saving warning: {e}")

    # --- YT Cooldowns ---
    def get_yt_cooldowns(self):
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    cursor.execute('SELECT user_id, expiry FROM yt_cooldowns')
                    return {str(row[0]): row[1] for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"Error getting yt cooldowns: {e}"); return {}

    def save_yt_cooldown(self, user_id, expiry):
        p = self.get_placeholder()
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    if self.is_postgres:
                        cursor.execute(
                            'INSERT INTO yt_cooldowns (user_id, expiry) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET expiry = EXCLUDED.expiry',
                            (int(user_id), expiry)
                        )
                    else:
                        cursor.execute(
                            'INSERT OR REPLACE INTO yt_cooldowns (user_id, expiry) VALUES (?, ?)',
                            (int(user_id), expiry)
                        )
                conn.commit()
        except Exception as e:
            logger.error(f"Error saving yt cooldown: {e}")

    # --- Guild Inviters ---
    def get_guild_inviters(self):
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    cursor.execute('SELECT guild_id, user_id FROM guild_inviters')
                    return {row[0]: row[1] for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"Error getting guild inviters: {e}"); return {}

    def save_guild_inviter(self, guild_id, user_id):
        p = self.get_placeholder()
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    if self.is_postgres:
                        cursor.execute(
                            'INSERT INTO guild_inviters (guild_id, user_id) VALUES (%s, %s) ON CONFLICT (guild_id) DO UPDATE SET user_id = EXCLUDED.user_id',
                            (str(guild_id), user_id)
                        )
                    else:
                        cursor.execute(
                            'INSERT OR REPLACE INTO guild_inviters (guild_id, user_id) VALUES (?, ?)',
                            (str(guild_id), user_id)
                        )
                conn.commit()
        except Exception as e:
            logger.error(f"Error saving guild inviter: {e}")

    def delete_guild_inviter(self, guild_id):
        p = self.get_placeholder()
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    cursor.execute(f'DELETE FROM guild_inviters WHERE guild_id = {p}', (str(guild_id),))
                conn.commit()
        except Exception as e:
            logger.error(f"Error deleting guild inviter: {e}")

    # --- Portfolios ---
    def get_portfolios(self):
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    cursor.execute('SELECT user_id, portfolio_data FROM user_portfolios')
                    return {row[0]: json.loads(row[1]) for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"Error getting portfolios: {e}"); return {}

    def save_portfolio(self, user_id, portfolio_data):
        p = self.get_placeholder()
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    if self.is_postgres:
                        cursor.execute(
                            'INSERT INTO user_portfolios (user_id, portfolio_data) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET portfolio_data = EXCLUDED.portfolio_data',
                            (int(user_id), json.dumps(portfolio_data))
                        )
                    else:
                        cursor.execute(
                            'INSERT OR REPLACE INTO user_portfolios (user_id, portfolio_data) VALUES (?, ?)',
                            (int(user_id), json.dumps(portfolio_data))
                        )
                conn.commit()
        except Exception as e:
            logger.error(f"Error saving portfolio: {e}")

    # --- Captchas ---
    def get_active_captchas(self):
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    cursor.execute('SELECT user_id, code FROM active_captchas')
                    return {row[0]: row[1] for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"Error getting captchas: {e}"); return {}

    def save_captcha(self, user_id, code):
        p = self.get_placeholder()
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    if self.is_postgres:
                        cursor.execute(
                            'INSERT INTO active_captchas (user_id, code) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET code = EXCLUDED.code, timestamp = CURRENT_TIMESTAMP',
                            (int(user_id), code)
                        )
                    else:
                        cursor.execute(
                            'INSERT OR REPLACE INTO active_captchas (user_id, code) VALUES (?, ?)',
                            (int(user_id), code)
                        )
                conn.commit()
        except Exception as e:
            logger.error(f"Error saving captcha: {e}")

    def delete_captcha(self, user_id):
        p = self.get_placeholder()
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    cursor.execute(f'DELETE FROM active_captchas WHERE user_id = {p}', (int(user_id),))
                conn.commit()
        except Exception as e:
            logger.error(f"Error deleting captcha: {e}")

    # --- Reminders ---
    def get_all_reminders(self):
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    cursor.execute('SELECT user_id, reminder_text, delay, timestamp FROM user_reminders')
                    return [{"user_id": row[0], "text": row[1], "delay": row[2], "timestamp": row[3]} for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting reminders: {e}"); return []

    def save_reminder(self, user_id, text, delay):
        p = self.get_placeholder()
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    cursor.execute(
                        f'INSERT INTO user_reminders (user_id, reminder_text, delay) VALUES ({p}, {p}, {p})',
                        (int(user_id), text, delay)
                    )
                conn.commit()
        except Exception as e:
            logger.error(f"Error saving reminder: {e}")

    def delete_reminder(self, user_id, text):
        p = self.get_placeholder()
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    cursor.execute(f'DELETE FROM user_reminders WHERE user_id = {p} AND reminder_text = {p}', (int(user_id), text))
                conn.commit()
        except Exception as e:
            logger.error(f"Error deleting reminder: {e}")

    # --- Notes ---
    def get_notes(self, user_id):
        p = self.get_placeholder()
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    cursor.execute(f'SELECT note_text FROM user_notes WHERE user_id = {p} ORDER BY timestamp DESC', (int(user_id),))
                    return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting notes: {e}"); return []

    def save_note(self, user_id, text):
        p = self.get_placeholder()
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    cursor.execute(
                        f'INSERT INTO user_notes (user_id, note_text) VALUES ({p}, {p})',
                        (int(user_id), text)
                    )
                conn.commit()
        except Exception as e:
            logger.error(f"Error saving note: {e}")

    def delete_notes(self, user_id):
        p = self.get_placeholder()
        try:
            with self.get_connection() as conn:
                with self.get_cursor(conn) as cursor:
                    cursor.execute(f'DELETE FROM user_notes WHERE user_id = {p}', (int(user_id),))
                conn.commit()
        except Exception as e:
            logger.error(f"Error deleting notes: {e}")

db_manager = DatabaseManager()
