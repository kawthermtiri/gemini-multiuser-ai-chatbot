from flask import Flask, render_template, request, jsonify, redirect, session, url_for
from google import genai
from dotenv import load_dotenv
from werkzeug.security import check_password_hash, generate_password_hash
import sqlite3
import os
from datetime import datetime

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-this-secret-key")
DATABASE = os.path.join(os.path.dirname(__file__), "chat.db")

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

def get_db_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def init_database():
    connection = get_db_connection()
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL DEFAULT 'Nouvelle conversation',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            conversation_id INTEGER,
            role TEXT NOT NULL CHECK(role IN ('user', 'model')),
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)
    message_columns = [row["name"] for row in connection.execute("PRAGMA table_info(messages)").fetchall()]
    if "conversation_id" not in message_columns:
        connection.execute("ALTER TABLE messages ADD COLUMN conversation_id INTEGER")

    users = connection.execute("SELECT id FROM users").fetchall()
    for user in users:
        conversation = connection.execute(
            "SELECT id FROM conversations WHERE user_id = ? ORDER BY id LIMIT 1",
            (user["id"],),
        ).fetchone()
        if conversation is None:
            cursor = connection.execute(
                "INSERT INTO conversations (user_id) VALUES (?)", (user["id"],)
            )
            conversation_id = cursor.lastrowid
        else:
            conversation_id = conversation["id"]
        connection.execute(
            "UPDATE messages SET conversation_id = ? WHERE user_id = ? AND conversation_id IS NULL",
            (conversation_id, user["id"]),
        )
    connection.execute(
        "UPDATE conversations SET title = strftime('%d/%m/%Y %H:%M', created_at) "
        "WHERE title = 'Nouvelle conversation'"
    )
    connection.commit()
    connection.close()


