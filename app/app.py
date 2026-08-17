from flask import Flask
import os

app = Flask(__name__)

VERSION = os.environ.get("APP_VERSION", "v1.0.0")

@app.route("/")
def home():
    return f"Hello from Intermediate-project! Current version: {VERSION}\n"

@app.route("/health")
def health():
    return {"status": "ok"}, 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

