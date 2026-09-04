from flask import Flask, request, render_template, jsonify, redirect, url_for, session
from functools import wraps
import sqlite3
from datetime import datetime, timedelta
import re
import os
import secrets
import requests
from dotenv import load_dotenv

# Загружаем .env из папки проекта независимо от текущей рабочей директории.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(16))

# ============================================================
# НАСТРОЙКИ
# ============================================================

PRICE_PER_SHARD = 1.50
DATABASE = os.path.join(BASE_DIR, "shop.db")

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
DISCORD_REVIEWS_WEBHOOK = os.getenv("DISCORD_REVIEWS_WEBHOOK", "")

ADMIN_KEY = os.getenv("ADMIN_KEY", "admin123")
PAYMENT_DETAILS = os.getenv("PAYMENT_DETAILS", "Карта: 1234 5678 9012 3456")

# ============================================================
# ДЕКОРАТОРЫ
# ============================================================

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.args.get('key') or request.headers.get('X-Admin-Key')
        if session.get('admin_auth') or key == ADMIN_KEY:
            if key == ADMIN_KEY:
                session['admin_auth'] = True
            return f(*args, **kwargs)
        return redirect(url_for('admin_login_page', next=request.url))
    return decorated

# ============================================================
# БАЗА ДАННЫХ
# ============================================================

