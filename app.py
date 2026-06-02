from flask import Flask, render_template, request, redirect, url_for, flash
from pathlib import Path
import os
from datetime import datetime, timezone
import sqlite3
import paramiko

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("ISYONE_DB_PATH", BASE_DIR / "isyone.db"))
SCRIPTS_DIR = Path(os.getenv("ISYONE_SCRIPTS_DIR", BASE_DIR / "scripts"))

app = Flask(__name__)
app.secret_key = "troque-esta-chave-em-producao"

ALLOWED_TASKS = {
    "check_docker": {
        "label": "Verificar Docker",
        "command": "docker ps --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}'",
        "script": "check_docker.sh",
    },
    "check_disk": {
        "label": "Verificar Disco",
        "command": "df -h",
        "script": "check_disk.sh",
    },
    "check_memory": {
        "label": "Verificar Memória",
        "command": "free -h",
        "script": "check_memory.sh",
    },
    "check_agent_status": {
        "label": "Status do Agente Isy.One",
        "command": "systemctl status isy-agent --no-pager || docker ps | grep -i isy || true",
        "script": "check_agent_status.sh",
    },
    "clean_old_coupon_logs": {
        "label": "Limpar Logs Antigos",
        "command": "find /var/log/isyone/coupons -type f -mtime +30 -name '*.log' -delete && echo 'Logs antigos removidos.'",
        "script": "clean_old_coupon_logs.sh",
    },
    "restart_docker_containers": {
        "label": "Reiniciar Containers Docker",
        "command": "docker compose restart || docker restart $(docker ps -q)",
        "script": "restart_docker_containers.sh",
    },
}


