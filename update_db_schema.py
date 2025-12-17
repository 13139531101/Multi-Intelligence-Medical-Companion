import psycopg
import os

# DB Config for Host Access
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'user': 'pha',
    'password': 'pha_pass',
    'dbname': 'personal_health_assistant'
}

def update_schema():
    print("Connecting to database...")
    try:
        conn = psycopg.connect(**DB_CONFIG)
        conn.autocommit = True
        cursor = conn.cursor()

        # 1. Update consultations table
        print("Checking 'consultations' table...")
        try:
            # Check if title column exists
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='consultations' AND column_name='title';
            """)
            if not cursor.fetchone():
                print("Adding 'title' column to 'consultations'...")
                cursor.execute("ALTER TABLE consultations ADD COLUMN title TEXT;")
            else:
                print("'title' column already exists.")

            # Check if session_id column exists
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='consultations' AND column_name='session_id';
            """)
            if not cursor.fetchone():
                print("Adding 'session_id' column to 'consultations'...")
                cursor.execute("ALTER TABLE consultations ADD COLUMN session_id TEXT;")
            else:
                print("'session_id' column already exists.")

            # Check if tags column exists
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='consultations' AND column_name='tags';
            """)
            if not cursor.fetchone():
                print("Adding 'tags' column to 'consultations'...")
                cursor.execute("ALTER TABLE consultations ADD COLUMN tags JSONB;")
            else:
                print("'tags' column already exists.")

            # Check if consultation_type column exists
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='consultations' AND column_name='consultation_type';
            """)
            if not cursor.fetchone():
                print("Adding 'consultation_type' column to 'consultations'...")
                cursor.execute("ALTER TABLE consultations ADD COLUMN consultation_type TEXT;")
            else:
                print("'consultation_type' column already exists.")

            # Check if agent_id column exists
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='consultations' AND column_name='agent_id';
            """)
            if not cursor.fetchone():
                print("Adding 'agent_id' column to 'consultations'...")
                cursor.execute("ALTER TABLE consultations ADD COLUMN agent_id TEXT;")
            else:
                print("'agent_id' column already exists.")

            # Check if status column exists
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='consultations' AND column_name='status';
            """)
            if not cursor.fetchone():
                print("Adding 'status' column to 'consultations'...")
                cursor.execute("ALTER TABLE consultations ADD COLUMN status TEXT;")
            else:
                print("'status' column already exists.")

        except Exception as e:
            print(f"Error updating consultations: {e}")

        # 2. Update chat_messages table
        print("Checking 'chat_messages' table...")
        try:
            # Check if files column exists
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='chat_messages' AND column_name='files';
            """)
            if not cursor.fetchone():
                print("Adding 'files' column to 'chat_messages'...")
                cursor.execute("ALTER TABLE chat_messages ADD COLUMN files JSONB;")
            else:
                print("'files' column already exists.")
        except Exception as e:
            print(f"Error updating chat_messages: {e}")

        cursor.close()
        conn.close()
        print("Schema update completed.")

    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    update_schema()
