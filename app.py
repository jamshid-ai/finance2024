from datetime import datetime
import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd, validate_register_form, validate_stock_form

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    if not db.execute("SELECT * FROM users INNER JOIN transactions ON users.id = transactions.user_id WHERE user_id = ?", session.get("user_id")):
        rows = db.execute("SELECT * FROM users WHERE id = ?", session.get("user_id"))

        cash = rows[0]["cash"]
        total = cash

        return render_template("index.html",cash=usd(cash),total=usd(total))

    rows = db.execute("SELECT symbol, SUM(shares), cash FROM transactions INNER JOIN users ON users.id = transactions.user_id WHERE user_id = ? GROUP BY symbol", session.get("user_id"))

    total_grand = 0
    cash = rows[0]["cash"]

    for row in rows:
        if row["SUM(shares)"] > 0:
            quote = lookup(row["symbol"])
            row["name"] = quote["symbol"]
            row["price_actual"] = usd(quote["price"])
            total_holding = quote["price"] * row["SUM(shares)"]
            row["total_holding"] = usd(total_holding)
            total_grand += total_holding

    total_grand += cash

    return render_template("index.html", rows=rows, cash=usd(cash), total_grand=usd(total_grand))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        if not request.form.get("symbol") and not request.form.get("shares"):
            return apology("Invalid form")
        stock = lookup(request.form.get("symbol"))
        if not stock:
            return apology("There is no such stock!")
        if int(request.form.get("shares")) < 1:
            return apology("Enter Positive Shares")
        # TODO: check user's cash
        cash = db.execute("SELECT cash from users WHERE id = ?", session.get("user_id"))
        if cash[0].get("cash") < stock.get("price") * int(request.form.get("shares")):
            return apology("You dont have enough cash!")
        db.execute("""CREATE TABLE IF NOT EXISTS transactions (
id INTEGER NOT NULL,
user_id INTEGER NOT NULL,
symbol TEXT NOT NULL,
shares NUMERIC NOT NULL,
price NUMERIC NOT NULL,
created_at DATETIME NOT NULL,
FOREIGN KEY (user_id)
REFERENCES users (id)
PRIMARY KEY (id AUTOINCREMENT));
                   """)
        # TODO: Add to transactions
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price, created_at) VALUES(?, ?, ?, ?, ?)", session.get("user_id"), request.form.get("symbol"), request.form.get("shares"), usd(stock.get("price")), datetime.now())
        # TODO: Update user's cash
        updated_cash = cash[0].get("cash") - stock.get("price") * int(request.form.get("shares"))
        db.execute("UPDATE users SET cash = ? WHERE id = ?", updated_cash, session.get("user_id"))
        return redirect("/")
    return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    rows = db.execute(
        "SELECT symbol, shares, price, created_at, cash FROM transactions INNER JOIN users ON users.id = transactions.user_id WHERE user_id = ?",
        session.get("user_id"))

    return render_template("history.html",
                           rows=rows)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        return render_template("quoted.html", context=lookup(request.form.get("symbol")))
    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == 'POST':
        if validate_register_form(request.form):
            ### TODO: 
            # 1. check username from db
            # 2. if username doesnt exist in db . register user else reutrn apology
            username = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
            if username:
                return apology("This username is taken")
            db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", request.form.get("username"), generate_password_hash(request.form.get("password")))
            return render_template("login.html")
        else:
            return apology("Invalid form")

    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    stocks = db.execute("SELECT DISTINCT symbol FROM transactions WHERE user_id = ?", session.get("user_id"))
    if request.method == "POST":
        if not request.form.get("shares") or not request.form.get("stock"):
            return apology("Invalid form", 400)
        if int(request.form.get("shares")) < 0:
            return apology("Enter positive shares", 400)
        shares_sum = db.execute("SELECT SUM(shares) AS shares FROM transactions WHERE user_id = ? AND symbol = ?", session.get("user_id"), request.form.get("stock"))
        if shares_sum[0]['shares'] < int(request.form.get("shares")):
            return apology(f"You don't have {request.form.get('shares')} shares", 400)

        # lookup stock and its price
        quote = lookup(request.form.get("stock"))
        # income = quote["price"] * int(request.form.get("shares"))

        db.execute(
            "INSERT INTO transactions (user_id, symbol, shares, price, created_at) VALUES (?, ?, ?, ?, ?)",
            session["user_id"],
            request.form.get("stock"),
            "-"+request.form.get("shares"),
            usd(quote["price"]),
            datetime.now())
        # update_cash
        cash = db.execute("SELECT cash from users WHERE id = ?", session.get("user_id"))
        updated_cash = cash[0].get("cash") + quote.get("price") * int(request.form.get("shares"))
        db.execute("UPDATE users SET cash = ? WHERE id = ?", updated_cash, session.get("user_id"))
        return redirect("/")
    return render_template("sell.html", stocks=stocks)

if __name__ == "__name__":
    app.run(host="127.0.0.1", port=5510)