def now_utc_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            host TEXT NOT NULL,
            port INTEGER NOT NULL DEFAULT 22,
            username TEXT NOT NULL,
            password TEXT,
            private_key_path TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS task_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id INTEGER NOT NULL,
            task TEXT NOT NULL,
            success INTEGER NOT NULL,
            output TEXT,
            error TEXT,
            executed_at TEXT NOT NULL,
            FOREIGN KEY(server_id) REFERENCES servers(id)
        )
        """
    )
    conn.commit()
    conn.close()


def get_server(server_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM servers WHERE id = ?", (server_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def read_script_for_task(task_key):
    script_name = ALLOWED_TASKS[task_key].get("script")
    if not script_name:
        return None

    script_path = (SCRIPTS_DIR / script_name).resolve()
    scripts_root = SCRIPTS_DIR.resolve()

    # Evita path traversal e só permite scripts dentro do diretório montado.
    if scripts_root not in script_path.parents and script_path != scripts_root:
        raise ValueError("Caminho de script inválido.")

    if not script_path.exists():
        return None

    return script_path.read_text(encoding="utf-8")


def run_ssh_script(server, script_content):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        connect_args = {
            "hostname": server["host"],
            "port": int(server["port"]),
            "username": server["username"],
            "timeout": 15,
        }
        if server.get("private_key_path"):
            connect_args["key_filename"] = server["private_key_path"]
        else:
            connect_args["password"] = server.get("password")

        client.connect(**connect_args)
        stdin, stdout, stderr = client.exec_command("bash -s", timeout=120)
        stdin.write(script_content)
        stdin.channel.shutdown_write()
        output = stdout.read().decode("utf-8", errors="replace")
        error = stderr.read().decode("utf-8", errors="replace")
        exit_status = stdout.channel.recv_exit_status()
        return exit_status == 0, output, error
    finally:
        client.close()


def run_ssh_command(server, command):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        connect_args = {
            "hostname": server["host"],
            "port": int(server["port"]),
            "username": server["username"],
            "timeout": 15,
        }
        if server.get("private_key_path"):
            connect_args["key_filename"] = server["private_key_path"]
        else:
            connect_args["password"] = server.get("password")

        client.connect(**connect_args)
        stdin, stdout, stderr = client.exec_command(command, timeout=60)
        output = stdout.read().decode("utf-8", errors="replace")
        error = stderr.read().decode("utf-8", errors="replace")
        exit_status = stdout.channel.recv_exit_status()
        return exit_status == 0, output, error
    finally:
        client.close()


def save_history(server_id, task, success, output, error):
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO task_history (server_id, task, success, output, error, executed_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (server_id, task, int(success), output, error, now_utc_iso()),
    )
    conn.commit()
    conn.close()


@app.route("/")
def dashboard():
    conn = get_conn()
    total_servers = conn.execute("SELECT COUNT(*) AS total FROM servers").fetchone()["total"]
    total_tasks = conn.execute("SELECT COUNT(*) AS total FROM task_history").fetchone()["total"]
    total_success = conn.execute("SELECT COUNT(*) AS total FROM task_history WHERE success = 1").fetchone()["total"]
    total_errors = conn.execute("SELECT COUNT(*) AS total FROM task_history WHERE success = 0").fetchone()["total"]
    latest = conn.execute(
        """
        SELECT h.id, h.task, h.success, h.output, h.error, h.executed_at, s.name AS server_name, s.host
        FROM task_history h
        JOIN servers s ON s.id = h.server_id
        ORDER BY h.id DESC
        LIMIT 5
        """
    ).fetchall()
    servers = conn.execute("SELECT * FROM servers ORDER BY id DESC LIMIT 5").fetchall()
    conn.close()
    return render_template(
        "dashboard.html",
        total_servers=total_servers,
        total_tasks=total_tasks,
        total_success=total_success,
        total_errors=total_errors,
        latest=latest,
        servers=servers,
        tasks=ALLOWED_TASKS,
    )


@app.route("/servers")
def servers():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM servers ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("servers.html", servers=rows)


@app.route("/servers/new", methods=["GET", "POST"])
def new_server():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        host = request.form.get("host", "").strip()
        port = request.form.get("port", "22").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        private_key_path = request.form.get("private_key_path", "").strip()

        if not name or not host or not username:
            flash("Preencha nome, host/IP e usuário SSH.", "danger")
            return redirect(url_for("new_server"))

        conn = get_conn()
        conn.execute(
            """
            INSERT INTO servers (name, host, port, username, password, private_key_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (name, host, int(port or 22), username, password, private_key_path or None, now_utc_iso()),
        )
        conn.commit()
        conn.close()
        flash("Servidor cadastrado com sucesso.", "success")
        return redirect(url_for("servers"))

    return render_template("server_form.html")


@app.route("/tasks")
def tasks_page():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM servers ORDER BY name ASC").fetchall()
    conn.close()
    return render_template("tasks.html", servers=rows, tasks=ALLOWED_TASKS)


@app.route("/tasks/run", methods=["POST"])
def run_task():
    server_id = request.form.get("server_id")
    task = request.form.get("task")

    if task not in ALLOWED_TASKS:
        flash("Tarefa inválida.", "danger")
        return redirect(url_for("tasks_page"))

    server = get_server(server_id)
    if not server:
        flash("Servidor não encontrado.", "danger")
        return redirect(url_for("tasks_page"))

    command = ALLOWED_TASKS[task]["command"]
    try:
        script_content = read_script_for_task(task)
        if script_content:
            success, output, error = run_ssh_script(server, script_content)
        else:
            success, output, error = run_ssh_command(server, command)
    except Exception as exc:
        success = False
        output = ""
        error = str(exc)

    save_history(server_id, task, success, output, error)
    return render_template(
        "task_result.html",
        server=server,
        task_key=task,
        task=ALLOWED_TASKS[task],
        success=success,
        output=output,
        error=error,
    )


@app.route("/history")
def history():
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT h.id, h.task, h.success, h.output, h.error, h.executed_at, s.name AS server_name, s.host
        FROM task_history h
        JOIN servers s ON s.id = h.server_id
        ORDER BY h.id DESC
        LIMIT 100
        """
    ).fetchall()
    conn.close()
    return render_template("history.html", history=rows, tasks=ALLOWED_TASKS)


init_db()

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