def current_user():
    user_id = session.get("user_id")
    if user_id is None:
        return None

    connection = get_db_connection()
    user = connection.execute(
        "SELECT id, name, email FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    connection.close()
    return user


def create_conversation(user_id):
    connection = get_db_connection()
    cursor = connection.execute(
        "INSERT INTO conversations (user_id, title) VALUES (?, ?)",
        (user_id, datetime.now().strftime("%d/%m/%Y %H:%M")),
    )
    connection.commit()
    conversation_id = cursor.lastrowid
    connection.close()
    return conversation_id


def get_current_conversation(user_id):
    conversation_id = session.get("conversation_id")
    connection = get_db_connection()
    conversation = None
    if conversation_id is not None:
        conversation = connection.execute(
            "SELECT id FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        ).fetchone()
    connection.close()

    if conversation is None:
        conversation_id = create_conversation(user_id)
        session["conversation_id"] = conversation_id
    return conversation_id


init_database()


@app.route("/")
def home():
    user = current_user()
    if user is None:
        return redirect(url_for("login"))
    get_current_conversation(user["id"])
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            return render_template("register.html", error="Tous les champs sont obligatoires.")
        if len(password) < 6:
            return render_template("register.html", error="Le mot de passe doit contenir au moins 6 caractères.")

        connection = get_db_connection()
        try:
            cursor = connection.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, generate_password_hash(password)),
            )
            connection.commit()
        except sqlite3.IntegrityError:
            connection.close()
            return render_template("register.html", error="Cette adresse e-mail est déjà utilisée.")
        connection.close()

        session["user_id"] = cursor.lastrowid
        session["conversation_id"] = create_conversation(cursor.lastrowid)
        return redirect(url_for("home"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        connection = get_db_connection()
        user = connection.execute(
            "SELECT id, password_hash FROM users WHERE email = ?", (email,)
        ).fetchone()
        connection.close()

        if user is None or not check_password_hash(user["password_hash"], password):
            return render_template("login.html", error="E-mail ou mot de passe incorrect.")

        session["user_id"] = user["id"]
        get_current_conversation(user["id"])
        return redirect(url_for("home"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/conversations")
def conversations():
    user = current_user()
    if user is None:
        return jsonify({"error": "Authentication required"}), 401

    current_id = get_current_conversation(user["id"])
    connection = get_db_connection()
    items = connection.execute(
        "SELECT id, title FROM conversations WHERE user_id = ? ORDER BY id DESC",
        (user["id"],),
    ).fetchall()
    connection.close()
    return jsonify({
        "current_id": current_id,
        "conversations": [dict(item) for item in items],
    })


@app.route("/new-chat", methods=["POST"])
def new_chat():
    user = current_user()
    if user is None:
        return jsonify({"error": "Authentication required"}), 401
    session["conversation_id"] = create_conversation(user["id"])
    return jsonify({"success": True})


@app.route("/select-chat", methods=["POST"])
def select_chat():
    user = current_user()
    if user is None:
        return jsonify({"error": "Authentication required"}), 401
    conversation_id = request.get_json().get("conversation_id")
    connection = get_db_connection()
    conversation = connection.execute(
        "SELECT id FROM conversations WHERE id = ? AND user_id = ?",
        (conversation_id, user["id"]),
    ).fetchone()
    connection.close()
    if conversation is None:
        return jsonify({"error": "Conversation not found"}), 404
    session["conversation_id"] = conversation["id"]
    return jsonify({"success": True})


@app.route("/rename-chat", methods=["POST"])
def rename_chat():
    user = current_user()
    if user is None:
        return jsonify({"error": "Authentication required"}), 401

    data = request.get_json() or {}
    conversation_id = data.get("conversation_id")
    title = data.get("title", "").strip()
    if not title:
        return jsonify({"error": "Le nom ne peut pas être vide."}), 400

    connection = get_db_connection()
    cursor = connection.execute(
        "UPDATE conversations SET title = ? WHERE id = ? AND user_id = ?",
        (title[:80], conversation_id, user["id"]),
    )
    connection.commit()
    connection.close()
    if cursor.rowcount == 0:
        return jsonify({"error": "Conversation not found"}), 404
    return jsonify({"success": True, "title": title[:80]})


@app.route("/history")
def history():
    user = current_user()
    if user is None:
        return jsonify({"error": "Authentication required"}), 401

    connection = get_db_connection()
    conversation_id = get_current_conversation(user["id"])
    messages = connection.execute(
        "SELECT role, content FROM messages WHERE user_id = ? AND conversation_id = ? ORDER BY id",
        (user["id"], conversation_id),
    ).fetchall()
    connection.close()
    return jsonify({"messages": [dict(message) for message in messages]})


@app.route("/chat", methods=["POST"])
def chat():

    user = current_user()
    if user is None:
        return jsonify({"error": "Authentication required"}), 401

    data = request.get_json()
    question = data.get("message")

    if not question:
        return jsonify({
            "error": "Message cannot be empty"
        }), 400

    try:

        conversation_id = get_current_conversation(user["id"])
        connection = get_db_connection()
        previous_messages = connection.execute(
            "SELECT role, content FROM messages WHERE user_id = ? AND conversation_id = ? ORDER BY id",
            (user["id"], conversation_id),
        ).fetchall()
        connection.execute(
            "INSERT INTO messages (user_id, conversation_id, role, content) VALUES (?, ?, 'user', ?)",
            (user["id"], conversation_id, question),
        )
        connection.commit()

        chat_history = [
            {"role": message["role"], "parts": [{"text": message["content"]}]}
            for message in previous_messages
        ]
        chat_history.append({"role": "user", "parts": [{"text": question}]})

        # Send the whole conversation to Gemini
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=chat_history
        )

        answer = response.text

        connection.execute(
            "INSERT INTO messages (user_id, conversation_id, role, content) VALUES (?, ?, 'model', ?)",
            (user["id"], conversation_id, answer),
        )
        connection.commit()
        connection.close()

        return jsonify({
            "response": answer
        })

    except Exception as e:

        print("ERROR:", str(e))

        return jsonify({
            "error": str(e)
        }), 500


if __name__ == "__main__":
    app.run(debug=True)