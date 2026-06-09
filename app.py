from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, os, functools, json
from datetime import datetime, timedelta, date as date_type

app = Flask(__name__)
app.secret_key = "muscle-meal-plan-secret-key-change-in-production"
DB_PATH = "muscle_meal.db"

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MEAL_TYPES = ["breakfast", "lunch", "dinner", "snack"]


# ── DB helpers ──────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS customer_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            age INTEGER,
            weight_kg REAL,
            height_cm REAL,
            goal TEXT,
            plan_type TEXT,
            nutritionist_id INTEGER DEFAULT NULL,
            status TEXT DEFAULT 'active',
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(nutritionist_id) REFERENCES nutritionist_profiles(id)
        );
        CREATE TABLE IF NOT EXISTS nutritionist_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            specialization TEXT,
            experience_years INTEGER,
            max_clients INTEGER DEFAULT 10,
            bio TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS food_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            meal_type TEXT NOT NULL,
            calories_per_100g REAL NOT NULL,
            protein_per_100g REAL NOT NULL,
            carbs_per_100g REAL NOT NULL,
            fat_per_100g REAL NOT NULL,
            default_serving_g REAL DEFAULT 100
        );
        CREATE TABLE IF NOT EXISTS meal_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            nutritionist_id INTEGER NOT NULL,
            week_start_date TEXT NOT NULL,
            daily_calories INTEGER,
            daily_protein_g REAL,
            daily_carbs_g REAL,
            daily_fat_g REAL,
            notes TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(customer_id) REFERENCES customer_profiles(id),
            FOREIGN KEY(nutritionist_id) REFERENCES nutritionist_profiles(id)
        );
        CREATE TABLE IF NOT EXISTS meal_plan_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meal_plan_id INTEGER NOT NULL,
            day_of_week INTEGER NOT NULL,
            meal_type TEXT NOT NULL,
            food_item_id INTEGER NOT NULL,
            quantity_g REAL DEFAULT 100,
            FOREIGN KEY(meal_plan_id) REFERENCES meal_plans(id),
            FOREIGN KEY(food_item_id) REFERENCES food_items(id)
        );
        CREATE TABLE IF NOT EXISTS meal_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meal_plan_item_id INTEGER NOT NULL,
            customer_user_id INTEGER NOT NULL,
            log_date TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            logged_at TIMESTAMP,
            FOREIGN KEY(meal_plan_item_id) REFERENCES meal_plan_items(id),
            FOREIGN KEY(customer_user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS meal_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meal_log_id INTEGER NOT NULL,
            customer_user_id INTEGER NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(meal_log_id) REFERENCES meal_logs(id),
            FOREIGN KEY(customer_user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS weight_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_user_id INTEGER NOT NULL,
            weight_kg REAL NOT NULL,
            log_date TEXT NOT NULL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(customer_user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_user_id INTEGER NOT NULL,
            receiver_user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_read INTEGER DEFAULT 0,
            FOREIGN KEY(sender_user_id) REFERENCES users(id),
            FOREIGN KEY(receiver_user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_user_id INTEGER NOT NULL,
            alert_type TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_read INTEGER DEFAULT 0,
            FOREIGN KEY(customer_user_id) REFERENCES users(id)
        );
        """)
    seed_food_database()

FOOD_SEED = [
    # (name, category, meal_type, cal/100g, p/100g, c/100g, f/100g, serving_g)
    # BREAKFAST - VEG
    ("Poha", "veg", "breakfast", 130, 2.5, 28.0, 1.5, 150),
    ("Upma", "veg", "breakfast", 150, 3.5, 25.0, 4.0, 150),
    ("Idli (4 pcs)", "veg", "breakfast", 58, 2.7, 12.0, 0.3, 240),
    ("Plain Dosa", "veg", "breakfast", 133, 2.9, 23.0, 3.0, 100),
    ("Masala Dosa", "veg", "breakfast", 175, 4.5, 30.0, 4.5, 200),
    ("Oats Porridge", "veg", "breakfast", 70, 2.5, 12.0, 1.5, 250),
    ("Whole Wheat Paratha", "veg", "breakfast", 215, 5.5, 33.0, 7.0, 150),
    ("Aloo Paratha", "veg", "breakfast", 260, 5.0, 40.0, 8.5, 150),
    ("Dhokla", "veg", "breakfast", 160, 6.5, 28.0, 2.0, 150),
    ("Moong Dal Chilla", "veg", "breakfast", 180, 10.0, 24.0, 4.5, 150),
    ("Besan Chilla", "veg", "breakfast", 195, 9.0, 26.0, 5.0, 150),
    ("Rava Uttapam", "veg", "breakfast", 145, 4.0, 26.0, 2.5, 150),
    ("Methi Thepla", "veg", "breakfast", 240, 7.0, 35.0, 8.0, 120),
    ("Bread Toast", "veg", "breakfast", 265, 8.5, 46.0, 5.0, 100),
    ("Sprouts Salad", "veg", "breakfast", 85, 6.5, 14.0, 0.5, 150),
    # BREAKFAST - NON VEG
    ("Egg Bhurji", "non_veg", "breakfast", 155, 10.5, 3.5, 11.0, 150),
    ("Boiled Eggs (2)", "non_veg", "breakfast", 155, 13.0, 1.0, 11.0, 100),
    ("Omelette", "non_veg", "breakfast", 165, 11.0, 2.0, 13.0, 100),
    ("Egg Paratha", "non_veg", "breakfast", 295, 11.0, 38.0, 10.5, 180),
    ("Chicken Keema Paratha", "non_veg", "breakfast", 310, 18.0, 35.0, 11.0, 180),
    # LUNCH - VEG
    ("Dal Tadka", "veg", "lunch", 90, 5.5, 14.0, 2.0, 200),
    ("Dal Makhani", "veg", "lunch", 120, 7.0, 16.0, 4.0, 200),
    ("Rajma Masala", "veg", "lunch", 140, 9.0, 25.0, 0.5, 200),
    ("Chole Masala", "veg", "lunch", 165, 9.0, 28.0, 2.5, 200),
    ("Paneer Butter Masala", "veg", "lunch", 240, 11.5, 12.0, 17.0, 200),
    ("Palak Paneer", "veg", "lunch", 185, 9.5, 7.0, 14.0, 200),
    ("Mix Veg Sabzi", "veg", "lunch", 95, 3.5, 14.0, 3.5, 200),
    ("Aloo Sabzi", "veg", "lunch", 100, 2.5, 20.0, 2.5, 150),
    ("Plain Rice", "veg", "lunch", 130, 2.7, 28.0, 0.3, 200),
    ("Brown Rice", "veg", "lunch", 111, 2.6, 23.0, 0.9, 200),
    ("Jeera Rice", "veg", "lunch", 140, 2.8, 29.0, 2.5, 200),
    ("Chapati / Roti (3)", "veg", "lunch", 300, 9.0, 57.0, 5.0, 100),
    ("Sambar", "veg", "lunch", 50, 2.5, 8.0, 1.2, 200),
    ("Curd / Yogurt", "veg", "lunch", 61, 3.5, 4.7, 3.3, 150),
    ("Bhindi Masala", "veg", "lunch", 80, 2.0, 8.0, 4.5, 150),
    ("Baingan Bharta", "veg", "lunch", 70, 2.0, 9.0, 2.5, 150),
    ("Khichdi", "veg", "lunch", 105, 5.0, 20.0, 1.5, 250),
    ("Matar Paneer", "veg", "lunch", 190, 10.0, 14.0, 11.0, 200),
    ("Lauki Sabzi", "veg", "lunch", 50, 1.5, 8.0, 1.5, 150),
    # LUNCH - NON VEG
    ("Chicken Curry", "non_veg", "lunch", 150, 15.0, 5.0, 8.0, 200),
    ("Tandoori Chicken", "non_veg", "lunch", 175, 25.0, 4.0, 7.0, 200),
    ("Grilled Chicken", "non_veg", "lunch", 165, 28.0, 0.0, 5.5, 200),
    ("Fish Curry", "non_veg", "lunch", 130, 17.0, 5.0, 5.0, 200),
    ("Egg Curry", "non_veg", "lunch", 155, 12.0, 6.0, 9.0, 200),
    ("Mutton Curry", "non_veg", "lunch", 185, 17.0, 4.0, 11.0, 200),
    ("Prawn Masala", "non_veg", "lunch", 120, 16.0, 5.0, 5.0, 200),
    ("Chicken Biryani", "non_veg", "lunch", 170, 13.0, 22.0, 4.0, 250),
    ("Egg Bhurji", "non_veg", "lunch", 155, 10.5, 3.5, 11.0, 150),
    # DINNER - VEG
    ("Moong Dal Soup", "veg", "dinner", 55, 4.0, 9.0, 0.5, 250),
    ("Vegetable Soup", "veg", "dinner", 45, 2.0, 8.0, 0.5, 250),
    ("Dalia (Broken Wheat)", "veg", "dinner", 100, 4.5, 20.0, 0.5, 200),
    ("Paneer Bhurji", "veg", "dinner", 265, 14.0, 6.0, 21.0, 150),
    ("Dal Tadka", "veg", "dinner", 90, 5.5, 14.0, 2.0, 200),
    ("Chapati / Roti (2)", "veg", "dinner", 240, 6.5, 45.0, 4.0, 80),
    ("Palak Sabzi", "veg", "dinner", 55, 3.0, 7.0, 2.0, 150),
    ("Khichdi", "veg", "dinner", 105, 5.0, 20.0, 1.5, 250),
    # DINNER - NON VEG
    ("Grilled Fish", "non_veg", "dinner", 150, 20.0, 2.0, 7.0, 200),
    ("Chicken Soup", "non_veg", "dinner", 60, 8.0, 4.0, 1.5, 250),
    ("Egg Curry", "non_veg", "dinner", 155, 12.0, 6.0, 9.0, 200),
    ("Grilled Chicken", "non_veg", "dinner", 165, 28.0, 0.0, 5.5, 200),
    # SNACKS - VEG
    ("Roasted Chana", "veg", "snack", 375, 20.0, 60.0, 5.0, 30),
    ("Makhana (Fox Nuts)", "veg", "snack", 347, 9.7, 77.0, 0.1, 30),
    ("Mixed Fruit Bowl", "veg", "snack", 60, 0.8, 15.0, 0.2, 200),
    ("Coconut Water", "veg", "snack", 19, 0.7, 3.7, 0.2, 300),
    ("Buttermilk / Chaas", "veg", "snack", 40, 3.0, 5.0, 1.0, 250),
    ("Almonds (handful)", "veg", "snack", 579, 21.0, 22.0, 50.0, 30),
    ("Walnuts", "veg", "snack", 654, 15.0, 14.0, 65.0, 30),
    ("Greek Yogurt", "veg", "snack", 97, 9.0, 6.0, 5.0, 150),
    ("Banana", "veg", "snack", 89, 1.1, 23.0, 0.3, 120),
    ("Apple", "veg", "snack", 52, 0.3, 14.0, 0.2, 150),
    ("Dates (3-4)", "veg", "snack", 282, 2.5, 75.0, 0.4, 50),
    ("Sprouts Salad", "veg", "snack", 85, 6.5, 14.0, 0.5, 150),
    ("Peanuts (roasted)", "veg", "snack", 567, 25.0, 16.0, 49.0, 30),
    # SNACKS - NON VEG
    ("Boiled Eggs (2)", "non_veg", "snack", 155, 13.0, 1.0, 11.0, 100),
    ("Chicken Sandwich", "non_veg", "snack", 220, 18.0, 22.0, 7.0, 150),
    ("Tuna Salad", "non_veg", "snack", 130, 20.0, 5.0, 4.0, 150),
]

def seed_food_database():
    with get_db() as db:
        count = db.execute("SELECT COUNT(*) as cnt FROM food_items").fetchone()["cnt"]
        if count > 0:
            return
        db.executemany(
            "INSERT INTO food_items (name,category,meal_type,calories_per_100g,protein_per_100g,carbs_per_100g,fat_per_100g,default_serving_g) VALUES (?,?,?,?,?,?,?,?)",
            FOOD_SEED
        )

init_db()


# ── Auth helpers ────────────────────────────────────────────────────────────

def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def current_user():
    if "user_id" not in session:
        return None
    with get_db() as db:
        return db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()


# ── Business logic helpers ──────────────────────────────────────────────────

def get_week_start(d=None):
    if d is None:
        d = date_type.today()
    return d - timedelta(days=d.weekday())

def calculate_targets(profile):
    if not profile or not profile["weight_kg"] or not profile["height_cm"] or not profile["age"]:
        return {"calories": 2000, "protein_g": 120.0, "carbs_g": 225.0, "fat_g": 67.0}
    bmr = 10 * profile["weight_kg"] + 6.25 * profile["height_cm"] - 5 * profile["age"] + 5
    tdee = bmr * 1.55
    goal = profile["goal"] or ""
    if goal == "Weight Loss":
        calories = tdee - 500
    elif goal == "Muscle Gain":
        calories = tdee + 300
    elif goal == "Diabetes Management":
        calories = tdee - 300
    elif goal == "Heart Health":
        calories = tdee - 200
    else:
        calories = tdee
    calories = max(calories, 1200)
    protein_g = round(profile["weight_kg"] * 2, 1)
    fat_g = round(calories * 0.25 / 9, 1)
    carbs_g = round((calories - protein_g * 4 - fat_g * 9) / 4, 1)
    return {"calories": int(calories), "protein_g": protein_g, "carbs_g": max(carbs_g, 0.0), "fat_g": fat_g}

def ensure_today_meal_logs(customer_user_id):
    today = date_type.today()
    today_str = today.isoformat()
    day_of_week = today.weekday()
    with get_db() as db:
        cp = db.execute("SELECT id FROM customer_profiles WHERE user_id=?", (customer_user_id,)).fetchone()
        if not cp:
            return []
        plan = db.execute(
            "SELECT * FROM meal_plans WHERE customer_id=? AND is_active=1 ORDER BY week_start_date DESC LIMIT 1",
            (cp["id"],)
        ).fetchone()
        if not plan:
            return []
        items = db.execute(
            "SELECT id FROM meal_plan_items WHERE meal_plan_id=? AND day_of_week=?",
            (plan["id"], day_of_week)
        ).fetchall()
        for item in items:
            existing = db.execute(
                "SELECT id FROM meal_logs WHERE meal_plan_item_id=? AND log_date=? AND customer_user_id=?",
                (item["id"], today_str, customer_user_id)
            ).fetchone()
            if not existing:
                db.execute(
                    "INSERT INTO meal_logs (meal_plan_item_id,customer_user_id,log_date,status) VALUES (?,?,?,'pending')",
                    (item["id"], customer_user_id, today_str)
                )
        logs = db.execute("""
            SELECT ml.id, ml.status, ml.logged_at, mpi.meal_type, mpi.quantity_g,
                   fi.name as food_name, fi.category,
                   fi.calories_per_100g, fi.protein_per_100g, fi.carbs_per_100g, fi.fat_per_100g,
                   mf.rating as feedback_rating, mf.comment as feedback_comment
            FROM meal_logs ml
            JOIN meal_plan_items mpi ON mpi.id=ml.meal_plan_item_id
            JOIN food_items fi ON fi.id=mpi.food_item_id
            LEFT JOIN meal_feedback mf ON mf.meal_log_id=ml.id AND mf.customer_user_id=?
            WHERE ml.customer_user_id=? AND ml.log_date=?
            ORDER BY CASE mpi.meal_type WHEN 'breakfast' THEN 1 WHEN 'lunch' THEN 2 WHEN 'snack' THEN 3 WHEN 'dinner' THEN 4 END, fi.name
        """, (customer_user_id, customer_user_id, today_str)).fetchall()
        return logs

def check_and_create_alerts(customer_user_id):
    today = date_type.today()
    with get_db() as db:
        recent = db.execute("""
            SELECT status FROM meal_logs
            WHERE customer_user_id=? AND log_date>=? AND status!='pending'
            ORDER BY log_date DESC, id DESC LIMIT 6
        """, (customer_user_id, (today - timedelta(days=3)).isoformat())).fetchall()
        if len(recent) >= 3 and sum(1 for r in recent[:3] if r["status"] == "skipped") >= 3:
            exists = db.execute(
                "SELECT id FROM alerts WHERE customer_user_id=? AND alert_type='meal_skip' AND date(created_at)=?",
                (customer_user_id, today.isoformat())
            ).fetchone()
            if not exists:
                db.execute(
                    "INSERT INTO alerts (customer_user_id,alert_type,message) VALUES (?,'meal_skip',?)",
                    (customer_user_id, "You have skipped 3 or more meals recently. Consistent eating is key to reaching your goal!")
                )
        cp = db.execute("SELECT goal, weight_kg FROM customer_profiles WHERE user_id=?", (customer_user_id,)).fetchone()
        if cp and cp["goal"] == "Weight Loss":
            wk_ago = db.execute(
                "SELECT weight_kg FROM weight_logs WHERE customer_user_id=? AND log_date<=? ORDER BY log_date DESC LIMIT 1",
                (customer_user_id, (today - timedelta(days=7)).isoformat())
            ).fetchone()
            latest = db.execute(
                "SELECT weight_kg FROM weight_logs WHERE customer_user_id=? ORDER BY log_date DESC LIMIT 1",
                (customer_user_id,)
            ).fetchone()
            if wk_ago and latest and abs(wk_ago["weight_kg"] - latest["weight_kg"]) < 0.3:
                exists = db.execute(
                    "SELECT id FROM alerts WHERE customer_user_id=? AND alert_type='weight_stagnant' AND date(created_at)>=?",
                    (customer_user_id, (today - timedelta(days=3)).isoformat())
                ).fetchone()
                if not exists:
                    db.execute(
                        "INSERT INTO alerts (customer_user_id,alert_type,message) VALUES (?,'weight_stagnant',?)",
                        (customer_user_id, "Your weight has not changed significantly in the past week. Consider reviewing your meal plan with your nutritionist.")
                    )

def get_unread_alerts(customer_user_id):
    with get_db() as db:
        return db.execute(
            "SELECT * FROM alerts WHERE customer_user_id=? AND is_read=0 ORDER BY created_at DESC",
            (customer_user_id,)
        ).fetchall()

def get_unread_chat_count(user_id):
    with get_db() as db:
        row = db.execute(
            "SELECT COUNT(*) as cnt FROM chat_messages WHERE receiver_user_id=? AND is_read=0",
            (user_id,)
        ).fetchone()
        return row["cnt"] if row else 0


# ── Landing ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", user=current_user())


# ── Auth ────────────────────────────────────────────────────────────────────

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        if not email or not password:
            flash("Email and password are required.", "danger")
            return render_template("register.html")
        with get_db() as db:
            existing = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
            if existing:
                flash("Email already registered. Please log in.", "warning")
                return redirect(url_for("login"))
            db.execute("INSERT INTO users (email,password) VALUES (?,?)", (email, generate_password_hash(password)))
            user_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        session["user_id"] = user_id
        flash("Account created! Please choose your role.", "success")
        return redirect(url_for("role_select"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        with get_db() as db:
            user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not user or not check_password_hash(user["password"], password):
            flash("Invalid email or password.", "danger")
            return render_template("login.html")
        session["user_id"] = user["id"]
        if not user["role"]:
            return redirect(url_for("role_select"))
        return redirect(url_for("customer_dashboard" if user["role"] == "customer" else "nutritionist_dashboard"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("index"))


# ── Role selection ────────────────────────────────────────────────────────────

@app.route("/role", methods=["GET", "POST"])
@login_required
def role_select():
    if request.method == "POST":
        role = request.form.get("role")
        if role not in ("customer", "nutritionist"):
            flash("Please select a valid role.", "danger")
            return render_template("role_select.html")
        with get_db() as db:
            db.execute("UPDATE users SET role=? WHERE id=?", (role, session["user_id"]))
        return redirect(url_for("customer_profile" if role == "customer" else "nutritionist_profile"))
    return render_template("role_select.html")


# ── Customer profile ──────────────────────────────────────────────────────────

def get_available_nutritionists():
    with get_db() as db:
        return db.execute("""
            SELECT np.*,
                   COUNT(CASE WHEN cp.status!='completed' THEN 1 END) AS current_clients
            FROM nutritionist_profiles np
            LEFT JOIN customer_profiles cp ON cp.nutritionist_id=np.id AND cp.status!='completed'
            GROUP BY np.id
            HAVING COUNT(CASE WHEN cp.status!='completed' THEN 1 END) < np.max_clients
            ORDER BY np.full_name ASC
        """).fetchall()

@app.route("/customer/profile", methods=["GET", "POST"])
@login_required
def customer_profile():
    user = current_user()
    if user["role"] != "customer":
        flash("Access denied.", "danger")
        return redirect(url_for("index"))
    with get_db() as db:
        profile = db.execute("SELECT * FROM customer_profiles WHERE user_id=?", (user["id"],)).fetchone()
    if request.method == "POST":
        full_name = request.form["full_name"].strip()
        age = request.form.get("age", type=int)
        weight_kg = request.form.get("weight_kg", type=float)
        height_cm = request.form.get("height_cm", type=float)
        goal = request.form.get("goal", "")
        plan_type = request.form.get("plan_type", "")
        nutritionist_id = request.form.get("nutritionist_id", type=int)
        if not nutritionist_id:
            flash("Please select a nutritionist to continue.", "danger")
            return render_template("customer/profile.html", user=user, profile=profile, nutritionists=get_available_nutritionists())
        with get_db() as db:
            valid = db.execute("SELECT id FROM nutritionist_profiles WHERE id=?", (nutritionist_id,)).fetchone()
            if not valid:
                flash("Invalid nutritionist selected.", "danger")
                return render_template("customer/profile.html", user=user, profile=profile, nutritionists=get_available_nutritionists())
            if profile:
                db.execute("""
                    UPDATE customer_profiles SET full_name=?,age=?,weight_kg=?,height_cm=?,goal=?,plan_type=?,nutritionist_id=?
                    WHERE user_id=?
                """, (full_name, age, weight_kg, height_cm, goal, plan_type, nutritionist_id, user["id"]))
            else:
                db.execute("""
                    INSERT INTO customer_profiles (user_id,full_name,age,weight_kg,height_cm,goal,plan_type,nutritionist_id)
                    VALUES (?,?,?,?,?,?,?,?)
                """, (user["id"], full_name, age, weight_kg, height_cm, goal, plan_type, nutritionist_id))
        flash("Profile saved!", "success")
        return redirect(url_for("customer_dashboard"))
    return render_template("customer/profile.html", user=user, profile=profile, nutritionists=get_available_nutritionists())


# ── Customer dashboard ────────────────────────────────────────────────────────

@app.route("/customer/dashboard")
@login_required
def customer_dashboard():
    user = current_user()
    if user["role"] != "customer":
        return redirect(url_for("index"))
    check_and_create_alerts(user["id"])
    with get_db() as db:
        profile = db.execute("SELECT * FROM customer_profiles WHERE user_id=?", (user["id"],)).fetchone()
        nutritionist = None
        if profile and profile["nutritionist_id"]:
            nutritionist = db.execute("SELECT * FROM nutritionist_profiles WHERE id=?", (profile["nutritionist_id"],)).fetchone()
        latest_weight = db.execute(
            "SELECT weight_kg, log_date FROM weight_logs WHERE customer_user_id=? ORDER BY log_date DESC LIMIT 1",
            (user["id"],)
        ).fetchone()
    if not profile:
        return redirect(url_for("customer_profile"))
    today_logs = ensure_today_meal_logs(user["id"])
    eaten = sum(1 for l in today_logs if l["status"] == "eaten")
    alerts = get_unread_alerts(user["id"])
    unread_chat = get_unread_chat_count(user["id"])
    return render_template("customer/dashboard.html",
        user=user, profile=profile, nutritionist=nutritionist,
        today_logs=today_logs, eaten=eaten, total=len(today_logs),
        alerts=alerts, latest_weight=latest_weight, unread_chat=unread_chat)


# ── Customer: today's meals ───────────────────────────────────────────────────

@app.route("/customer/today")
@login_required
def customer_today():
    user = current_user()
    if user["role"] != "customer":
        return redirect(url_for("index"))
    logs = ensure_today_meal_logs(user["id"])
    grouped = {"breakfast": [], "lunch": [], "snack": [], "dinner": []}
    for log in logs:
        grouped[log["meal_type"]].append(log)
    today_name = DAYS[date_type.today().weekday()]
    return render_template("customer/today_meals.html", user=user, grouped=grouped, today_name=today_name)

@app.route("/customer/meal/<int:log_id>/status", methods=["POST"])
@login_required
def customer_meal_status(log_id):
    user = current_user()
    status = request.form.get("status")
    if status not in ("eaten", "skipped", "pending"):
        flash("Invalid status.", "danger")
        return redirect(url_for("customer_today"))
    with get_db() as db:
        db.execute(
            "UPDATE meal_logs SET status=?,logged_at=CURRENT_TIMESTAMP WHERE id=? AND customer_user_id=?",
            (status, log_id, user["id"])
        )
    return redirect(url_for("customer_today"))

@app.route("/customer/meal/<int:log_id>/feedback", methods=["POST"])
@login_required
def customer_meal_feedback(log_id):
    user = current_user()
    rating = request.form.get("rating", type=int)
    comment = request.form.get("comment", "").strip()
    if not rating or rating < 1 or rating > 5:
        flash("Please select a valid rating.", "danger")
        return redirect(url_for("customer_today"))
    with get_db() as db:
        existing = db.execute(
            "SELECT id FROM meal_feedback WHERE meal_log_id=? AND customer_user_id=?",
            (log_id, user["id"])
        ).fetchone()
        if existing:
            db.execute("UPDATE meal_feedback SET rating=?,comment=? WHERE id=?", (rating, comment, existing["id"]))
        else:
            db.execute(
                "INSERT INTO meal_feedback (meal_log_id,customer_user_id,rating,comment) VALUES (?,?,?,?)",
                (log_id, user["id"], rating, comment)
            )
    flash("Feedback saved!", "success")
    return redirect(url_for("customer_today"))


# ── Customer: progress & weight ───────────────────────────────────────────────

@app.route("/customer/progress", methods=["GET", "POST"])
@login_required
def customer_progress():
    user = current_user()
    if user["role"] != "customer":
        return redirect(url_for("index"))
    if request.method == "POST":
        weight_kg = request.form.get("weight_kg", type=float)
        notes = request.form.get("notes", "").strip()
        log_date = request.form.get("log_date") or date_type.today().isoformat()
        if weight_kg:
            with get_db() as db:
                existing = db.execute(
                    "SELECT id FROM weight_logs WHERE customer_user_id=? AND log_date=?",
                    (user["id"], log_date)
                ).fetchone()
                if existing:
                    db.execute("UPDATE weight_logs SET weight_kg=?,notes=? WHERE id=?",
                               (weight_kg, notes, existing["id"]))
                else:
                    db.execute(
                        "INSERT INTO weight_logs (customer_user_id,weight_kg,log_date,notes) VALUES (?,?,?,?)",
                        (user["id"], weight_kg, log_date, notes)
                    )
            flash("Weight logged!", "success")
        return redirect(url_for("customer_progress"))
    with get_db() as db:
        profile = db.execute("SELECT * FROM customer_profiles WHERE user_id=?", (user["id"],)).fetchone()
        weights = db.execute(
            "SELECT weight_kg, log_date, notes FROM weight_logs WHERE customer_user_id=? ORDER BY log_date ASC",
            (user["id"],)
        ).fetchall()
        four_weeks_ago = (date_type.today() - timedelta(days=28)).isoformat()
        meal_stats = db.execute("""
            SELECT log_date,
                   SUM(CASE WHEN status='eaten' THEN 1 ELSE 0 END) as eaten,
                   COUNT(*) as total
            FROM meal_logs WHERE customer_user_id=? AND log_date>=?
            GROUP BY log_date ORDER BY log_date ASC
        """, (user["id"], four_weeks_ago)).fetchall()
    weights_list = [dict(w) for w in weights]
    weights_table = []
    last7 = weights_list[-7:]
    for i, w in enumerate(reversed(last7)):
        orig_idx = len(last7) - 1 - i
        change = None
        if orig_idx > 0:
            change = round(float(w["weight_kg"]) - float(last7[orig_idx - 1]["weight_kg"]), 1)
        weights_table.append({"log_date": w["log_date"], "weight_kg": w["weight_kg"], "change": change})
    return render_template("customer/progress.html",
        user=user, profile=profile,
        weights=weights_list, weights_table=weights_table,
        meal_stats=meal_stats,
        today=date_type.today().isoformat())


# ── Customer: chat ────────────────────────────────────────────────────────────

@app.route("/customer/chat")
@login_required
def customer_chat():
    user = current_user()
    if user["role"] != "customer":
        return redirect(url_for("index"))
    with get_db() as db:
        cp = db.execute("SELECT * FROM customer_profiles WHERE user_id=?", (user["id"],)).fetchone()
        if not cp or not cp["nutritionist_id"]:
            flash("No nutritionist assigned yet.", "warning")
            return redirect(url_for("customer_dashboard"))
        np = db.execute("SELECT * FROM nutritionist_profiles WHERE id=?", (cp["nutritionist_id"],)).fetchone()
        nut_user_id = np["user_id"]
        db.execute(
            "UPDATE chat_messages SET is_read=1 WHERE receiver_user_id=? AND sender_user_id=?",
            (user["id"], nut_user_id)
        )
        messages = db.execute("""
            SELECT cm.id, cm.message, cm.sent_at, cm.sender_user_id, u.role as sender_role
            FROM chat_messages cm JOIN users u ON u.id=cm.sender_user_id
            WHERE (cm.sender_user_id=? AND cm.receiver_user_id=?)
               OR (cm.sender_user_id=? AND cm.receiver_user_id=?)
            ORDER BY cm.sent_at ASC
        """, (user["id"], nut_user_id, nut_user_id, user["id"])).fetchall()
    return render_template("customer/chat.html",
        user=user, partner=np, messages=messages, partner_user_id=nut_user_id)

@app.route("/customer/chat/send", methods=["POST"])
@login_required
def customer_chat_send():
    user = current_user()
    message = request.form.get("message", "").strip()
    receiver_id = request.form.get("receiver_id", type=int)
    if message and receiver_id:
        with get_db() as db:
            db.execute(
                "INSERT INTO chat_messages (sender_user_id,receiver_user_id,message) VALUES (?,?,?)",
                (user["id"], receiver_id, message)
            )
    return redirect(url_for("customer_chat"))

@app.route("/customer/alerts/read", methods=["POST"])
@login_required
def customer_alerts_read():
    user = current_user()
    with get_db() as db:
        db.execute("UPDATE alerts SET is_read=1 WHERE customer_user_id=?", (user["id"],))
    return redirect(request.referrer or url_for("customer_dashboard"))


# ── Nutritionist profile ──────────────────────────────────────────────────────

@app.route("/nutritionist/profile", methods=["GET", "POST"])
@login_required
def nutritionist_profile():
    user = current_user()
    if user["role"] != "nutritionist":
        flash("Access denied.", "danger")
        return redirect(url_for("index"))
    with get_db() as db:
        profile = db.execute("SELECT * FROM nutritionist_profiles WHERE user_id=?", (user["id"],)).fetchone()
    if request.method == "POST":
        full_name = request.form["full_name"].strip()
        specialization = request.form.get("specialization", "")
        experience_years = request.form.get("experience_years", type=int)
        max_clients = request.form.get("max_clients", 10, type=int)
        bio = request.form.get("bio", "")
        with get_db() as db:
            if profile:
                db.execute("""
                    UPDATE nutritionist_profiles SET full_name=?,specialization=?,experience_years=?,max_clients=?,bio=?
                    WHERE user_id=?
                """, (full_name, specialization, experience_years, max_clients, bio, user["id"]))
            else:
                db.execute("""
                    INSERT INTO nutritionist_profiles (user_id,full_name,specialization,experience_years,max_clients,bio)
                    VALUES (?,?,?,?,?,?)
                """, (user["id"], full_name, specialization, experience_years, max_clients, bio))
        flash("Profile saved!", "success")
        return redirect(url_for("nutritionist_dashboard"))
    return render_template("nutritionist/profile.html", user=user, profile=profile)


# ── Nutritionist dashboard ────────────────────────────────────────────────────

@app.route("/nutritionist/dashboard")
@login_required
def nutritionist_dashboard():
    user = current_user()
    if user["role"] != "nutritionist":
        return redirect(url_for("index"))
    with get_db() as db:
        profile = db.execute("SELECT * FROM nutritionist_profiles WHERE user_id=?", (user["id"],)).fetchone()
        if not profile:
            return redirect(url_for("nutritionist_profile"))
        clients = db.execute("""
            SELECT cp.*, u.email, u.id as user_id,
                   (SELECT COUNT(*) FROM meal_plans mp WHERE mp.customer_id=cp.id AND mp.is_active=1) as has_plan,
                   (SELECT COUNT(*) FROM chat_messages cm WHERE cm.sender_user_id=u.id AND cm.receiver_user_id=? AND cm.is_read=0) as unread_msgs
            FROM customer_profiles cp
            JOIN users u ON u.id=cp.user_id
            WHERE cp.nutritionist_id=?
            ORDER BY cp.id DESC
        """, (user["id"], profile["id"])).fetchall()
    unread_chat = get_unread_chat_count(user["id"])
    return render_template("nutritionist/dashboard.html",
        user=user, profile=profile, clients=clients, unread_chat=unread_chat)


# ── Nutritionist: client detail view ─────────────────────────────────────────

@app.route("/nutritionist/customer/<int:customer_id>")
@login_required
def nutritionist_customer_view(customer_id):
    user = current_user()
    if user["role"] != "nutritionist":
        return redirect(url_for("index"))
    with get_db() as db:
        np = db.execute("SELECT id FROM nutritionist_profiles WHERE user_id=?", (user["id"],)).fetchone()
        client = db.execute("""
            SELECT cp.*, u.email, u.id as user_id FROM customer_profiles cp
            JOIN users u ON u.id=cp.user_id
            WHERE cp.id=? AND cp.nutritionist_id=?
        """, (customer_id, np["id"])).fetchone()
        if not client:
            flash("Client not found.", "danger")
            return redirect(url_for("nutritionist_dashboard"))
        plans = db.execute(
            "SELECT * FROM meal_plans WHERE customer_id=? ORDER BY week_start_date DESC",
            (customer_id,)
        ).fetchall()
        weights = db.execute(
            "SELECT weight_kg, log_date FROM weight_logs WHERE customer_user_id=? ORDER BY log_date ASC",
            (client["user_id"],)
        ).fetchall()
        week_ago = (date_type.today() - timedelta(days=6)).isoformat()
        meal_stats = db.execute("""
            SELECT log_date,
                   SUM(CASE WHEN status='eaten' THEN 1 ELSE 0 END) as eaten,
                   COUNT(*) as total
            FROM meal_logs WHERE customer_user_id=? AND log_date>=?
            GROUP BY log_date ORDER BY log_date ASC
        """, (client["user_id"], week_ago)).fetchall()
        # Recent meal feedback from this customer
        recent_feedback = db.execute("""
            SELECT mf.rating, mf.comment, mf.created_at, fi.name as food_name
            FROM meal_feedback mf
            JOIN meal_logs ml ON ml.id=mf.meal_log_id
            JOIN meal_plan_items mpi ON mpi.id=ml.meal_plan_item_id
            JOIN food_items fi ON fi.id=mpi.food_item_id
            WHERE mf.customer_user_id=?
            ORDER BY mf.created_at DESC LIMIT 10
        """, (client["user_id"],)).fetchall()
    targets = calculate_targets(client)
    return render_template("nutritionist/customer_view.html",
        user=user, client=client, plans=plans, weights=weights,
        meal_stats=meal_stats, recent_feedback=recent_feedback, targets=targets)


# ── Nutritionist: create / edit meal plan ────────────────────────────────────

@app.route("/nutritionist/customer/<int:customer_id>/plan", methods=["GET", "POST"])
@login_required
def nutritionist_create_plan(customer_id):
    user = current_user()
    if user["role"] != "nutritionist":
        return redirect(url_for("index"))
    with get_db() as db:
        np = db.execute("SELECT id FROM nutritionist_profiles WHERE user_id=?", (user["id"],)).fetchone()
        client = db.execute("""
            SELECT cp.*, u.email FROM customer_profiles cp JOIN users u ON u.id=cp.user_id
            WHERE cp.id=? AND cp.nutritionist_id=?
        """, (customer_id, np["id"])).fetchone()
        if not client:
            flash("Client not found.", "danger")
            return redirect(url_for("nutritionist_dashboard"))
        foods = db.execute("SELECT * FROM food_items ORDER BY meal_type,category,name").fetchall()
        foods_json = json.dumps([dict(f) for f in foods])

    if request.method == "POST":
        week_start = request.form.get("week_start")
        daily_calories = request.form.get("daily_calories", type=int)
        daily_protein = request.form.get("daily_protein_g", type=float)
        daily_carbs = request.form.get("daily_carbs_g", type=float)
        daily_fat = request.form.get("daily_fat_g", type=float)
        notes = request.form.get("notes", "").strip()
        items_json = request.form.get("items_json", "[]")
        try:
            items = json.loads(items_json)
        except Exception:
            items = []
        if not week_start:
            flash("Please select a week start date.", "danger")
        elif not items:
            flash("Please add at least one meal item to the plan.", "danger")
        else:
            with get_db() as db:
                db.execute("UPDATE meal_plans SET is_active=0 WHERE customer_id=?", (customer_id,))
                db.execute("""
                    INSERT INTO meal_plans (customer_id,nutritionist_id,week_start_date,daily_calories,daily_protein_g,daily_carbs_g,daily_fat_g,notes,is_active)
                    VALUES (?,?,?,?,?,?,?,?,1)
                """, (customer_id, np["id"], week_start, daily_calories, daily_protein, daily_carbs, daily_fat, notes))
                plan_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
                for item in items:
                    db.execute("""
                        INSERT INTO meal_plan_items (meal_plan_id,day_of_week,meal_type,food_item_id,quantity_g)
                        VALUES (?,?,?,?,?)
                    """, (plan_id, item["day"], item["meal_type"], item["food_item_id"], item["quantity_g"]))
            flash("Meal plan created successfully!", "success")
            return redirect(url_for("nutritionist_customer_view", customer_id=customer_id))

    with get_db() as db:
        active_plan = db.execute(
            "SELECT * FROM meal_plans WHERE customer_id=? AND is_active=1 ORDER BY week_start_date DESC LIMIT 1",
            (customer_id,)
        ).fetchone()
        existing_items = []
        if active_plan:
            existing_items = db.execute("""
                SELECT mpi.*, fi.name as food_name,
                       fi.calories_per_100g, fi.protein_per_100g, fi.carbs_per_100g, fi.fat_per_100g
                FROM meal_plan_items mpi JOIN food_items fi ON fi.id=mpi.food_item_id
                WHERE mpi.meal_plan_id=?
                ORDER BY mpi.day_of_week, CASE mpi.meal_type WHEN 'breakfast' THEN 1 WHEN 'lunch' THEN 2 WHEN 'snack' THEN 3 WHEN 'dinner' THEN 4 END
            """, (active_plan["id"],)).fetchall()

    targets = calculate_targets(client)
    return render_template("nutritionist/create_plan.html",
        user=user, client=client, foods_json=foods_json,
        days=DAYS, meal_types=MEAL_TYPES,
        active_plan=active_plan,
        existing_items=json.dumps([dict(i) for i in existing_items]),
        targets=targets,
        week_start_default=get_week_start().isoformat())


# ── Nutritionist: chat ────────────────────────────────────────────────────────

@app.route("/nutritionist/chat/<int:customer_user_id>")
@login_required
def nutritionist_chat(customer_user_id):
    user = current_user()
    if user["role"] != "nutritionist":
        return redirect(url_for("index"))
    with get_db() as db:
        partner_cp = db.execute("SELECT * FROM customer_profiles WHERE user_id=?", (customer_user_id,)).fetchone()
        db.execute(
            "UPDATE chat_messages SET is_read=1 WHERE receiver_user_id=? AND sender_user_id=?",
            (user["id"], customer_user_id)
        )
        messages = db.execute("""
            SELECT cm.id, cm.message, cm.sent_at, cm.sender_user_id, u.role as sender_role
            FROM chat_messages cm JOIN users u ON u.id=cm.sender_user_id
            WHERE (cm.sender_user_id=? AND cm.receiver_user_id=?)
               OR (cm.sender_user_id=? AND cm.receiver_user_id=?)
            ORDER BY cm.sent_at ASC
        """, (user["id"], customer_user_id, customer_user_id, user["id"])).fetchall()
    return render_template("nutritionist/chat.html",
        user=user, partner_cp=partner_cp, messages=messages, partner_user_id=customer_user_id)

@app.route("/nutritionist/chat/<int:customer_user_id>/send", methods=["POST"])
@login_required
def nutritionist_chat_send(customer_user_id):
    user = current_user()
    message = request.form.get("message", "").strip()
    if message:
        with get_db() as db:
            db.execute(
                "INSERT INTO chat_messages (sender_user_id,receiver_user_id,message) VALUES (?,?,?)",
                (user["id"], customer_user_id, message)
            )
    return redirect(url_for("nutritionist_chat", customer_user_id=customer_user_id))


# ── Shared: chat poll API ─────────────────────────────────────────────────────

@app.route("/api/chat/messages")
@login_required
def api_chat_messages():
    user = current_user()
    partner_id = request.args.get("partner_id", type=int)
    after_id = request.args.get("after_id", 0, type=int)
    if not partner_id:
        return jsonify([])
    with get_db() as db:
        db.execute(
            "UPDATE chat_messages SET is_read=1 WHERE receiver_user_id=? AND sender_user_id=?",
            (user["id"], partner_id)
        )
        rows = db.execute("""
            SELECT cm.id, cm.message, cm.sent_at, cm.sender_user_id
            FROM chat_messages cm
            WHERE ((cm.sender_user_id=? AND cm.receiver_user_id=?)
                OR (cm.sender_user_id=? AND cm.receiver_user_id=?))
              AND cm.id > ?
            ORDER BY cm.sent_at ASC
        """, (user["id"], partner_id, partner_id, user["id"], after_id)).fetchall()
    return jsonify([dict(r) for r in rows])


# ── Nutritionist: client status ───────────────────────────────────────────────

@app.route("/nutritionist/client/<int:client_id>/status", methods=["POST"])
@login_required
def update_client_status(client_id):
    user = current_user()
    if user["role"] != "nutritionist":
        return redirect(url_for("index"))
    status = request.form.get("status")
    if status not in ("active", "on_hold", "completed"):
        flash("Invalid status.", "danger")
        return redirect(url_for("nutritionist_dashboard"))
    with get_db() as db:
        np = db.execute("SELECT id FROM nutritionist_profiles WHERE user_id=?", (user["id"],)).fetchone()
        if np:
            db.execute(
                "UPDATE customer_profiles SET status=? WHERE id=? AND nutritionist_id=?",
                (status, client_id, np["id"])
            )
    flash("Client status updated.", "success")
    return redirect(url_for("nutritionist_dashboard"))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8000)
