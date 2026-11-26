
import sqlite3

conn = sqlite3.connect("data/raw/airtel.db")

query = "SELECT name FROM sqlite_master WHERE type = ?"

tables = conn.execute(query, ("table",)).fetchall()

print("DATABASE TABLES:")

for table in tables:
    print(table[0])

conn.close()
