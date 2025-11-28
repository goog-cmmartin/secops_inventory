import sqlite3
import json
import os

# --- Configuration ---
BACKUP_DB_PATH = 'gcp_inventory.bak'
TABLES_TO_EXPORT = ['audit', 'configurable_audit']

def export_table_to_json(table_name, con):
    """
    Reads all records from a specific table and writes them to a JSON file.
    """
    output_json_path = f'{table_name}_backup.json'
    print(f"\n--- Exporting table '{table_name}' to '{output_json_path}' ---")
    
    try:
        cur = con.cursor()
        print(f"Executing query: SELECT * FROM {table_name};")
        
        cur.execute(f"SELECT * FROM {table_name}")
        rows = cur.fetchall()

        data = [dict(row) for row in rows]
        
        if not data:
            print(f"No records found in table '{table_name}'.")
            return

        with open(output_json_path, 'w') as f:
            json.dump(data, f, indent=2)

        print(f"Successfully exported {len(data)} records from '{table_name}'.")

    except sqlite3.OperationalError as e:
        print(f"Warning: Could not export table '{table_name}'. Reason: {e}")
    except Exception as e:
        print(f"An unexpected error occurred while exporting '{table_name}': {e}")


def export_data():
    """
    Connects to a backup SQLite database and exports specified tables to JSON files.
    """
    print(f"--- Starting export from '{BACKUP_DB_PATH}' ---")

    if not os.path.exists(BACKUP_DB_PATH):
        print(f"Error: Backup database file not found at '{BACKUP_DB_PATH}'")
        return

    try:
        con = sqlite3.connect(BACKUP_DB_PATH)
        con.row_factory = sqlite3.Row
        
        for table in TABLES_TO_EXPORT:
            export_table_to_json(table, con)

    except sqlite3.Error as e:
        print(f"Database connection error: {e}")
    finally:
        if 'con' in locals() and con:
            con.close()
            print("\nDatabase connection closed.")

if __name__ == "__main__":
    export_data()
