import psycopg
import os

# Connection string for host machine to docker postgres
PG_DSN = "postgresql://pha:pha_pass@localhost:5432/personal_health_assistant"

def insert_drug(user_id, drug_name):
    try:
        with psycopg.connect(PG_DSN) as conn:
            with conn.cursor() as cur:
                # Check if exists
                cur.execute(
                    "SELECT id FROM user_medications WHERE user_id = %s AND drug_name = %s AND is_active = TRUE",
                    (user_id, drug_name)
                )
                if cur.fetchone():
                    print(f"Drug {drug_name} already exists for user {user_id}")
                    return

                cur.execute(
                    """
                    INSERT INTO user_medications (user_id, drug_name, is_active)
                    VALUES (%s, %s, TRUE)
                    """,
                    (user_id, drug_name)
                )
                conn.commit()
                print(f"Inserted {drug_name} for user {user_id}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    insert_drug("test-123", "Warfarin") # Warfarin interacts with Aspirin
