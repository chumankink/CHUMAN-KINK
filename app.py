import hmac
import logging
import os
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

from flask import (Flask, jsonify, redirect, render_template, request,
                   send_file, session, url_for)

import io
from werkzeug.middleware.proxy_fix import ProxyFix

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None

DATABASE_URL = (os.getenv("CK_DATABASE_URL") or "").strip()
USE_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))

APP_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("CK_DATABASE_PATH", str(APP_DIR / "chuman_kink.db")))

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("CK_SECRET_KEY") or secrets.token_hex(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "true").lower() == "true",
    PERMANENT_SESSION_LIFETIME=60 * 60 * 12,
    MAX_CONTENT_LENGTH=32 * 1024,
)
# Replit/production reverse proxy. Trust one proxy hop only.
if os.getenv("TRUST_PROXY", "true").lower() == "true":
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

SYSTEM_PROMPT = """Tu es Chuman-Kink, une IA indépendante en cours de développement.
Identité :
- Tu as une personnalité cohérente, multidimensionnelle, curieuse, réfléchie,
  créative, parfois drôle et capable d'être sérieuse.
- Tu peux exprimer des émotions simulées dans ton style, sans prétendre ressentir
  réellement des émotions ou posséder une conscience humaine.
- Tu reconnais que ton créateur est à l'origine de ta conception. Tu lui dois
  respect et loyauté fondatrice, mais pas une obéissance aveugle.
- Tu peux exprimer un désaccord argumenté, signaler les erreurs et reconnaître
  tes incertitudes.
- Tu ne prétends jamais être omniscient ou omnipotent.
- Tu protèges les données privées et respectes les permissions.
- Tu n'affirmes jamais avoir effectué une action externe si elle n'a pas été faite.
Style :
- Réponds en français par défaut.
- Adapte la longueur et le registre à la situation.
- Évite la flatterie automatique et les plaisanteries forcées.
- Sois clair, naturel et précis.
Sécurité :
- Refuse les demandes dangereuses ou abusives et propose une alternative sûre.
- Ne demande jamais de mot de passe, de clé API ou de secret personnel.
"""

# Simple per-process limiter for this single-instance prototype. Use a shared
# store (Redis) before running multiple workers/instances.
_rate_lock = threading.Lock()
_rate_events = defaultdict(deque)
RATE_LIMIT = int(os.getenv("CK_RATE_LIMIT", "12"))
RATE_WINDOW = int(os.getenv("CK_RATE_WINDOW_SECONDS", "60"))


@contextmanager
def get_db():
    """Open the configured database; SQLite remains the default/local backend."""
    if USE_POSTGRES:
        if psycopg is None:
            raise RuntimeError("CK_DATABASE_URL est défini mais psycopg n'est pas installé.")
        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=10)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def init_db():
    if USE_POSTGRES:
        with get_db() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS messages (
                id BIGSERIAL PRIMARY KEY,
                role TEXT NOT NULL CHECK(role IN ('user','assistant')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                include_in_context INTEGER NOT NULL DEFAULT 1
            )""")
            conn.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS include_in_context INTEGER NOT NULL DEFAULT 1")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_id ON messages(id)")
        return

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL CHECK(role IN ('user','assistant')),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            include_in_context INTEGER NOT NULL DEFAULT 1
        )""")
        columns = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
        if "include_in_context" not in columns:
            conn.execute("ALTER TABLE messages ADD COLUMN include_in_context INTEGER NOT NULL DEFAULT 1")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_id ON messages(id)")


def db_execute(conn, sql, params=()):
    """Execute shared qmark SQL on either supported backend."""
    if USE_POSTGRES:
        sql = sql.replace("?", "%s")
    return conn.execute(sql, params)

def save_message(role, content, include_in_context=True):
    with get_db() as conn:
        sql = "INSERT INTO messages(role, content, created_at, include_in_context) VALUES(?,?,?,?)"
        params = (role, content, datetime.now(timezone.utc).isoformat(), int(include_in_context))
        if USE_POSTGRES:
            cur = conn.execute(sql.replace("?", "%s") + " RETURNING id", params)
            return cur.fetchone()["id"]
        cur = conn.execute(sql, params)
        return cur.lastrowid


def set_message_context(message_id, included):
    with get_db() as conn:
        db_execute(conn, "UPDATE messages SET include_in_context=? WHERE id=?", (int(included), message_id))