def get_db():
    conn = sqlite3.connect(DATABASE, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def create_database():
    conn = get_db()
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER DEFAULT 0,
            nickname TEXT NOT NULL,
            shards INTEGER NOT NULL,
            price REAL NOT NULL,
            status TEXT NOT NULL,
            chat_token TEXT UNIQUE,
            created_at TEXT NOT NULL,
            paid_at TEXT,
            completed_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            sender TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders (id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nickname TEXT NOT NULL,
            rating INTEGER NOT NULL,
            review_text TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reviewed_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER UNIQUE NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    # Миграция старой базы: добавляем user_id, если его нет
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(orders)").fetchall()]
        if "user_id" not in cols:
            conn.execute("ALTER TABLE orders ADD COLUMN user_id INTEGER DEFAULT 0")
    except Exception as e:
        print("DB migration error:", e)

    conn.commit()
    conn.close()

# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def valid_nickname(nickname):
    return bool(re.fullmatch(r"[A-Za-z0-9_]{1,16}", nickname))

def generate_token():
    return secrets.token_urlsafe(32)

def send_discord_order_notification(order, chat_url):
    if not DISCORD_WEBHOOK_URL:
        return False
    try:
        content = (
            f"📦 **Новый заказ!**\n"
            f"**Игрок:** {order['nickname']}\n"
            f"**ШАРДЫ:** {order['shards']}\n"
            f"**Сумма:** {order['price']} ₽\n"
            f"**ID заказа:** #{order['id']}\n"
            f"**Ссылка на чат:** {chat_url}\n\n"
            f"📌 Админы, перейдите в админ-панель."
        )
        response = requests.post(DISCORD_WEBHOOK_URL, json={"content": content}, timeout=5)
        return response.status_code in (200, 204)
    except Exception as e:
        print(f"[Discord error] {e}")
        return False

def send_discord_review(review_data):
    webhook = DISCORD_REVIEWS_WEBHOOK.strip()
    if not webhook:
        print("[Discord review] Webhook не загружен: DISCORD_REVIEWS_WEBHOOK пуст.")
        return False

    try:
        rating = max(1, min(5, int(review_data.get("rating", 0))))
        nickname = str(review_data.get("nickname", "")).strip()
        review_text = str(review_data.get("review_text", "")).strip()

        content = (
            "⭐ **Новый отзыв!**\n"
            f"**Игрок:** {nickname}\n"
            f"**Оценка:** {'⭐' * rating} ({rating}/5)\n"
            f"**Текст:** {review_text}"
        )

        response = requests.post(
            webhook,
            json={"content": content},
            headers={"Content-Type": "application/json", "User-Agent": "YLWSMP-ReviewBot/1.0"},
            timeout=10,
        )

        print(f"[Discord review] HTTP {response.status_code}")
        if response.status_code not in (200, 204):
            print(f"[Discord review] Ответ Discord: {response.text[:1000]}")
            return False

        print("[Discord review] Отзыв успешно отправлен.")
        return True

    except requests.RequestException as e:
        print(f"[Discord review] Ошибка сети: {e}")
        return False
    except Exception as e:
        print(f"[Discord review] Ошибка: {e}")
        return False

def add_system_message(order_id, message):
    conn = get_db()
    conn.execute(
        "INSERT INTO messages (order_id, sender, message, created_at) VALUES (?, ?, ?, ?)",
        (order_id, 'system', message, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def auto_complete_old_orders():
    three_days_ago = (datetime.now() - timedelta(days=3)).isoformat()
    conn = get_db()
    conn.execute(
        "UPDATE orders SET status = 'completed', completed_at = ? WHERE status = 'paid' AND paid_at < ?",
        (datetime.now().isoformat(), three_days_ago)
    )
    affected = conn.total_changes
    conn.commit()
    conn.close()
    return affected

# ============================================================
# ГЛАВНАЯ (магазин)
# ============================================================

@app.route("/", methods=["GET", "POST"])
def shop():
    auto_complete_old_orders()

    if request.method == "POST":
        nickname = request.form.get("nickname", "").strip()
        shards_text = request.form.get("shards", "0").strip()

        if not nickname or not valid_nickname(nickname):
            return "Ошибка: некорректный Minecraft-ник!", 400

        try:
            shards = int(shards_text)
        except ValueError:
            return "Ошибка: количество должно быть числом!", 400

        if shards < 1 or shards > 100000:
            return "Ошибка: количество от 1 до 100000!", 400

        price = round(shards * PRICE_PER_SHARD, 2)
        token = generate_token()

        conn = get_db()
        cursor = conn.execute(
            """
            INSERT INTO orders (user_id, nickname, shards, price, status, chat_token, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (0, nickname, shards, price, "waiting_payment", token, datetime.now().isoformat())
        )
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()

        order = {
            "id": order_id,
            "nickname": nickname,
            "shards": shards,
            "price": price,
            "status": "waiting_payment",
            "chat_token": token
        }

        chat_url = request.url_root.rstrip('/') + f"/chat/{token}"
        send_discord_order_notification(order, chat_url)

        welcome = f"Йоу, привет! В скором времени тебе ответит админ. Для получения шардов переведи деньги по реквизитам: {PAYMENT_DETAILS}"
        add_system_message(order_id, welcome)

        return redirect(f'/chat/{token}')

    return render_template("index.html", active="shop")

# ============================================================
# ЧАТ ДЛЯ ИГРОКА
# ============================================================

@app.route('/chat/<token>')
def chat_page(token):
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE chat_token = ?", (token,)).fetchone()
    if not order:
        conn.close()
        return "Чат не найден", 404

    auto_complete_old_orders()

    messages = conn.execute("SELECT * FROM messages WHERE order_id = ? ORDER BY created_at", (order['id'],)).fetchall()
    conn.close()

    return render_template('chat.html',
        order=dict(order),
        messages=[dict(m) for m in messages],
        token=token,
        payment_details=PAYMENT_DETAILS
    )

@app.route('/api/chat/<token>/messages')
def get_messages(token):
    conn = get_db()
    order = conn.execute("SELECT id FROM orders WHERE chat_token = ?", (token,)).fetchone()
    if not order:
        conn.close()
        return jsonify({"ok": False, "error": "Чат не найден"}), 404
    messages = conn.execute("SELECT sender, message, created_at FROM messages WHERE order_id = ? ORDER BY created_at", (order['id'],)).fetchall()
    conn.close()
    return jsonify({
        "ok": True,
        "messages": [{"sender": m["sender"], "message": m["message"], "created_at": m["created_at"]} for m in messages]
    })

@app.route('/api/chat/<token>/send', methods=['POST'])
def send_message(token):
    data = request.get_json()
    message = data.get('message', '').strip()
    if not message:
        return jsonify({"ok": False, "error": "Сообщение не может быть пустым"}), 400

    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE chat_token = ?", (token,)).fetchone()
    if not order:
        conn.close()
        return jsonify({"ok": False, "error": "Чат не найден"}), 404

    # Антифлуд
    last_msg = conn.execute(
        "SELECT created_at FROM messages WHERE order_id = ? AND sender = 'player' ORDER BY created_at DESC LIMIT 1",
        (order['id'],)
    ).fetchone()
    if last_msg:
        last_time = datetime.fromisoformat(last_msg['created_at'])
        if (datetime.now() - last_time).total_seconds() < 5:
            conn.close()
            return jsonify({"ok": False, "error": "Слишком часто! Подождите 5 секунд."}), 429

    conn.execute(
        "INSERT INTO messages (order_id, sender, message, created_at) VALUES (?, ?, ?, ?)",
        (order['id'], 'player', message, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route('/api/chat/<token>/mark_paid', methods=['POST'])
def mark_order_paid(token):
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE chat_token = ?", (token,)).fetchone()
    if not order:
        conn.close()
        return jsonify({"ok": False, "error": "Заказ не найден"}), 404

    if order['status'] != 'waiting_payment':
        conn.close()
        return jsonify({"ok": False, "error": "Заказ уже обработан"}), 400

    conn.execute(
        "UPDATE orders SET status = 'paid', paid_at = ? WHERE id = ?",
        (datetime.now().isoformat(), order['id'])
    )
    conn.commit()
    add_system_message(order['id'], "✅ Игрок подтвердил оплату. Ожидайте выдачи шардов.")
    conn.close()
    return jsonify({"ok": True, "message": "Оплата подтверждена!"})

# ============================================================
# АДМИН-ПАНЕЛЬ
# ============================================================

@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login_page():
    error = None
    next_url = request.args.get('next')
    if request.method == 'POST':
        password = request.form.get('password', '').strip()
        if password == ADMIN_KEY:
            session['admin_auth'] = True
            if next_url:
                from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
                parsed = urlparse(next_url)
                query = parse_qs(parsed.query)
                query['key'] = [password]
                new_query = urlencode(query, doseq=True)
                new_url = urlunparse(parsed._replace(query=new_query))
                return redirect(new_url)
            else:
                return redirect(url_for('admin_panel', key=password))
        else:
            error = 'Неверный пароль!'
    return render_template('admin_login.html', error=error)

@app.route('/admin')
@admin_required
def admin_panel():
    auto_complete_old_orders()
    conn = get_db()
    orders = conn.execute("""
        SELECT orders.*,
               (SELECT COUNT(*) FROM messages WHERE messages.order_id = orders.id AND messages.sender = 'player') as unread
        FROM orders
        ORDER BY id DESC
    """).fetchall()
    conn.close()
    return render_template('admin.html', orders=[dict(o) for o in orders])

@app.route('/admin/chat/<token>')
@admin_required
def admin_chat(token):
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE chat_token = ?", (token,)).fetchone()
    if not order:
        conn.close()
        return "Чат не найден", 404
    messages = conn.execute("SELECT * FROM messages WHERE order_id = ? ORDER BY created_at", (order['id'],)).fetchall()
    conn.close()
    return render_template('admin_chat.html',
        order=dict(order),
        messages=[dict(m) for m in messages],
        token=token
    )

@app.route('/api/admin/chat/<token>/send', methods=['POST'])
@admin_required
def admin_send_message(token):
    data = request.get_json()
    message = data.get('message', '').strip()
    if not message:
        return jsonify({"ok": False, "error": "Сообщение не может быть пустым"}), 400

    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE chat_token = ?", (token,)).fetchone()
    if not order:
        conn.close()
        return jsonify({"ok": False, "error": "Чат не найден"}), 404

    conn.execute(
        "INSERT INTO messages (order_id, sender, message, created_at) VALUES (?, ?, ?, ?)",
        (order['id'], 'admin', message, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route('/admin/give', methods=['POST'])
@admin_required
def admin_give():
    data = request.get_json()
    nickname = data.get('nickname', '').strip()
    amount = data.get('amount', 0)

    if not nickname or amount <= 0:
        return jsonify({"ok": False, "message": "Неверные данные"}), 400

    conn = get_db()
    orders = conn.execute(
        "SELECT * FROM orders WHERE nickname = ? AND status IN ('waiting_payment', 'paid')",
        (nickname,)
    ).fetchall()

    if not orders:
        conn.close()
        return jsonify({"ok": False, "message": "Нет активных заказов для выдачи"}), 404

    for order in orders:
        conn.execute(
            "UPDATE orders SET status = 'completed', completed_at = ? WHERE id = ?",
            (datetime.now().isoformat(), order['id'])
        )
    conn.commit()

    for order in orders:
        add_system_message(order['id'], f"🎉 Администратор выдал вам {amount} шардов. Спасибо за покупку!")
        add_system_message(order['id'], "📝 Покупка завершена! Оставьте отзыв в открывшемся окне.")

    conn.close()
    return jsonify({"ok": True, "message": f"Шарды выданы игроку {nickname}"})

@app.route('/admin/mark_paid', methods=['POST'])
@admin_required
def admin_mark_paid():
    data = request.get_json()
    order_id = data.get('order_id')
    if not order_id:
        return jsonify({"ok": False, "message": "Не указан ID заказа"}), 400

    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        conn.close()
        return jsonify({"ok": False, "message": "Заказ не найден"}), 404

    if order['status'] != 'waiting_payment':
        conn.close()
        return jsonify({"ok": False, "message": "Заказ уже обработан"}), 400

    conn.execute(
        "UPDATE orders SET status = 'paid', paid_at = ? WHERE id = ?",
        (datetime.now().isoformat(), order_id)
    )
    conn.commit()
    add_system_message(order_id, "✅ Администратор подтвердил оплату. Ожидайте выдачи шардов.")
    conn.close()
    return jsonify({"ok": True, "message": "Заказ отмечен как оплаченный"})

# ============================================================
# ОТЗЫВЫ
# ============================================================


@app.route('/order-review/<token>', methods=['POST'])
def submit_order_review(token):
    data = request.get_json() or {}
    rating = int(data.get('rating', 0))
    text = str(data.get('review_text', '')).strip()
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE chat_token = ? AND status = 'completed'", (token,)).fetchone()
    if not order:
        conn.close(); return jsonify({"ok": False, "error": "Покупка еще не завершена"}), 400
    exists = conn.execute("SELECT 1 FROM reviewed_orders WHERE order_id = ?", (order['id'],)).fetchone()
    if exists:
        conn.close(); return jsonify({"ok": False, "error": "Отзыв уже оставлен"}), 400
    if rating < 1 or rating > 5 or not text:
        conn.close(); return jsonify({"ok": False, "error": "Заполните отзыв"}), 400
    conn.execute("INSERT INTO reviews (nickname, rating, review_text, created_at) VALUES (?, ?, ?, ?)", (order['nickname'], rating, text, datetime.now().isoformat()))
    conn.execute("INSERT INTO reviewed_orders (order_id, created_at) VALUES (?, ?)", (order['id'], datetime.now().isoformat()))
    conn.commit(); conn.close()
    send_discord_review({
        'nickname': order['nickname'],
        'rating': rating,
        'review_text': text
    })
    return jsonify({"ok": True})

@app.route('/order-review-status/<token>')
def order_review_status(token):
    conn=get_db()
    row=conn.execute("SELECT orders.status, reviewed_orders.order_id as reviewed FROM orders LEFT JOIN reviewed_orders ON orders.id=reviewed_orders.order_id WHERE orders.chat_token=?", (token,)).fetchone()
    conn.close()
    return jsonify({"show": bool(row and row['status']=='completed' and not row['reviewed'])})

def get_recent_reviews(limit=30):
    conn = get_db()
    reviews = conn.execute(
        "SELECT nickname, rating, review_text, created_at FROM reviews ORDER BY id DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in reviews]

@app.route('/reviews', methods=['GET'])
def reviews_page():
    return render_template('reviews.html', active='reviews', reviews=get_recent_reviews())

# ============================================================
# ТЕСТЫ
# ============================================================

@app.route('/test-discord')
def test_discord():
    if not DISCORD_WEBHOOK_URL:
        return jsonify({"error": "DISCORD_WEBHOOK_URL не задан", "ok": False}), 500
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json={"content": "🔔 Тестовое сообщение с сайта YLWSMP"}, timeout=5)
        return jsonify({
            "status_code": response.status_code,
            "ok": response.status_code in (200, 204)
        })
    except Exception as e:
        return jsonify({"error": str(e), "ok": False}), 500

@app.route('/test-review-discord')
@admin_required
def test_review_discord():
    ok = send_discord_review({
        "nickname": "TEST",
        "rating": 3,
        "review_text": "Тестовое сообщение review webhook с сайта YLWSMP."
    })
    return jsonify({
        "ok": ok,
        "webhook_loaded": bool(DISCORD_REVIEWS_WEBHOOK.strip()),
        "message": "Проверь консоль сервера: там указан HTTP-код Discord."
    }), (200 if ok else 500)

# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":
    create_database()
    app.run(host="0.0.0.0", port=5000, debug=True)