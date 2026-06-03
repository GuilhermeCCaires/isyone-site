import os
import sqlite3
import subprocess
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, redirect, render_template, request, url_for, flash
from markupsafe import escape

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("ISY_DATA_DIR", BASE_DIR / "data"))
SCRIPTS_DIR = Path(os.getenv("ISY_SCRIPTS_DIR", BASE_DIR / "scripts"))
DB_PATH = DATA_DIR / "isyone.db"
DEFAULT_TOKEN = os.getenv("ISY_INITIAL_TOKEN", "isyone-dev-token")

DATA_DIR.mkdir(parents=True, exist_ok=True)
SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(16))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS scripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            file_name TEXT NOT NULL,
            params_schema TEXT,
            description TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS execution_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            executed_at TEXT NOT NULL,
            script_name TEXT NOT NULL,
            params_used TEXT,
            return_code INTEGER,
            status TEXT NOT NULL,
            stdout TEXT,
            stderr TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    existing = cur.execute("SELECT value FROM settings WHERE key = 'api_token'").fetchone()
    if not existing:
        cur.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            ("api_token", DEFAULT_TOKEN, utc_now()),
        )
    conn.commit()
    conn.close()


def seed_scripts():
    conn = get_conn()
    cur = conn.cursor()
    defaults = [
        ("teste", "teste.sh", "{}", "Script de teste", 1),
        ("check_disk", "check_disk.sh", "{}", "Verifica o uso de disco do servidor", 1),
        ("check_memory", "check_memory.sh", "{}", "Verifica o uso de memória do servidor", 1),
        ("hello", "hello.sh", '{"name":"opcional"}', "Script de teste parametrizável", 1),
    ]
    for name, file_name, params_schema, description, active in defaults:
        cur.execute(
            """
            INSERT OR IGNORE INTO scripts
            (name, file_name, params_schema, description, active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (name, file_name, params_schema, description, active, utc_now(), utc_now()),
        )
    conn.commit()
    conn.close()


def get_token() -> str:
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key = 'api_token'").fetchone()
    conn.close()
    return row["value"] if row else DEFAULT_TOKEN


def set_token(new_token: str):
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO settings (key, value, updated_at)
        VALUES ('api_token', ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (new_token, utc_now()),
    )
    conn.commit()
    conn.close()


def require_api_token():
    sent_token = request.headers.get("X-Isy-Token")
    expected = get_token()
    if not sent_token or not secrets.compare_digest(sent_token, expected):
        return jsonify({"error": "Token inválido ou ausente. Envie X-Isy-Token no cabeçalho HTTP."}), 401
    return None


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def get_script_by_name(name: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM scripts WHERE name = ?", (name,)).fetchone()
    conn.close()
    return row_to_dict(row) if row else None


def safe_script_path(file_name: str) -> Path:
    candidate = (SCRIPTS_DIR / file_name).resolve()
    base = SCRIPTS_DIR.resolve()
    if base not in candidate.parents and candidate != base:
        raise ValueError("Caminho de script inválido")
    if candidate.suffix != ".sh":
        raise ValueError("Somente arquivos .sh são permitidos")
    return candidate


def normalize_params(payload: dict[str, Any]) -> list[str]:
    params = payload.get("params", [])
    if isinstance(params, dict):
        result = []
        for key, value in params.items():
            result.append(f"--{key}")
            if value is not None and value is not True:
                result.append(str(value))
        return result
    if isinstance(params, list):
        return [str(item) for item in params]
    return []


def save_execution_log(script_name: str, params_used: list[str], return_code: int | None, status: str, stdout: str, stderr: str):
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO execution_logs
        (executed_at, script_name, params_used, return_code, status, stdout, stderr)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (utc_now(), script_name, " ".join(params_used), return_code, status, stdout, stderr),
    )
    conn.commit()
    conn.close()


def try_save_execution_log(script_name: str, params_used: list[str], return_code: int | None, status: str, stdout: str, stderr: str) -> str:
    try:
        save_execution_log(script_name, params_used, return_code, status, stdout, stderr)
    except Exception as exc:
        return f"Falha ao salvar log de execução: {exc}"
    return ""


def render_execution_result(script: sqlite3.Row, status: str, return_code: int | None, stdout: str, stderr: str):
    try:
        return render_template(
            "resultado.html",
            script=script,
            status=status,
            return_code=return_code,
            stdout=stdout,
            stderr=stderr,
        )
    except Exception as exc:
        script_name = script["name"] if script else "desconhecido"
        body = f"""
        <!doctype html>
        <html lang="pt-br">
        <head><meta charset="utf-8"><title>Resultado da execução</title></head>
        <body>
          <h1>Resultado da execução</h1>
          <p><strong>Script:</strong> {escape(script_name)}</p>
          <p><strong>Status:</strong> {escape(status)}</p>
          <p><strong>Código de retorno:</strong> {escape(return_code)}</p>
          <h2>Saída</h2>
          <pre>{escape(stdout)}</pre>
          <h2>Erro</h2>
          <pre>{escape(stderr)}</pre>
          <h2>Erro ao renderizar template</h2>
          <pre>{escape(str(exc))}</pre>
          <p><a href="/admin/scripts">Voltar para scripts</a></p>
        </body>
        </html>
        """
        return Response(body, status=200, mimetype="text/html")


@app.before_request
def setup():
    init_db()
    seed_scripts()


@app.get("/")
def dashboard():
    conn = get_conn()
    total_scripts = conn.execute("SELECT COUNT(*) AS c FROM scripts").fetchone()["c"]
    active_scripts = conn.execute("SELECT COUNT(*) AS c FROM scripts WHERE active = 1").fetchone()["c"]
    total_logs = conn.execute("SELECT COUNT(*) AS c FROM execution_logs").fetchone()["c"]
    recent_logs = conn.execute("SELECT * FROM execution_logs ORDER BY id DESC LIMIT 5").fetchall()
    conn.close()
    return render_template(
        "dashboard.html",
        total_scripts=total_scripts,
        active_scripts=active_scripts,
        total_logs=total_logs,
        recent_logs=recent_logs,
        token=get_token(),
    )


@app.get("/admin/scripts")
def scripts_admin():
    conn = get_conn()
    scripts = conn.execute("SELECT * FROM scripts ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("scripts.html", scripts=scripts)


@app.post("/admin/scripts")
def create_script():
    name = request.form.get("name", "").strip()
    file_name = request.form.get("file_name", "").strip()
    params_schema = request.form.get("params_schema", "{}").strip()
    description = request.form.get("description", "").strip()
    active = 1 if request.form.get("active") == "on" else 0

    if not name or not file_name or not description:
        flash("Nome, arquivo e descrição são obrigatórios.", "danger")
        return redirect(url_for("scripts_admin"))

    try:
        safe_script_path(file_name)
        conn = get_conn()
        conn.execute(
            """
            INSERT INTO scripts (name, file_name, params_schema, description, active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (name, file_name, params_schema, description, active, utc_now(), utc_now()),
        )
        conn.commit()
        conn.close()
        flash("Script cadastrado com sucesso.", "success")
    except Exception as exc:
        flash(f"Erro ao cadastrar script: {exc}", "danger")
    return redirect(url_for("scripts_admin"))


@app.post("/admin/scripts/<int:script_id>/toggle")
def toggle_script(script_id: int):
    conn = get_conn()
    row = conn.execute("SELECT active FROM scripts WHERE id = ?", (script_id,)).fetchone()
    if row:
        new_status = 0 if row["active"] else 1
        conn.execute("UPDATE scripts SET active = ?, updated_at = ? WHERE id = ?", (new_status, utc_now(), script_id))
        conn.commit()
    conn.close()
    return redirect(url_for("scripts_admin"))


@app.get("/admin/token")
def token_admin():
    return render_template("token.html", token=get_token())


@app.post("/admin/token")
def update_token():
    new_token = request.form.get("token", "").strip()
    if len(new_token) < 8:
        flash("O token deve ter pelo menos 8 caracteres.", "danger")
    else:
        set_token(new_token)
        flash("Token atualizado com sucesso.", "success")
    return redirect(url_for("token_admin"))


@app.get("/admin/logs")
def logs_admin():
    conn = get_conn()
    logs = conn.execute("SELECT * FROM execution_logs ORDER BY id DESC LIMIT 100").fetchall()
    conn.close()
    return render_template("logs.html", logs=logs)


@app.get("/api/scripts")
def api_list_scripts():
    auth_error = require_api_token()
    if auth_error:
        return auth_error
    conn = get_conn()
    rows = conn.execute(
        "SELECT name, file_name, params_schema, description, active FROM scripts ORDER BY name"
    ).fetchall()
    conn.close()
    return jsonify([row_to_dict(row) for row in rows])


@app.post("/admin/scripts/<int:script_id>/execute")
def execute_script_web(script_id: int):
    conn = get_conn()
    script = conn.execute(
        "SELECT * FROM scripts WHERE id = ?",
        (script_id,)
    ).fetchone()
    conn.close()

    if not script:
        flash("Script não encontrado.", "danger")
        return redirect(url_for("scripts_admin"))

    if not script["active"]:
        flash("Script inativo. Ative o script antes de executar.", "warning")
        return redirect(url_for("scripts_admin"))

    try:
        script_path = safe_script_path(script["file_name"])

        if not script_path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {script_path.name}")

        command = ["/bin/sh", str(script_path)]

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            cwd=str(SCRIPTS_DIR),
            check=False,
        )

        status = "sucesso" if completed.returncode == 0 else "falha"

        log_error = try_save_execution_log(
            script_name=script["name"],
            params_used=[],
            return_code=completed.returncode,
            status=status,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
        stderr = completed.stderr
        if log_error:
            stderr = f"{stderr}\n{log_error}".strip()

        return render_execution_result(
            script=script,
            status=status,
            return_code=completed.returncode,
            stdout=completed.stdout,
            stderr=stderr,
        )

    except Exception as exc:
        stderr = str(exc)
        log_error = try_save_execution_log(
            script_name=script["name"],
            params_used=[],
            return_code=None,
            status="falha",
            stdout="",
            stderr=stderr,
        )
        if log_error:
            stderr = f"{stderr}\n{log_error}".strip()

        return render_execution_result(
            script=script,
            status="falha",
            return_code=None,
            stdout="",
            stderr=stderr,
        )
if __name__ == "__main__":
    init_db()
    seed_scripts()
    app.run(host="0.0.0.0", port=5000, debug=False)