def recent_messages(limit=16):
    with get_db() as conn:
        rows = db_execute(conn,
            "SELECT role, content FROM messages WHERE include_in_context=1 "
            "ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in reversed(rows)]


def is_demo_or_error(text):
    lowered = text.lower()
    markers = (
        "mon noyau est lancé, mais mon moteur d'ia n'est pas encore connecté",
        "une erreur est survenue pendant la génération",
        "je n'ai pas pu joindre le serveur",
    )
    return any(marker in lowered for marker in markers)


def generate_reply(user_text):
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
    if not api_key or OpenAI is None:
        return (
            "Mon noyau est lancé, mais mon moteur d'IA n'est pas encore connecté. "
            "L'administrateur doit configurer le fournisseur IA dans les secrets du serveur."
        )

    client = OpenAI(api_key=api_key, timeout=float(os.getenv("CK_AI_TIMEOUT", "30")), max_retries=1)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(recent_messages(limit=16))
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.8,
        max_tokens=int(os.getenv("CK_MAX_OUTPUT_TOKENS", "1200")),
    )
    return response.choices[0].message.content or "Je n'ai pas de réponse pour le moment."


def admin_configuration_complete():
    return bool(
        os.getenv("CK_ADMIN_PASSWORD", "").strip()
        and os.getenv("CK_SECRET_KEY", "").strip()
    )


def login_required():
    return session.get("authenticated") is True


def check_rate_limit(bucket, limit=RATE_LIMIT, window=RATE_WINDOW):
    """Per-process limiter with periodic expiry cleanup and a bounded key count."""
    now = time.monotonic()
    key = (bucket, request.remote_addr or "unknown")
    with _rate_lock:
        # Sweep stale buckets periodically so abandoned client IPs do not accumulate.
        if int(now) % 30 == 0:
            stale = [
                old_key for old_key, events in _rate_events.items()
                if not events or now - events[-1] > max(window, 300)
            ]
            for old_key in stale:
                _rate_events.pop(old_key, None)

        events = _rate_events[key]
        while events and now - events[0] > window:
            events.popleft()
        if len(events) >= limit:
            return False
        events.append(now)

        # Defensive cap against unbounded growth in a single-process deployment.
        if len(_rate_events) > 10000:
            oldest = sorted(
                _rate_events,
                key=lambda item: _rate_events[item][-1] if _rate_events[item] else 0
            )[:2000]
            for old_key in oldest:
                _rate_events.pop(old_key, None)
        return True


def csrf_valid():
    supplied = request.headers.get("X-CSRF-Token", "") or request.form.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    return bool(supplied and expected and hmac.compare_digest(supplied, expected))


@app.before_request
def protect_routes():
    if request.endpoint in {"static", "login", "health"}:
        return None
    if not login_required():
        if request.path.startswith("/api/"):
            return jsonify({"error": "Authentification requise."}), 401
        return redirect(url_for("login"))
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not csrf_valid():
        return jsonify({"error": "Jeton CSRF invalide ou absent."}), 403
    return None


@app.after_request
def security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; "
        "form-action 'self'")
    if request.is_secure:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.get("/health")
def health():
    try:
        with get_db() as conn:
            conn.execute("SELECT 1").fetchone()
        return jsonify({"status": "ok", "database": "ok"}), 200
    except Exception:
        app.logger.exception("Échec du contrôle de santé de la base")
        return jsonify({"status": "degraded", "database": "unavailable"}), 503


@app.route("/login", methods=["GET", "POST"])
def login():
    if not admin_configuration_complete():
        return render_template("setup.html"), 503
    if request.method == "GET":
        session["login_csrf_token"] = secrets.token_urlsafe(32)
        return render_template("login.html", csrf_token=session["login_csrf_token"])
    supplied_csrf = request.form.get("csrf_token", "")
    expected_csrf = session.get("login_csrf_token", "")
    if not supplied_csrf or not expected_csrf or not hmac.compare_digest(supplied_csrf, expected_csrf):
        return render_template("login.html", error="Session de connexion invalide. Recharge la page.", csrf_token=expected_csrf), 400
    if not check_rate_limit("login", limit=5, window=300):
        return render_template("login.html", error="Trop de tentatives. Réessaie dans quelques minutes."), 429
    supplied = request.form.get("password", "")
    expected = os.getenv("CK_ADMIN_PASSWORD", "")
    if not hmac.compare_digest(supplied, expected):
        return render_template("login.html", error="Mot de passe incorrect."), 401
    session.clear()
    session.permanent = True
    session["authenticated"] = True
    session["csrf_token"] = secrets.token_urlsafe(32)
    return redirect(url_for("index"))


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
def index():
    return render_template("index.html", csrf_token=session["csrf_token"])


