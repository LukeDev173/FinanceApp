"""
LukeFinance - Desktop expense manager
Python 3.10+
Install: pip install -r requirements.txt
Run: python main.py
Data is stored locally in ~/.lukefinance/finance.db
"""
import os
import sqlite3
import csv
import math
import calendar
from datetime import date, timedelta
from datetime import date, datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    from tkcalendar import Calendar
except ImportError:
    raise SystemExit("tkcalendar is missing. Run: python -m pip install -r requirements.txt")

try:
    import customtkinter as ctk
except ImportError:
    raise SystemExit("CustomTkinter is missing. Run: pip install -r requirements.txt")

try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
except ImportError:
    raise SystemExit("Matplotlib is missing. Run: pip install -r requirements.txt")

APP_VERSION = "1.0.0"
APP_NAME = "LukeFinance"
DATA_DIR = Path.home() / ".lukefinance"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "finance.db"

CATEGORIES = {
    "Food": "🍔", "Coffee": "☕", "Transport": "🚌", "Shopping": "🛍",
    "Entertainment": "🎮", "Bills": "💡", "Health": "✚",
    "Education": "📚", "Home": "🏠", "Salary": "💼",
    "Gift": "🎁", "Other": "•"
}
EXPENSE_CATEGORIES = [c for c in CATEGORIES if c not in ("Salary", "Gift")]
INCOME_CATEGORIES = ["Salary", "Gift", "Other"]

THEMES = {
    "dark": {
        "bg": "#10151C", "panel": "#171F29", "panel2": "#1E2935",
        "border": "#2B3948", "text": "#F1F5F9", "muted": "#91A1B5",
        "accent": "#8BFA65", "accent_hover": "#73E84D", "red": "#FF6B78",
        "blue": "#6EA8FE", "purple": "#B69CFF", "chart_grid": "#2B3948"
    },
    "light": {
        "bg": "#F3F6F9", "panel": "#FFFFFF", "panel2": "#EAF0F5",
        "border": "#D8E1E9", "text": "#1A2633", "muted": "#647589",
        "accent": "#42B82E", "accent_hover": "#329B22", "red": "#D94354",
        "blue": "#3478D4", "purple": "#8158D8", "chart_grid": "#D8E1E9"
    }
}


def money(value):
    return f"€{value:,.2f}"

def month_key(d=None):
    d = d or date.today()
    return d.strftime("%Y-%m")

def parse_month(s):
    try:
        return datetime.strptime(s, "%Y-%m").date()
    except ValueError:
        return date.today().replace(day=1)

