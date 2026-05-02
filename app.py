"""
杭钢公园游客调查问卷 — Flask 后端
==============================
功能：
  1. 提供问卷页面 (GET /)
  2. 接收问卷提交 (POST /submit)
  3. 管理员查看结果统计 (GET /admin)
  4. 导出 CSV 数据 (GET /export)
  5. 清空数据 (POST /clear)
"""

import csv
import io
import sqlite3
import os
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, Response, flash, session
from functools import wraps

app = Flask(__name__)

# ── Secret key（持久化，避免重启后 flash 签名失效）────────────
SECRET_KEY_FILE = os.path.join(os.path.dirname(__file__), ".secret_key")
if "SECRET_KEY" in os.environ:
    app.secret_key = os.environ["SECRET_KEY"]
elif os.path.exists(SECRET_KEY_FILE):
    with open(SECRET_KEY_FILE) as f:
        app.secret_key = f.read().strip()
else:
    key = os.urandom(16).hex()
    with open(SECRET_KEY_FILE, "w") as f:
        f.write(key)
    app.secret_key = key

# ── 管理员密码 ──────────────────────────────────────────────
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

# ── 数据库路径 ──────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "survey.db")


# ── 数据库初始化 ────────────────────────────────────────────
def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS responses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at  TEXT    DEFAULT (datetime('now', 'localtime')),
            q1          TEXT,
            q2          TEXT,
            q3_1        TEXT,
            q3_2        TEXT,
            q3_3        TEXT,
            q4          TEXT,
            q5          TEXT,
            q6          TEXT,
            q7          TEXT
        )
    """)
    conn.commit()
    conn.close()


init_db()


# ── 管理员登录验证装饰器 ────────────────────────────────────
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


# ── 管理员登录页面 ───────────────────────────────────────────
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin"))
        flash("密码错误")
    return render_template("admin_login.html")


# ── 管理员退出 ───────────────────────────────────────────────
@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("survey"))


# ── 首页：问卷 ─────────────────────────────────────────────
@app.route("/")
def survey():
    return render_template("survey.html")


# ── 提交问卷 ───────────────────────────────────────────────
@app.route("/submit", methods=["POST"])
def submit():
    data = request.form

    # 简单校验：Q1/Q5/Q6 为必填单选
    if not data.get("q1"):
        flash("请回答第 1 题")
        return redirect(url_for("survey"))
    if not data.get("q5"):
        flash("请回答第 5 题")
        return redirect(url_for("survey"))
    if not data.get("q6"):
        flash("请回答第 6 题")
        return redirect(url_for("survey"))

    conn = get_db()
    conn.execute("""
        INSERT INTO responses (q1, q2, q3_1, q3_2, q3_3, q4, q5, q6, q7)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("q1"),
        ",".join(data.getlist("q2")) if data.getlist("q2") else "",
        data.get("q3_1", ""),
        data.get("q3_2", ""),
        data.get("q3_3", ""),
        ",".join(data.getlist("q4")) if data.getlist("q4") else "",
        data.get("q5"),
        data.get("q6"),
        data.get("q7", ""),
    ))
    conn.commit()
    conn.close()

    return redirect(url_for("survey", submitted="ok") + "#thanks")


# ── 管理员后台：统计看板 ────────────────────────────────────
@app.route("/admin")
@admin_required
def admin():
    conn = get_db()
    rows = conn.execute("SELECT * FROM responses ORDER BY created_at DESC").fetchall()
    total = len(rows)
    conn.close()

    # 频率统计（各题的 ABCD 等选项计数）
    def freq(rows, field):
        counts = {}
        for r in rows:
            val = r[field]
            if val:
                # 多选题用逗号分隔
                for v in val.split(","):
                    v = v.strip()
                    counts[v] = counts.get(v, 0) + 1
        # 按 value 字母排序
        return dict(sorted(counts.items()))

    # Likert 评分均值
    def likert_avg(rows, field):
        vals = []
        for r in rows:
            v = r[field]
            if v and v.isdigit():
                vals.append(int(v))
        if not vals:
            return 0
        return round(sum(vals) / len(vals), 2)

    stats = {
        "q1": freq(rows, "q1"),
        "q2": freq(rows, "q2"),
        "q3_1": freq(rows, "q3_1"),
        "q3_2": freq(rows, "q3_2"),
        "q3_3": freq(rows, "q3_3"),
        "q3_1_avg": likert_avg(rows, "q3_1"),
        "q3_2_avg": likert_avg(rows, "q3_2"),
        "q3_3_avg": likert_avg(rows, "q3_3"),
        "q4": freq(rows, "q4"),
        "q5": freq(rows, "q5"),
        "q6": freq(rows, "q6"),
    }
    return render_template("admin.html", rows=rows, total=total, stats=stats)


# ── 导出 CSV ───────────────────────────────────────────────
@app.route("/export")
@admin_required
def export_csv():
    conn = get_db()
    rows = conn.execute("SELECT * FROM responses ORDER BY created_at DESC").fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "编号", "提交时间", "Q1_了解程度", "Q2_来园目的(多选)",
        "Q3.1_两山论", "Q3.2_以人民为中心", "Q3.3_高质量发展",
        "Q4_周边区域变化(多选)", "Q5_幸福感提升", "Q6_推广价值", "Q7_建议"
    ])
    for r in rows:
        writer.writerow([
            r["id"], r["created_at"],
            r["q1"], r["q2"],
            r["q3_1"], r["q3_2"], r["q3_3"],
            r["q4"], r["q5"], r["q6"], r["q7"]
        ])

    content = output.getvalue().encode("utf-8-sig")
    return Response(
        content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=survey_results.csv"}
    )


# ── 清空数据 ───────────────────────────────────────────────
@app.route("/clear", methods=["POST"])
@admin_required
def clear_data():
    conn = get_db()
    conn.execute("DELETE FROM responses")
    conn.commit()
    conn.close()
    flash("数据已清空")
    return redirect(url_for("admin"))


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
    app.run(host="0.0.0.0", port=5000, debug=debug)
