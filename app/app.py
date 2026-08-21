from flask import Flask, jsonify, request
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST
import mysql.connector
import os

app = Flask(__name__)

VERSION = os.environ.get("APP_VERSION", "v1.0.0")

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
        CREATE TABLE IF NOT EXISTS items (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()


@app.route("/")
def home():
    REQUEST_COUNT.labels(endpoint="/").inc()
    return f"Hello from Intermediate-project! Current version: {VERSION}\n"


@app.route("/health")
def health():
    REQUEST_COUNT.labels(endpoint="/health").inc()
    return {"status": "ok"}, 200


@app.route("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


@app.route("/items", methods=["GET"])
def get_items():
    REQUEST_COUNT.labels(endpoint="/items").inc()
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, name, created_at FROM items ORDER BY id DESC")
        items = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(items), 200
    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500


@app.route("/items", methods=["POST"])
def add_item():
    REQUEST_COUNT.labels(endpoint="/items").inc()
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    if not name:
        return jsonify({"error": "'name' field is required"}), 400
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO items (name) VALUES (%s)", (name,))
        conn.commit()
        new_id = cursor.lastrowid
        cursor.close()
        conn.close()
        return jsonify({"id": new_id, "name": name}), 201
    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500


if __name__ == "__main__":
    try:
        init_db()
    except Exception as e:
        print(f"Warning: could not initialize DB on startup: {e}")
    app.run(host="0.0.0.0", port=5000)
