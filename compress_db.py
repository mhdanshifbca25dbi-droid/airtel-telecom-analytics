
import sqlite3
import gzip
import os
import shutil

db_path = "data/raw/airtel.db"
compressed_path = "data/raw/airtel.db.gz"

original_size = os.path.getsize(db_path) / (1024 * 1024)

with open(db_path, "rb") as source:
    with gzip.open(compressed_path, "wb") as target:
        shutil.copyfileobj(source, target)

compressed_size = os.path.getsize(compressed_path) / (1024 * 1024)

print("Original database:", round(original_size, 2), "MB")
print("Compressed database:", round(compressed_size, 2), "MB")

if compressed_size < 95:
    print("GOOD: Suitable for GitHub upload")
else:
    print("Still too large for GitHub")
