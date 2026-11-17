# FinanceApp

A Windows desktop personal-finance app with a dark/light theme.

## Requirements
- Windows 10/11
- Python 3.10 or newer

## Install and run
1. Open Command Prompt in this folder.
2. Install the required packages:
   ```bat
   python -m pip install -r requirements.txt
   ```
3. Start the app:
   ```bat
   python main.py
   ```

## Features
- Dashboard with selected-month income and expenses, current balance, and side-by-side income and expense bars for Monday through Sunday.
- Set a starting balance for money you already have. It is stored separately from income and added to all-time income minus all-time expenses to calculate your current balance.
- Add, edit, search, and delete transactions.
- Monthly budgets and savings goals.
- Reports and CSV export.
- Dark/light mode.
- Calendar pickers for transaction dates, goal deadlines, and the top-right month filter. The month filter no longer requires typing; choose a date in the calendar, click **Select month**, then click **Apply**.
- Local SQLite storage, no account or bank connection required.

## Data storage
Your database is stored at `%USERPROFILE%\.name\finance.db` and remains in place when you replace the app folder. The starting balance is stored in the same database in a separate settings table, not as an income transaction. Use the backup option in Reports to create a backup.
