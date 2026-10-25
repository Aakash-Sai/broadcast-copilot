"""SQLite online backup: safe while the one-instance app is running."""
import argparse
import os
from pathlib import Path
from dotenv import load_dotenv
from backend.editorial_store import EditorialStore


if __name__=='__main__':
    root=Path(__file__).resolve().parent.parent
    load_dotenv(root/'.env')
    parser=argparse.ArgumentParser()
    parser.add_argument('destination',type=Path)
    args=parser.parse_args()
    source=Path(os.getenv('EDITORIAL_DB_PATH',str(root/'runtime/editorial.sqlite3')))
    if not source.is_file():
        raise SystemExit('Source database does not exist; no backup created.')
    EditorialStore(source).backup(args.destination)
    print('Editorial backup completed.')
