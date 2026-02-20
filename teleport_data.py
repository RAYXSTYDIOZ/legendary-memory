import psycopg2
import logging
import sys

# --- CONFIGURATION ---
# Paste your OLD Railway Postgres URL here
SOURCE_DB = "postgresql://postgres:EKgnwDuXppFjhyqWgDMriCtPRxwterbY@tramway.proxy.rlwy.net:16003/railway"

# Paste your NEW Neon Postgres URL here
DEST_DB = "postgresql://neondb_owner:npg_cQyUr70jPVoY@ep-long-union-aibzd462-pooler.c-4.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger('teleport')

def migrate():
    if "PASTE_" in SOURCE_DB or "PASTE_" in DEST_DB:
        logger.error("❌ Please edit teleport_data.py and paste your database URLs first!")
        return

    try:
        logger.info("🔗 Connecting to SOURCE (Old DB)...")
        src_conn = psycopg2.connect(SOURCE_DB)
        src_cur = src_conn.cursor()

        logger.info("🔗 Connecting to DESTINATION (New Neon DB)...")
        dest_conn = psycopg2.connect(DEST_DB)
        dest_cur = dest_conn.cursor()

        # 1. Get all tables from source
        src_cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        tables = [t[0] for t in src_cur.fetchall()]
        
        if not tables:
            logger.warning("⚠️ No tables found in source database.")
            return

        logger.info(f"📋 Found {len(tables)} tables: {', '.join(tables)}")

        # 2. Transfer data table by table
        for table in tables:
            logger.info(f"🚀 Teleporting table: {table}...")
            
            # Get column names
            try:
                src_cur.execute(f"SELECT * FROM {table} LIMIT 0")
                colnames = [desc[0] for desc in src_cur.description]
                cols_str = ", ".join([f'"{c}"' for c in colnames])
                placeholders = ", ".join(["%s"] * len(colnames))

                # Fetch all data
                src_cur.execute(f"SELECT * FROM {table}")
                rows = src_cur.fetchall()

                if rows:
                    # Insert into destination
                    insert_query = f'INSERT INTO "{table}" ({cols_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'
                    dest_cur.executemany(insert_query, rows)
                    dest_conn.commit()
                    logger.info(f"✅ Transferred {len(rows)} rows for {table}.")
                else:
                    logger.info(f"ℹ️ Table {table} is empty skipping.")
            except Exception as table_e:
                logger.error(f"❌ Error teleporting table {table}: {table_e}")
                dest_conn.rollback()

        logger.info("\n✨ TELEPORT COMPLETE! Your data is now permanently in the Cloud.")
        
    except Exception as e:
        logger.error(f"❌ Migration Error: {e}")
    finally:
        if 'src_conn' in locals(): src_conn.close()
        if 'dest_conn' in locals(): dest_conn.close()

if __name__ == "__main__":
    migrate()