class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL CHECK(kind IN ('expense','income')),
            amount REAL NOT NULL CHECK(amount > 0),
            category TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            tx_date TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL UNIQUE,
            monthly_limit REAL NOT NULL CHECK(monthly_limit > 0)
        );
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            target REAL NOT NULL CHECK(target > 0),
            saved REAL NOT NULL DEFAULT 0 CHECK(saved >= 0),
            deadline TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS app_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL
        );
        INSERT OR IGNORE INTO app_settings(setting_key, setting_value)
            VALUES ('opening_balance', '0');
        """)
        self.conn.commit()
        # Migrate category labels from the earlier Greek UI to English without losing existing data.
        category_map = {"Φαγητό":"Food", "Καφές":"Coffee", "Μεταφορές":"Transport", "Αγορές":"Shopping", "Ψυχαγωγία":"Entertainment", "Λογαριασμοί":"Bills", "Υγεία":"Health", "Εκπαίδευση":"Education", "Σπίτι":"Home", "Μισθός":"Salary", "Δώρο":"Gift", "Άλλο":"Other"}
        for old, new in category_map.items():
            self.conn.execute("UPDATE transactions SET category=? WHERE category=?", (new, old))
            self.conn.execute("UPDATE budgets SET category=? WHERE category=?", (new, old))
        self.conn.commit()

    def execute(self, sql, params=()):
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        return cur

    def transactions(self, month=None, kind=None, search=""):
        sql = "SELECT * FROM transactions WHERE 1=1"
        params = []
        if month:
            sql += " AND substr(tx_date,1,7)=?"
            params.append(month)
        if kind in ("expense", "income"):
            sql += " AND kind=?"
            params.append(kind)
        if search:
            sql += " AND (description LIKE ? OR category LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])
        return self.conn.execute(sql + " ORDER BY tx_date DESC, id DESC", params).fetchall()

    def totals(self, month):
        row = self.conn.execute("""
            SELECT
            COALESCE(SUM(CASE WHEN kind='income' THEN amount ELSE 0 END),0) income,
            COALESCE(SUM(CASE WHEN kind='expense' THEN amount ELSE 0 END),0) expenses
            FROM transactions WHERE substr(tx_date,1,7)=?
        """, (month,)).fetchone()
        return float(row["income"]), float(row["expenses"])

    def opening_balance(self):
        row = self.conn.execute(
            "SELECT setting_value FROM app_settings WHERE setting_key='opening_balance'"
        ).fetchone()
        return float(row[0]) if row else 0.0

    def set_opening_balance(self, amount):
        self.execute(
            "INSERT INTO app_settings(setting_key, setting_value) VALUES('opening_balance', ?) "
            "ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value",
            (str(float(amount)),)
        )

    def lifetime_totals(self):
        row = self.conn.execute("""
            SELECT
            COALESCE(SUM(CASE WHEN kind='income' THEN amount ELSE 0 END),0) income,
            COALESCE(SUM(CASE WHEN kind='expense' THEN amount ELSE 0 END),0) expenses
            FROM transactions
        """).fetchone()
        return float(row['income']), float(row['expenses'])

    def category_totals(self, month):
        return self.conn.execute("""
            SELECT category, SUM(amount) total FROM transactions
            WHERE kind='expense' AND substr(tx_date,1,7)=?
            GROUP BY category ORDER BY total DESC
        """, (month,)).fetchall()

    def close(self):
        self.conn.close()

class FinanceApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.db = Database()
        self.theme_name = "dark"
        self.t = THEMES[self.theme_name]
        self.title("LukeFinance | Personal Finance")
        self.geometry("1920x1080")
        # Fullscreen
        self.attributes("-fullscreen", True)

        # Exit fullscreen with ESC
        self.bind("<Escape>", lambda event: self.destroy())
        self.minsize(1920, 1080)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("green")
        self.current_page = "Dashboard"
        self.selected_month = month_key()
        self.search_var = tk.StringVar()
        self.filter_var = tk.StringVar(value="All")
        self._build_shell()
        self.show_page("Dashboard")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_shell(self):
        self.configure(fg_color=self.t["bg"])
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.sidebar = ctk.CTkFrame(self, width=230, corner_radius=0, fg_color=self.t["panel"])
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        logo = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        logo.pack(fill="x", padx=20, pady=(24, 30))
        ctk.CTkLabel(logo, text="▥", text_color=self.t["accent"], font=("Segoe UI", 32, "bold")).pack(side="left")
        namebox = ctk.CTkFrame(logo, fg_color="transparent")
        namebox.pack(side="left", padx=10)
        ctk.CTkLabel(namebox, text="LukeFinance", font=("Segoe UI", 18, "bold"), text_color=self.t["text"]).pack(anchor="w")
        ctk.CTkLabel(namebox, text="TRACK  •  PLAN  •  BUILD", font=("Segoe UI", 9), text_color=self.t["muted"]).pack(anchor="w", pady=(2,0))
        self.nav_buttons = {}
        for title, icon in [("Dashboard","⌂"),("Transactions","⇄"),("Budgets","▤"),("Goals","◎"),("Reports","▥")]:
            b = ctk.CTkButton(self.sidebar, text=f"{icon}    {title}", anchor="w", height=44,
                              corner_radius=10, fg_color="transparent", hover_color=self.t["panel2"],
                              text_color=self.t["text"], font=("Segoe UI", 13),
                              command=lambda p=title: self.show_page(p))
            b.pack(fill="x", padx=13, pady=3)
            self.nav_buttons[title] = b
        spacer = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        spacer.pack(fill="both", expand=True)
        ctk.CTkFrame(self.sidebar, height=1, fg_color=self.t["border"]).pack(fill="x", padx=18, pady=12)
        self.theme_button = ctk.CTkButton(self.sidebar, text="☼  Toggle theme", height=40,
            fg_color=self.t["panel2"], hover_color=self.t["border"], text_color=self.t["text"],
            command=self.toggle_theme)
        self.theme_button.pack(fill="x", padx=13, pady=(0,8))
        ctk.CTkLabel(self.sidebar, text="Your data stays on this device.", wraplength=190,
                     text_color=self.t["muted"], font=("Segoe UI", 10)).pack(padx=18, pady=(4,18))

        self.main = ctk.CTkFrame(self, fg_color=self.t["bg"], corner_radius=0)
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(1, weight=1)
        self.header = ctk.CTkFrame(self.main, fg_color="transparent")
        self.header.grid(row=0, column=0, sticky="ew", padx=28, pady=(24,14))
        self.header.grid_columnconfigure(0, weight=1)
        self.page_title = ctk.CTkLabel(self.header, text="", font=("Segoe UI", 27, "bold"), text_color=self.t["text"])
        self.page_title.grid(row=0, column=0, sticky="w")
        self.page_subtitle = ctk.CTkLabel(self.header, text="", font=("Segoe UI", 12), text_color=self.t["muted"])
        self.page_subtitle.grid(row=1, column=0, sticky="w", pady=(3,0))
        self.pending_month = self.selected_month
        self.month_button = ctk.CTkButton(
            self.header, text=f"▦  {datetime.strptime(self.selected_month, '%Y-%m').strftime('%b %Y')}",
            width=135, height=36, fg_color=self.t["panel"], hover_color=self.t["panel2"],
            text_color=self.t["text"], border_width=1, border_color=self.t["border"],
            command=self.choose_filter_month)
        self.month_button.grid(row=0, column=1, rowspan=2, padx=(10,8))
        ctk.CTkButton(self.header, text="Apply", width=85, height=36, command=self.change_month).grid(row=0, column=2, rowspan=2)

        self.content = ctk.CTkScrollableFrame(self.main, fg_color="transparent", corner_radius=0)
        self.content.grid(row=1, column=0, sticky="nsew", padx=22, pady=(0,20))
        self.content.grid_columnconfigure(0, weight=1)

    def clear_content(self):
        for child in self.content.winfo_children():
            child.destroy()

    def show_page(self, page):
        self.current_page = page
        for title, b in self.nav_buttons.items():
            active = title == page
            b.configure(fg_color=self.t["panel2"] if active else "transparent",
                        text_color=self.t["accent"] if active else self.t["text"])
        titles = {
            "Dashboard": ("Dashboard", "A clear overview of your finances."),
            "Transactions": ("Transactions", "Record and organize every euro."),
            "Budgets": ("Budgets", "Set limits for your spending categories."),
            "Goals": ("Savings Goals", "Small steps, measurable progress."),
            "Reports": ("Reports", "See where your money goes.")
        }
        self.page_title.configure(text=titles[page][0])
        self.page_subtitle.configure(text=titles[page][1])
        self.clear_content()
        {"Dashboard": self.dashboard, "Transactions": self.transactions_page,
         "Budgets": self.budgets_page, "Goals": self.goals_page,
         "Reports": self.reports_page}[page]()

    def choose_filter_month(self):
        """Open the calendar used by the top-right month filter."""
        start_date = datetime.strptime(self.pending_month, "%Y-%m").date().replace(day=1)
        popup = ctk.CTkToplevel(self)
        popup.title("Choose month")
        popup.resizable(False, False)
        popup.transient(self)
        popup.grab_set()
        popup.configure(fg_color=self.t["panel"])
        cal = Calendar(
            popup, selectmode="day", year=start_date.year, month=start_date.month,
            day=start_date.day, date_pattern="yyyy-mm-dd",
            background=self.t["panel"], foreground=self.t["text"],
            bordercolor=self.t["border"], headersbackground=self.t["panel2"],
            headersforeground=self.t["text"], selectbackground=self.t["accent"],
            selectforeground="#10151C", normalbackground=self.t["panel"],
            normalforeground=self.t["text"], weekendbackground=self.t["panel"],
            weekendforeground=self.t["muted"], othermonthbackground=self.t["panel"],
            othermonthforeground=self.t["text"], othermonthwebackground=self.t["panel"],
            othermonthweforeground=self.t["text"])
        cal.pack(padx=12, pady=(12, 8))
        controls = ctk.CTkFrame(popup, fg_color="transparent")
        controls.pack(fill="x", padx=12, pady=(0, 12))

        def use_month():
            chosen = datetime.strptime(cal.get_date(), "%Y-%m-%d")
            self.pending_month = chosen.strftime("%Y-%m")
            self.month_button.configure(text=f"▦  {chosen.strftime('%b %Y')}")
            popup.destroy()

        self.button(controls, "Cancel", popup.destroy, width=90).pack(side="right", padx=(6, 0))
        self.button(controls, "Select month", use_month, primary=True, width=120).pack(side="right")
        popup.update_idletasks()
        x = self.winfo_rootx() + max(20, (self.winfo_width() - popup.winfo_width()) // 2)
        y = self.winfo_rooty() + max(20, (self.winfo_height() - popup.winfo_height()) // 2)
        popup.geometry(f"+{x}+{y}")

    def change_month(self):
        self.selected_month = self.pending_month
        self.show_page(self.current_page)

    def panel(self, parent=None, **kwargs):
        parent = parent or self.content
        return ctk.CTkFrame(parent, fg_color=self.t["panel"], corner_radius=16,
                            border_width=1, border_color=self.t["border"], **kwargs)

    def label(self, parent, text, size=13, color=None, bold=False, **kwargs):
        return ctk.CTkLabel(parent, text=text, font=("Segoe UI", size, "bold" if bold else "normal"),
                            text_color=color or self.t["text"], **kwargs)

    def button(self, parent, text, command, primary=False, width=None):
        return ctk.CTkButton(parent, text=text, command=command, width=width or 140, height=38,
            corner_radius=10, fg_color=self.t["accent"] if primary else self.t["panel2"],
            hover_color=self.t["accent_hover"] if primary else self.t["border"],
            text_color="#10151C" if primary else self.t["text"], font=("Segoe UI", 12, "bold" if primary else "normal"))

    def stat_card(self, parent, title, value, hint, color=None):
        card = self.panel(parent)
        card.grid_columnconfigure(0, weight=1)
        self.label(card, title, 12, self.t["muted"]).pack(anchor="w", padx=17, pady=(16,5))
        self.label(card, value, 25, color or self.t["text"], True).pack(anchor="w", padx=17)
        self.label(card, hint, 11, self.t["muted"]).pack(anchor="w", padx=17, pady=(3,16))
        return card

    def dashboard(self):
        income, expenses = self.db.totals(self.selected_month)
        lifetime_income, lifetime_expenses = self.db.lifetime_totals()
        balance = self.db.opening_balance() + lifetime_income - lifetime_expenses
        cards = ctk.CTkFrame(self.content, fg_color="transparent")
        cards.grid(row=0, column=0, sticky="ew", pady=(0,16))
        for i in range(3): cards.grid_columnconfigure(i, weight=1, uniform="stats")
        self.stat_card(cards, "TOTAL INCOME", money(income), self.selected_month, self.t["accent"]).grid(row=0,column=0,sticky="ew",padx=(0,7))
        self.stat_card(cards, "TOTAL EXPENSES", money(expenses), "Recorded expenses", self.t["red"]).grid(row=0,column=1,sticky="ew",padx=7)
        self.stat_card(cards, "CURRENT BALANCE", money(balance), "Starting balance + all-time activity", self.t["blue"] if balance >= 0 else self.t["red"]).grid(row=0,column=2,sticky="ew",padx=(7,0))

        quick = self.panel(self.content)
        quick.grid(row=1,column=0,sticky="ew",pady=(0,16))
        row = ctk.CTkFrame(quick,fg_color="transparent")
        row.pack(fill="x",padx=16,pady=14)
        self.label(row,"Quick actions",15,bold=True).pack(side="left",padx=(0,16))
        self.button(row,"＋  Add expense",lambda:self.transaction_dialog("expense"),True).pack(side="left",padx=4)
        self.button(row,"＋  Add income",lambda:self.transaction_dialog("income")).pack(side="left",padx=4)
        self.button(row,"◎  Set starting balance",self.set_starting_balance).pack(side="left",padx=4)
        self.button(row,"⇄  All transactions",lambda:self.show_page("Transactions")).pack(side="right")

        charts = ctk.CTkFrame(self.content, fg_color="transparent")
        charts.grid(row=2,column=0,sticky="ew",pady=(0,16))
        charts.grid_columnconfigure(0,weight=3,uniform="charts")
        charts.grid_columnconfigure(1,weight=2,uniform="charts")
        trend = self.panel(charts); trend.grid(row=0,column=0,sticky="nsew",padx=(0,8))
        cats = self.panel(charts); cats.grid(row=0,column=1,sticky="nsew",padx=(8,0))
        self.label(trend,"Daily income & expenses by weekday",15,bold=True).pack(anchor="w",padx=16,pady=(14,0))
        self.draw_weekly_stackplot(trend)
        self.label(cats,"Expenses by category",15,bold=True).pack(anchor="w",padx=16,pady=(14,0))
        self.draw_donut(cats)

        recent = self.panel(self.content)
        recent.grid(row=3,column=0,sticky="ew")
        head = ctk.CTkFrame(recent,fg_color="transparent"); head.pack(fill="x",padx=16,pady=(13,6))
        self.label(head,"Recent transactions",15,bold=True).pack(side="left")
        self.button(head,"View all",lambda:self.show_page("Transactions"),width=120).pack(side="right")
        rows = self.db.transactions(self.selected_month)[:5]
        if not rows:
            self.label(recent,"No transactions for this month yet.",12,self.t["muted"]).pack(anchor="w",padx=16,pady=14)
        else:
            for tx in rows:
                self.transaction_row(recent,tx,compact=True)

    def make_figure(self, figsize=(6,2.6)):
        fig = Figure(figsize=figsize, dpi=100, facecolor=self.t["panel"])
        return fig

    def set_starting_balance(self):
        """Set money already owned before tracking transactions; this is not income."""
        current = self.db.opening_balance()
        dialog = ctk.CTkToplevel(self)
        dialog.title("Set starting balance")
        dialog.geometry("420x235")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(fg_color=self.t["bg"])

        self.label(dialog, "Starting balance", 19, bold=True).pack(anchor="w", padx=22, pady=(20, 5))
        self.label(dialog, "Enter how much money you already had before recording transactions. This will not be counted as income.", 11, self.t["muted"]).pack(anchor="w", padx=22, pady=(0, 12))
        amount_var = tk.StringVar(value=f"{current:.2f}")
        entry = ctk.CTkEntry(dialog, textvariable=amount_var, height=40, font=("Segoe UI", 15))
        entry.pack(fill="x", padx=22)
        entry.focus_set()
        entry.select_range(0, "end")

        def save():
            raw = amount_var.get().strip().replace("€", "").replace(" ", "")
            # Accept either 125.50 or 125,50.
            if "," in raw and "." not in raw:
                raw = raw.replace(",", ".")
            else:
                raw = raw.replace(",", "")
            try:
                value = float(raw)
                if value < 0 or not math.isfinite(value):
                    raise ValueError
            except ValueError:
                messagebox.showerror("Invalid amount", "Enter a valid amount of 0 or more.", parent=dialog)
                return
            self.db.set_opening_balance(value)
            dialog.destroy()
            self.show_page("Dashboard")
            messagebox.showinfo("Starting balance saved", "Your starting balance has been saved. It is separate from income.", parent=self)

        buttons = ctk.CTkFrame(dialog, fg_color="transparent")
        buttons.pack(fill="x", padx=22, pady=18)
        self.button(buttons, "Cancel", dialog.destroy).pack(side="right", padx=(8, 0))
        self.button(buttons, "Save balance", save, True).pack(side="right")
        dialog.bind("<Return>", lambda _event: save())

    def draw_weekly_stackplot(self, parent):
        # Group all transactions in the selected month by weekday.
        # Each weekday has two side-by-side bars: income and expenses.
        fig = self.make_figure((6, 2.5))
        ax = fig.add_subplot(111)
        labels = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        expenses = [0.0] * 7
        income = [0.0] * 7

        for tx in self.db.transactions(self.selected_month):
            tx_date = date.fromisoformat(tx["tx_date"])
            idx = tx_date.weekday()  # Monday=0 ... Sunday=6
            (income if tx["kind"] == "income" else expenses)[idx] += float(tx["amount"])

        xs = list(range(7))
        width = 0.36
        ax.bar([i - width / 2 for i in xs], income, width=width,
               label="Income", color=self.t["accent"])
        ax.bar([i + width / 2 for i in xs], expenses, width=width,
               label="Expenses", color=self.t["red"])
        ax.set_facecolor(self.t["panel"])
        ax.set_xticks(xs)
        ax.set_xticklabels(labels, rotation=25, ha="right")
        ax.tick_params(colors=self.t["muted"], labelsize=8)
        for sp in ax.spines.values():
            sp.set_color(self.t["border"])
        ax.grid(axis="y", color=self.t["chart_grid"], linewidth=.6)
        ax.set_axisbelow(True)
        ax.set_ylabel("€", color=self.t["muted"], fontsize=8)
        ax.legend(frameon=False, labelcolor=self.t["text"], fontsize=8, loc="upper left")
        fig.tight_layout(pad=1.4)
        canvas = FigureCanvasTkAgg(fig, master=parent)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def draw_donut(self, parent):
        fig = self.make_figure((4.4,2.5))
        ax = fig.add_subplot(111)
        data = self.db.category_totals(self.selected_month)
        if data:
            vals = [float(r["total"]) for r in data]
            labels = [r["category"] for r in data]
            palette = [self.t["accent"],self.t["blue"],self.t["purple"],"#F7B267","#FF6B78","#47C9AF","#D8DDE5"]
            wedges, _ = ax.pie(vals, startangle=90, colors=palette*3, wedgeprops=dict(width=.36, edgecolor=self.t["panel"]))
            ax.legend(wedges, [f"{l}  {money(v)}" for l,v in zip(labels,vals)], loc="center left",
                      bbox_to_anchor=(.82,.5), frameon=False, labelcolor=self.t["text"], fontsize=7)
            ax.set_position([.02,.02,.7,.9])
        else:
            ax.text(.5,.55,"No data yet",ha="center",va="center",color=self.t["muted"],fontsize=12)
            ax.text(.5,.4,"Add your first expense",ha="center",va="center",color=self.t["muted"],fontsize=8)
        ax.set_facecolor(self.t["panel"])
        fig.tight_layout(pad=.5)
        canvas = FigureCanvasTkAgg(fig, master=parent)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both",expand=True,padx=5,pady=(0,8))

    def transaction_row(self, parent, tx, compact=False):
        row = ctk.CTkFrame(parent,fg_color="transparent")
        row.pack(fill="x",padx=14,pady=4)
        icon = CATEGORIES.get(tx["category"],"•")
        self.label(row,icon,18).pack(side="left",padx=(0,10))
        info = ctk.CTkFrame(row,fg_color="transparent")
        info.pack(side="left",fill="x",expand=True)
        desc = tx["description"].strip() or tx["category"]
        self.label(info,desc,12,bold=True).pack(anchor="w")
        self.label(info,f'{tx["category"]}  •  {tx["tx_date"]}',10,self.t["muted"]).pack(anchor="w")
        amount = float(tx["amount"])
        sign = "+" if tx["kind"]=="income" else "−"
        col = self.t["accent"] if tx["kind"]=="income" else self.t["red"]
        self.label(row,f"{sign}{money(amount)}",12,col,True).pack(side="right",padx=(8,12))
        if not compact:
            self.button(row,"✎",lambda i=tx["id"]:self.transaction_dialog(None,i),width=36).pack(side="right",padx=3)
            self.button(row,"×",lambda i=tx["id"]:self.delete_transaction(i),width=36).pack(side="right",padx=3)
        ctk.CTkFrame(parent,height=1,fg_color=self.t["border"]).pack(fill="x",padx=14,pady=(3,0))

    def transactions_page(self):
        toolbar = self.panel(self.content); toolbar.grid(row=0,column=0,sticky="ew",pady=(0,12))
        top = ctk.CTkFrame(toolbar,fg_color="transparent"); top.pack(fill="x",padx=12,pady=12)
        self.search_var.set("")
        search = ctk.CTkEntry(top,textvariable=self.search_var,placeholder_text="Search description or category…",width=300)
        search.pack(side="left",padx=(0,8))
        filt = ctk.CTkOptionMenu(top,values=["All","Expenses","Income"],variable=self.filter_var,
                                 fg_color=self.t["panel2"],button_color=self.t["accent"],text_color=self.t["text"],
                                 command=lambda _:self.refresh_transactions())
        filt.pack(side="left",padx=4)
        self.button(top,"Search",self.refresh_transactions).pack(side="left",padx=6)
        self.button(top,"＋ New transaction",lambda:self.transaction_dialog("expense"),True).pack(side="right")
        self.button(top,"Reset transactions",self.reset_transactions).pack(side="right",padx=(0,8))
        self.tx_list = self.panel(self.content); self.tx_list.grid(row=1,column=0,sticky="ew")
        self.refresh_transactions()

    def reset_transactions(self):
        count = self.db.conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        if count == 0:
            messagebox.showinfo("Nothing to reset", "There are no transactions to delete.", parent=self)
            return
        confirmed = messagebox.askyesno(
            "Reset all transactions?",
            f"This will permanently delete all {count} transactions, including income and expenses.\n\n"
            "Budgets and savings goals will be kept. This cannot be undone.\n\nContinue?",
            icon="warning", parent=self
        )
        if not confirmed:
            return
        self.db.execute("DELETE FROM transactions")
        self.refresh_transactions()
        messagebox.showinfo(
            "Transactions reset",
            "All transactions have been deleted. Your budgets and savings goals are still there.",
            parent=self
        )

    def refresh_transactions(self):
        if not hasattr(self,"tx_list") or not self.tx_list.winfo_exists(): return
        for child in self.tx_list.winfo_children(): child.destroy()
        kind = {"Expenses":"expense","Income":"income"}.get(self.filter_var.get())
        rows = self.db.transactions(self.selected_month,kind,self.search_var.get().strip())
        if not rows:
            self.label(self.tx_list,"No transactions found. Try another search or add one.",12,self.t["muted"]).pack(padx=18,pady=30)
        else:
            for tx in rows: self.transaction_row(self.tx_list,tx)

    def choose_date(self, parent, target_entry, initial_date=None, allow_clear=False):
        """Open a compact calendar and write the selected date into an entry."""
        popup = ctk.CTkToplevel(parent)
        popup.title("Choose a date")
        popup.resizable(False, False)
        popup.transient(parent)
        popup.grab_set()
        popup.configure(fg_color=self.t["panel"])
        try:
            start_date = datetime.strptime(initial_date, "%Y-%m-%d").date() if initial_date else date.today()
        except ValueError:
            start_date = date.today()

        cal = Calendar(
            popup, selectmode="day", year=start_date.year, month=start_date.month,
            day=start_date.day, date_pattern="yyyy-mm-dd",
            background=self.t["panel"], foreground=self.t["text"],
            bordercolor=self.t["border"], headersbackground=self.t["panel2"],
            headersforeground=self.t["text"], selectbackground=self.t["accent"],
            selectforeground="#10151C", normalbackground=self.t["panel"],
            normalforeground=self.t["text"], weekendbackground=self.t["panel"],
            weekendforeground=self.t["muted"], othermonthbackground=self.t["panel"],
            othermonthforeground=self.t["muted"], othermonthwebackground=self.t["panel"],
            othermonthweforeground=self.t["muted"])
        cal.pack(padx=12, pady=(12, 8))
        controls = ctk.CTkFrame(popup, fg_color="transparent")
        controls.pack(fill="x", padx=12, pady=(0, 12))

        def write_value(value):
            target_entry.configure(state="normal")
            target_entry.delete(0, "end")
            if value:
                target_entry.insert(0, value)
            target_entry.configure(state="readonly")
            popup.destroy()

        self.button(controls, "Cancel", popup.destroy, width=90).pack(side="right", padx=(6, 0))
        self.button(controls, "Use selected date", lambda: write_value(cal.get_date()), primary=True, width=145).pack(side="right")
        if allow_clear:
            self.button(controls, "No deadline", lambda: write_value(""), width=100).pack(side="left")
        popup.update_idletasks()
        x = parent.winfo_rootx() + max(20, (parent.winfo_width() - popup.winfo_width()) // 2)
        y = parent.winfo_rooty() + max(20, (parent.winfo_height() - popup.winfo_height()) // 2)
        popup.geometry(f"+{x}+{y}")

    def transaction_dialog(self, kind="expense", tx_id=None):
        existing = None
        if tx_id:
            existing = self.db.conn.execute("SELECT * FROM transactions WHERE id=?",(tx_id,)).fetchone()
            if not existing: return
            kind = existing["kind"]
        win = ctk.CTkToplevel(self)
        win.title("Edit transaction" if existing else "New transaction")
        win.geometry("430x570"); win.resizable(False,False); win.transient(self); win.grab_set()
        win.configure(fg_color=self.t["bg"])
        frame = ctk.CTkFrame(win,fg_color=self.t["panel"],corner_radius=16)
        frame.pack(fill="both",expand=True,padx=18,pady=18)
        self.label(frame,"Edit transaction" if existing else "New transaction",21,bold=True).pack(anchor="w",padx=20,pady=(20,16))
        kind_var = tk.StringVar(value=kind)
        self.label(frame,"Type",11,self.t["muted"]).pack(anchor="w",padx=20)
        kind_menu = ctk.CTkSegmentedButton(frame,values=["expense","income"],variable=kind_var,
                                           command=lambda _:update_categories())
        kind_menu.pack(fill="x",padx=20,pady=(5,12))
        self.label(frame,"Amount (€)",11,self.t["muted"]).pack(anchor="w",padx=20)
        amount = ctk.CTkEntry(frame,placeholder_text="e.g. 12.50")
        amount.pack(fill="x",padx=20,pady=(5,12))
        if existing: amount.insert(0,str(existing["amount"]))
        self.label(frame,"Category",11,self.t["muted"]).pack(anchor="w",padx=20)
        cat_var = tk.StringVar(value=existing["category"] if existing else (EXPENSE_CATEGORIES[0] if kind=="expense" else "Salary"))
        cat_menu = ctk.CTkOptionMenu(frame,variable=cat_var,values=EXPENSE_CATEGORIES,
                                    fg_color=self.t["panel2"],button_color=self.t["accent"],text_color=self.t["text"])
        cat_menu.pack(fill="x",padx=20,pady=(5,12))
        self.label(frame,"Description",11,self.t["muted"]).pack(anchor="w",padx=20)
        desc = ctk.CTkEntry(frame,placeholder_text="e.g. weekly groceries")
        desc.pack(fill="x",padx=20,pady=(5,12))
        if existing: desc.insert(0,existing["description"])
        self.label(frame,"Date",11,self.t["muted"]).pack(anchor="w",padx=20)
        date_row = ctk.CTkFrame(frame, fg_color="transparent")
        date_row.pack(fill="x", padx=20, pady=(5,16))
        dt = ctk.CTkEntry(date_row, state="readonly")
        dt.pack(side="left", fill="x", expand=True, padx=(0,8))
        dt.configure(state="normal")
        dt.insert(0,existing["tx_date"] if existing else date.today().isoformat())
        dt.configure(state="readonly")
        self.button(date_row, "▦  Calendar", lambda: self.choose_date(win, dt, dt.get()), width=115).pack(side="right")

        def update_categories(*_):
            vals = EXPENSE_CATEGORIES if kind_var.get()=="expense" else INCOME_CATEGORIES
            cat_menu.configure(values=vals)
            if cat_var.get() not in vals: cat_var.set(vals[0])
        update_categories()
        def save():
            try:
                val = float(amount.get().strip().replace(",","."))
                if val <= 0: raise ValueError
            except ValueError:
                messagebox.showerror("Check amount","Amount must be a number greater than zero.",parent=win); return
            try: datetime.strptime(dt.get().strip(),"%Y-%m-%d")
            except ValueError:
                messagebox.showerror("Check date","Choose a valid date from the calendar.",parent=win); return
            if kind_var.get() not in ("expense","income"): return
            params=(kind_var.get(),val,cat_var.get(),desc.get().strip(),dt.get().strip())
            if existing:
                self.db.execute("UPDATE transactions SET kind=?,amount=?,category=?,description=?,tx_date=? WHERE id=?",params+(tx_id,))
            else:
                self.db.execute("INSERT INTO transactions(kind,amount,category,description,tx_date) VALUES(?,?,?,?,?)",params)
            win.destroy(); self.show_page(self.current_page)
        self.button(frame,"Save",save,True).pack(fill="x",padx=20,pady=(0,20))

    def delete_transaction(self, tx_id):
        if messagebox.askyesno("Delete","Delete this transaction?"):
            self.db.execute("DELETE FROM transactions WHERE id=?",(tx_id,))
            self.show_page(self.current_page)

    def budgets_page(self):
        add = self.panel(self.content); add.grid(row=0,column=0,sticky="ew",pady=(0,14))
        self.label(add,"New monthly budget",15,bold=True).pack(anchor="w",padx=16,pady=(14,8))
        row=ctk.CTkFrame(add,fg_color="transparent"); row.pack(fill="x",padx=14,pady=(0,14))
        cat=tk.StringVar(value=EXPENSE_CATEGORIES[0]); amt=tk.StringVar()
        ctk.CTkOptionMenu(row,variable=cat,values=EXPENSE_CATEGORIES,width=190,fg_color=self.t["panel2"],button_color=self.t["accent"],text_color=self.t["text"]).pack(side="left",padx=4)
        ctk.CTkEntry(row,textvariable=amt,placeholder_text="Limit in €",width=150).pack(side="left",padx=4)
        self.button(row,"Save budget",lambda:self.save_budget(cat.get(),amt.get()),True).pack(side="left",padx=4)
        self.label(add,"Budgets are monthly and apply to the selected month.",11,self.t["muted"]).pack(anchor="w",padx=18,pady=(0,12))
        wrap=self.panel(self.content); wrap.grid(row=1,column=0,sticky="ew")
        self.label(wrap,f"Budget progress · {self.selected_month}",15,bold=True).pack(anchor="w",padx=16,pady=(14,10))
        budgets=self.db.conn.execute("SELECT * FROM budgets ORDER BY category").fetchall()
        if not budgets: self.label(wrap,"You have not set any budgets yet.",12,self.t["muted"]).pack(anchor="w",padx=16,pady=18)
        for b in budgets:
            spentrow=self.db.conn.execute("SELECT COALESCE(SUM(amount),0) n FROM transactions WHERE kind='expense' AND category=? AND substr(tx_date,1,7)=?",(b["category"],self.selected_month)).fetchone()
            spent=float(spentrow["n"]); limit=float(b["monthly_limit"]); pct=spent/limit if limit else 0
            line=ctk.CTkFrame(wrap,fg_color="transparent"); line.pack(fill="x",padx=16,pady=8)
            info=ctk.CTkFrame(line,fg_color="transparent"); info.pack(fill="x")
            self.label(info,f'{CATEGORIES.get(b["category"],"•")}  {b["category"]}',12,bold=True).pack(side="left")
            self.label(info,f"{money(spent)} / {money(limit)}  ({pct*100:.0f}%)",11,self.t["red"] if pct>=1 else self.t["muted"]).pack(side="right")
            bar=ctk.CTkProgressBar(line,progress_color=self.t["red"] if pct>=1 else self.t["accent"],fg_color=self.t["panel2"],height=9)
            bar.pack(fill="x",pady=(7,3)); bar.set(min(pct,1))
            controls=ctk.CTkFrame(line,fg_color="transparent"); controls.pack(fill="x")
            self.label(controls,"Over budget" if pct>1 else f"{money(max(0,limit-spent))} remaining",10,self.t["red"] if pct>1 else self.t["muted"]).pack(side="left")
            self.button(controls,"Delete",lambda i=b["id"]:self.delete_budget(i),width=80).pack(side="right")
            ctk.CTkFrame(wrap,height=1,fg_color=self.t["border"]).pack(fill="x",padx=16,pady=4)

    def save_budget(self, category, amount):
        try:
            val=float(amount.strip().replace(",","."))
            if val<=0: raise ValueError
        except ValueError:
            messagebox.showerror("Invalid budget","Enter an amount greater than zero."); return
        self.db.execute("INSERT INTO budgets(category,monthly_limit) VALUES(?,?) ON CONFLICT(category) DO UPDATE SET monthly_limit=excluded.monthly_limit",(category,val))
        self.show_page("Budgets")

    def delete_budget(self, budget_id):
        if messagebox.askyesno("Delete budget","Delete this budget?"):
            self.db.execute("DELETE FROM budgets WHERE id=?",(budget_id,)); self.show_page("Budgets")

    def goals_page(self):
        add=self.panel(self.content); add.grid(row=0,column=0,sticky="ew",pady=(0,14))
        self.label(add,"Create a savings goal",15,bold=True).pack(anchor="w",padx=16,pady=(14,8))
        row=ctk.CTkFrame(add,fg_color="transparent"); row.pack(fill="x",padx=12,pady=(0,12))
        name=tk.StringVar(); target=tk.StringVar(); saved=tk.StringVar(value="0"); deadline=tk.StringVar()
        ctk.CTkEntry(row,textvariable=name,placeholder_text="Goal name",width=220).pack(side="left",padx=4)
        ctk.CTkEntry(row,textvariable=target,placeholder_text="Target €",width=120).pack(side="left",padx=4)
        ctk.CTkEntry(row,textvariable=saved,placeholder_text="Already saved €",width=150).pack(side="left",padx=4)
        deadline_entry = ctk.CTkEntry(row, textvariable=deadline, placeholder_text="Optional deadline", width=150, state="readonly")
        deadline_entry.pack(side="left",padx=4)
        self.button(row,"▦",lambda:self.choose_date(self,deadline_entry,deadline.get() or None,allow_clear=True),width=38).pack(side="left",padx=(0,4))
        self.button(row,"＋ Add goal",lambda:self.save_goal(name.get(),target.get(),saved.get(),deadline.get()),True).pack(side="left",padx=4)
        goals=self.db.conn.execute("SELECT * FROM goals ORDER BY id DESC").fetchall()
        if not goals:
            empty=self.panel(self.content); empty.grid(row=1,column=0,sticky="ew")
            self.label(empty,"No goals yet. Create one to track your progress.",12,self.t["muted"]).pack(padx=20,pady=28)
        for g in goals:
            card=self.panel(self.content); card.grid(sticky="ew",pady=7)
            top=ctk.CTkFrame(card,fg_color="transparent"); top.pack(fill="x",padx=16,pady=(14,6))
            self.label(top,"◎",24,self.t["accent"],True).pack(side="left",padx=(0,12))
            inf=ctk.CTkFrame(top,fg_color="transparent"); inf.pack(side="left",fill="x",expand=True)
            self.label(inf,g["name"],15,bold=True).pack(anchor="w")
            self.label(inf,(f'Deadline: {g["deadline"]}' if g["deadline"] else "No deadline"),10,self.t["muted"]).pack(anchor="w")
            pct=float(g["saved"])/float(g["target"])
            self.label(top,f'{money(g["saved"])} / {money(g["target"])}',12,self.t["accent"],True).pack(side="right",padx=10)
            bar=ctk.CTkProgressBar(card,progress_color=self.t["accent"],fg_color=self.t["panel2"],height=10)
            bar.pack(fill="x",padx=18,pady=(4,6)); bar.set(min(pct,1))
            foot=ctk.CTkFrame(card,fg_color="transparent"); foot.pack(fill="x",padx=16,pady=(0,12))
            self.label(foot,f"{pct*100:.0f}% complete · {money(max(0,float(g['target'])-float(g['saved'])))} remaining",10,self.t["muted"]).pack(side="left")
            self.button(foot,"＋ Add money",lambda i=g["id"]:self.contribute_goal(i),width=160).pack(side="right",padx=4)
            self.button(foot,"Delete",lambda i=g["id"]:self.delete_goal(i),width=80).pack(side="right",padx=4)

    def save_goal(self,name,target,saved,deadline):
        name=name.strip()
        try:
            target=float(target.strip().replace(",","."))
            saved=float(saved.strip().replace(",",".") or "0")
            if not name or target<=0 or saved<0: raise ValueError
        except ValueError:
            messagebox.showerror("Check details","Enter a name, a target above 0, and savings of 0 or more."); return
        deadline=deadline.strip()
        if deadline:
            try: datetime.strptime(deadline,"%Y-%m-%d")
            except ValueError:
                messagebox.showerror("Invalid date","Deadline must use YYYY-MM-DD."); return
        self.db.execute("INSERT INTO goals(name,target,saved,deadline) VALUES(?,?,?,?)",(name,target,saved,deadline))
        self.show_page("Goals")

    def contribute_goal(self,goal_id):
        win=ctk.CTkInputDialog(text="How many euros would you like to add to this goal?",title="Update savings")
        val=win.get_input()
        if val is None:return
        try: amount=float(val.strip().replace(",","."))
        except ValueError:
            messagebox.showerror("Invalid amount","Enter a valid number."); return
        if amount<=0:
            messagebox.showerror("Invalid amount","Amount must be greater than zero."); return
        self.db.execute("UPDATE goals SET saved=saved+? WHERE id=?",(amount,goal_id)); self.show_page("Goals")

    def delete_goal(self,goal_id):
        if messagebox.askyesno("Delete goal","Delete this goal?"):
            self.db.execute("DELETE FROM goals WHERE id=?",(goal_id,)); self.show_page("Goals")

    def reports_page(self):
        income,expenses=self.db.totals(self.selected_month)
        cards=ctk.CTkFrame(self.content,fg_color="transparent"); cards.grid(row=0,column=0,sticky="ew",pady=(0,14))
        for i in range(3):cards.grid_columnconfigure(i,weight=1,uniform="r")
        self.stat_card(cards,"INCOME",money(income),"Selected month",self.t["accent"]).grid(row=0,column=0,sticky="ew",padx=(0,7))
        self.stat_card(cards,"EXPENSES",money(expenses),"Selected month",self.t["red"]).grid(row=0,column=1,sticky="ew",padx=7)
        self.stat_card(cards,"SAVINGS RATE",f"{(income-expenses)/income*100:.1f}%" if income else "—","(Income − expenses) / income" if income else "No income this month",self.t["blue"]).grid(row=0,column=2,sticky="ew",padx=(7,0))
        chart=self.panel(self.content); chart.grid(row=1,column=0,sticky="ew",pady=(0,14))
        self.label(chart,"Last 6 months comparison",15,bold=True).pack(anchor="w",padx=16,pady=(14,0))
        self.draw_history(chart)
        breakdown=self.panel(self.content); breakdown.grid(row=2,column=0,sticky="ew",pady=(0,14))
        self.label(breakdown,"Expense breakdown by category",15,bold=True).pack(anchor="w",padx=16,pady=(14,8))
        data=self.db.category_totals(self.selected_month)
        total=sum(float(r["total"]) for r in data)
        if not data:self.label(breakdown,"No expenses for the selected month.",12,self.t["muted"]).pack(anchor="w",padx=16,pady=12)
        for r in data:
            val=float(r["total"]); pct=val/total if total else 0
            line=ctk.CTkFrame(breakdown,fg_color="transparent");line.pack(fill="x",padx=16,pady=5)
            self.label(line,f'{CATEGORIES.get(r["category"],"•")}  {r["category"]}',12).pack(side="left")
            self.label(line,f"{money(val)}  ·  {pct*100:.1f}%",11,self.t["muted"]).pack(side="right")
        actions=ctk.CTkFrame(self.content,fg_color="transparent");actions.grid(row=3,column=0,sticky="ew")
        self.button(actions,"Export transactions to CSV",self.export_csv,True).pack(side="left")
        self.button(actions,"Back up database",self.backup_db).pack(side="left",padx=8)

    def draw_history(self,parent):
        fig=self.make_figure((9,3))
        ax=fig.add_subplot(111)
        months=[]
        cur=parse_month(self.selected_month)
        for offset in range(5,-1,-1):
            y=cur.year; m=cur.month-offset
            while m<=0:y-=1;m+=12
            months.append(date(y,m,1))
        labels=[]; inc=[]; exp=[]
        for d in months:
            key=d.strftime("%Y-%m"); a,b=self.db.totals(key)
            labels.append(d.strftime("%b %y"));inc.append(a);exp.append(b)
        x=list(range(6));w=.36
        ax.bar([i-w/2 for i in x],inc,width=w,label="Income",color=self.t["accent"])
        ax.bar([i+w/2 for i in x],exp,width=w,label="Expenses",color=self.t["red"])
        ax.set_xticks(x,labels)
        ax.set_facecolor(self.t["panel"]);ax.tick_params(colors=self.t["muted"],labelsize=9)
        for sp in ax.spines.values():sp.set_color(self.t["border"])
        ax.grid(axis="y",color=self.t["chart_grid"],linewidth=.6);ax.set_axisbelow(True)
        ax.legend(frameon=False,labelcolor=self.t["text"])
        fig.tight_layout(pad=1.4)
        canvas=FigureCanvasTkAgg(fig,master=parent);canvas.draw()
        canvas.get_tk_widget().pack(fill="both",expand=True,padx=8,pady=(0,10))

    def export_csv(self):
        path=filedialog.asksaveasfilename(title="Export transactions",defaultextension=".csv",
            initialfile=f"lukefinance-{self.selected_month}.csv",filetypes=[("CSV","*.csv")])
        if not path:return
        rows=self.db.transactions(self.selected_month)
        try:
            with open(path,"w",newline="",encoding="utf-8-sig") as f:
                writer=csv.writer(f,delimiter=";")
                writer.writerow(["ID","Type","Amount EUR","Category","Description","Date"])
                for r in rows:writer.writerow([r["id"],"Income" if r["kind"]=="income" else "Expense",r["amount"],r["category"],r["description"],r["tx_date"]])
            messagebox.showinfo("Done",f"File saved to:\n{path}")
        except OSError as e:messagebox.showerror("Export error",str(e))

    def backup_db(self):
        path=filedialog.asksaveasfilename(title="Database backup",defaultextension=".db",
            initialfile="lukefinance-backup.db",filetypes=[("SQLite database","*.db")])
        if not path:return
        try:
            dest=sqlite3.connect(path)
            self.db.conn.backup(dest)
            dest.close()
            messagebox.showinfo("Done",f"Backup saved to:\n{path}")
        except sqlite3.Error as e:messagebox.showerror("Backup error",str(e))

    def toggle_theme(self):
        self.theme_name="light" if self.theme_name=="dark" else "dark"
        self.t=THEMES[self.theme_name]
        ctk.set_appearance_mode(self.theme_name)
        self.show_page(self.current_page)
        # Rebuild shell colours and navigation consistently.
        self.sidebar.configure(fg_color=self.t["panel"])
        self.main.configure(fg_color=self.t["bg"])
        self.content.configure(fg_color="transparent")
        self.header.configure(fg_color="transparent")
        self.page_title.configure(text_color=self.t["text"])
        self.page_subtitle.configure(text_color=self.t["muted"])
        self.month_button.configure(fg_color=self.t["panel"], hover_color=self.t["panel2"],
                                     border_color=self.t["border"], text_color=self.t["text"])
        for title,b in self.nav_buttons.items():
            active=title==self.current_page
            b.configure(fg_color=self.t["panel2"] if active else "transparent",hover_color=self.t["panel2"],
                         text_color=self.t["accent"] if active else self.t["text"])
        self.theme_button.configure(fg_color=self.t["panel2"],hover_color=self.t["border"],text_color=self.t["text"])

    def on_close(self):
        self.db.close()
        self.destroy()

if __name__ == "__main__":
    app=FinanceApp()
    app.mainloop()
