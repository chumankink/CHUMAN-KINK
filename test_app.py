"""Tests de base pour CHUMAN-KINK 0.2.2 (pytest)."""
import os
import tempfile
import importlib

def setup_module():
    global app_module, temp_dir
    temp_dir = tempfile.TemporaryDirectory()
    os.environ["CK_DATABASE_PATH"] = os.path.join(temp_dir.name, "test.db")
    os.environ["CK_ADMIN_PASSWORD"] = "test-password-long"
    os.environ["CK_SECRET_KEY"] = "test-secret-key-for-tests-only"
    os.environ["COOKIE_SECURE"] = "false"
    import app as app_module
    app_module.DB_PATH = __import__("pathlib").Path(os.environ["CK_DATABASE_PATH"])
    app_module.init_db()
    app_module.app.config.update(TESTING=True)

def teardown_module():
    temp_dir.cleanup()

def login(client):
    page = client.get("/login")
    assert page.status_code == 200
    import re
    token = re.search(rb'name="csrf_token" value="([^"]+)"', page.data).group(1).decode()
    return client.post("/login", data={"csrf_token": token, "password": "test-password-long"})

def test_auth_and_health():
    client = app_module.app.test_client()
    assert client.get("/health").status_code == 200
    assert client.get("/api/history").status_code == 401
    assert login(client).status_code == 302
    assert client.get("/").status_code == 200

def test_csrf_and_pagination_and_backup():
    client = app_module.app.test_client()
    login(client)
    assert client.post("/api/chat", json={"message": "hello"}).status_code == 403
    with client.session_transaction() as sess:
        token = sess["csrf_token"]
    headers = {"X-CSRF-Token": token}
    assert client.post("/api/chat", json={"message": "hello"}, headers=headers).status_code == 200
    assert client.get("/api/history?before=-1").status_code == 400
    backup = client.get("/api/backup")
    assert backup.status_code == 200
    assert len(backup.data) > 0


def test_backup_restores_into_separate_database_and_file_is_readable_from_another_process():
    import sqlite3
    import subprocess
    import sys

    client = app_module.app.test_client()
    login(client)
    with client.session_transaction() as sess:
        token = sess["csrf_token"]
    headers = {"X-CSRF-Token": token}

    response = client.post("/api/chat", json={"message": "backup round-trip"}, headers=headers)
    assert response.status_code == 200

    backup = client.get("/api/backup")
    assert backup.status_code == 200
    sql_dump = backup.data.decode("utf-8")
    assert "\n" in sql_dump
    assert "\\n" not in sql_dump

    restored_path = os.path.join(temp_dir.name, "restored.db")
    restored = sqlite3.connect(restored_path)
    try:
        restored.executescript(sql_dump)
        restored.commit()
        integrity = restored.execute("PRAGMA integrity_check").fetchone()[0]
        assert integrity == "ok"
        rows = restored.execute(
            "SELECT role, content FROM messages ORDER BY id"
        ).fetchall()
        assert any(content == "backup round-trip" for _, content in rows)
    finally:
        restored.close()

    # A fresh interpreter can read the same database file independently.
    script = (
        "import sqlite3,sys; "
        "c=sqlite3.connect(sys.argv[1]); "
        "print(c.execute('SELECT COUNT(*) FROM messages').fetchone()[0]); "
        "c.close()"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, os.environ["CK_DATABASE_PATH"]],
        check=True, capture_output=True, text=True,
    )
    assert int(result.stdout.strip()) >= 2
