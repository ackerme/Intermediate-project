from flask import Flask, jsonify, request
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
import jwt
import os
import datetime
from functools import wraps

app = Flask(__name__)

VERSION = os.environ.get("APP_VERSION", "v2.0.0")
JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production")

DB_CONFIG = {
    "host": os.environ.get("MYSQL_HOST", "mysql"),
    "user": os.environ.get("MYSQL_USER", "appuser"),
    "password": os.environ.get("MYSQL_PASSWORD", "apppass123"),
    "database": os.environ.get("MYSQL_DATABASE", "intermediate_db"),
}

REQUEST_COUNT = Counter(
    "app_requests_total", "Total number of requests", ["endpoint"]
)


def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INT AUTO_INCREMENT PRIMARY KEY,
            owner_id INT NOT NULL,
            name VARCHAR(255) NOT NULL,
            phone VARCHAR(50),
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE,
            INDEX idx_owner_phone (owner_id, phone)
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()


def token_required(f):
    """Decorator: מוודא שיש JWT תקין, ומזריק user_id לתוך הפונקציה."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401
        token = auth_header.split(" ", 1)[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            user_id = payload["user_id"]
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        return f(user_id, *args, **kwargs)
    return decorated


@app.route("/")
def home():
    REQUEST_COUNT.labels(endpoint="/").inc()
    return f"Intermediate-project CRM - version {VERSION}\n"


@app.route("/health")
def health():
    REQUEST_COUNT.labels(endpoint="/health").inc()
    return {"status": "ok"}, 200


@app.route("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


# ---------- Authentication ----------

@app.route("/auth/register", methods=["POST"])
def register():
    REQUEST_COUNT.labels(endpoint="/auth/register").inc()
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return jsonify({"error": "'username' and 'password' are required"}), 400
    if len(password) < 6:
        return jsonify({"error": "password must be at least 6 characters"}), 400

    password_hash = generate_password_hash(password)
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
            (username, password_hash),
        )
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": "user created"}), 201
    except mysql.connector.errors.IntegrityError:
        return jsonify({"error": "username already exists"}), 409
    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500


@app.route("/auth/login", methods=["POST"])
def login():
    REQUEST_COUNT.labels(endpoint="/auth/login").inc()
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return jsonify({"error": "'username' and 'password' are required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, password_hash FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "invalid username or password"}), 401

    token = jwt.encode(
        {
            "user_id": user["id"],
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24),
        },
        JWT_SECRET,
        algorithm="HS256",
    )
    return jsonify({"token": token}), 200


# ---------- Customers (CRM) ----------

@app.route("/customers", methods=["GET"])
@token_required
def list_customers(user_id):
    REQUEST_COUNT.labels(endpoint="/customers").inc()
    phone_query = request.args.get("phone")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    if phone_query:
        cursor.execute(
            "SELECT id, name, phone, notes, created_at, updated_at "
            "FROM customers WHERE owner_id = %s AND phone LIKE %s "
            "ORDER BY updated_at DESC",
            (user_id, f"%{phone_query}%"),
        )
    else:
        cursor.execute(
            "SELECT id, name, phone, notes, created_at, updated_at "
            "FROM customers WHERE owner_id = %s ORDER BY updated_at DESC",
            (user_id,),
        )
    customers = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(customers), 200


@app.route("/customers", methods=["POST"])
@token_required
def create_customer(user_id):
    REQUEST_COUNT.labels(endpoint="/customers").inc()
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    phone = data.get("phone", "")
    notes = data.get("notes", "")
    if not name:
        return jsonify({"error": "'name' is required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO customers (owner_id, name, phone, notes) VALUES (%s, %s, %s, %s)",
        (user_id, name, phone, notes),
    )
    conn.commit()
    new_id = cursor.lastrowid
    cursor.close()
    conn.close()
    return jsonify({"id": new_id, "name": name, "phone": phone, "notes": notes}), 201


@app.route("/customers/<int:customer_id>", methods=["PUT"])
@token_required
def update_customer(user_id, customer_id):
    """עדכון מלא של לקוח קיים - תמיד ניתן לערוך כל שדה, בכל עת."""
    REQUEST_COUNT.labels(endpoint="/customers/<id>").inc()
    data = request.get_json(silent=True) or {}

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT id FROM customers WHERE id = %s AND owner_id = %s",
        (customer_id, user_id),
    )
    if not cursor.fetchone():
        cursor.close()
        conn.close()
        return jsonify({"error": "customer not found"}), 404

    fields, values = [], []
    for field in ("name", "phone", "notes"):
        if field in data:
            fields.append(f"{field} = %s")
            values.append(data[field])
    if not fields:
        cursor.close()
        conn.close()
        return jsonify({"error": "no fields to update"}), 400

    values.extend([customer_id, user_id])
    cursor2 = conn.cursor()
    cursor2.execute(
        f"UPDATE customers SET {', '.join(fields)} WHERE id = %s AND owner_id = %s",
        tuple(values),
    )
    conn.commit()
    cursor.close()
    cursor2.close()
    conn.close()
    return jsonify({"message": "updated"}), 200


@app.route("/customers/<int:customer_id>", methods=["DELETE"])
@token_required
def delete_customer(user_id, customer_id):
    REQUEST_COUNT.labels(endpoint="/customers/<id>").inc()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM customers WHERE id = %s AND owner_id = %s",
        (customer_id, user_id),
    )
    conn.commit()
    deleted = cursor.rowcount
    cursor.close()
    conn.close()
    if deleted == 0:
        return jsonify({"error": "customer not found"}), 404
    return jsonify({"message": "deleted"}), 200


if __name__ == "__main__":
    try:
        init_db()
    except Exception as e:
        print(f"Warning: could not initialize DB on startup: {e}")
    app.run(host="0.0.0.0", port=5000)