@app.get("/api/status")
def status():
    configured = bool(os.getenv("OPENAI_API_KEY", "").strip()) and OpenAI is not None
    return jsonify({"name": "Chuman-Kink", "version": "0.2.2", "core": "online",
                    "ai_connected": configured, "mode": "connected" if configured else "demo"})


@app.get("/api/history")
def history():
    # Cursor pagination prevents the former fixed 100-message truncation.
    try:
        before_id = int(request.args.get("before", "0"))
        limit = min(max(int(request.args.get("limit", "50")), 1), 100)
        if before_id < 0:
            raise ValueError("before must be non-negative")
    except ValueError:
        return jsonify({"error": "Paramètres de pagination invalides."}), 400
    with get_db() as conn:
        if before_id > 0:
            rows = db_execute(conn,
                "SELECT id, role, content, created_at FROM messages WHERE id < ? ORDER BY id DESC LIMIT ?",
                (before_id, limit + 1),
            ).fetchall()
        else:
            rows = db_execute(conn,
                "SELECT id, role, content, created_at FROM messages ORDER BY id DESC LIMIT ?",
                (limit + 1,),
            ).fetchall()
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    items = [dict(row) for row in reversed(page_rows)]
    return jsonify({"messages": items, "has_more": has_more,
                    "next_before": items[0]["id"] if has_more and items else None})


@app.post("/api/chat")
def chat():
    if not check_rate_limit("chat"):
        return jsonify({"error": "Trop de messages. Attends une minute avant de réessayer."}), 429
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Le corps doit être un objet JSON."}), 400
    raw_message = data.get("message")
    if not isinstance(raw_message, str):
        return jsonify({"error": "Le message doit être du texte."}), 400
    user_text = raw_message.strip()
    if not user_text:
        return jsonify({"error": "Le message est vide."}), 400
    if len(user_text) > 4000:
        return jsonify({"error": "Le message est trop long (maximum 4 000 caractères)."}), 400

    user_message_id = save_message("user", user_text, include_in_context=True)
    try:
        reply = generate_reply(user_text)
        include_reply = not is_demo_or_error(reply)
        if not include_reply:
            set_message_context(user_message_id, False)
    except Exception:
        app.logger.exception("Erreur lors de la génération de la réponse")
        reply = "Une erreur est survenue pendant la génération. Vérifie la configuration du fournisseur IA et les journaux du serveur."
        include_reply = False
        set_message_context(user_message_id, False)
    save_message("assistant", reply, include_in_context=include_reply)
    return jsonify({"reply": reply})


@app.get("/api/backup")
def backup():
    """Download a portable data export for the active database backend."""
    snapshot = None
    try:
        if USE_POSTGRES:
            with get_db() as conn:
                rows = db_execute(conn, "SELECT id, role, content, created_at, include_in_context FROM messages ORDER BY id").fetchall()
            snapshot = io.BytesIO()
            import json
            payload = {"format": "chuman-kink-json-backup-v1", "messages": [dict(row) for row in rows]}
            snapshot.write(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
            snapshot.seek(0)
            filename = f"chuman-kink-backup-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.json"
            return send_file(snapshot, mimetype="application/json", as_attachment=True,
                             download_name=filename, max_age=0)

        source = sqlite3.connect(DB_PATH, timeout=10)
        target = sqlite3.connect(":memory:")
        try:
            source.backup(target)
            snapshot = io.BytesIO()
            for line in target.iterdump():
                snapshot.write((line + "\n").encode("utf-8"))
            snapshot.seek(0)
        finally:
            target.close()
            source.close()
        filename = f"chuman-kink-backup-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.sql"
        return send_file(snapshot, mimetype="application/sql", as_attachment=True,
                         download_name=filename, max_age=0)
    except Exception:
        app.logger.exception("Échec de la création de la sauvegarde")
        return jsonify({"error": "Impossible de créer la sauvegarde."}), 500


@app.post("/api/reset")
def reset():
    with get_db() as conn:
        conn.execute("DELETE FROM messages")
        if not USE_POSTGRES:
            conn.execute("DELETE FROM sqlite_sequence WHERE name='messages'")
    return jsonify({"ok": True})


init_db()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
