import os
import re
import subprocess
from flask import Flask, request, jsonify

ROOT = "/docs/n8n-docs"
app = Flask(__name__)

def safe_path(p: str) -> str:
    p = (p or "").strip()
    if not p.startswith(ROOT + "/"):
        raise ValueError("path must start with /docs/n8n-docs/")
    if ".." in p:
        raise ValueError("path traversal blocked")
    return p

def strip_html(s: str) -> str:
    s = re.sub(r"(?is)<script.*?>.*?</script>", " ", s)
    s = re.sub(r"(?is)<style.*?>.*?</style>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

@app.get("/health")
def health():
    return jsonify({"ok": True})

@app.get("/search")
def search():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"query": q, "results": []})

    # Быстрый поиск через ripgrep (гораздо быстрее, чем читать все файлы python-ом)
    # Ограничим выдачу, чтобы инструмент был детерминированным.
    cmd = [
        "rg", "-n", "--no-heading", "--smart-case",
        "--glob", "*.md", "--glob", "*.html", "--glob", "*.txt",
        "-m", "1", q, ROOT
    ]

    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
    except Exception as e:
        return jsonify({"query": q, "results": [], "error": str(e)}), 500

    if p.returncode not in (0, 1):  # 1 = not found
        return jsonify({"query": q, "results": [], "error": p.stderr[-400:]}), 500

    results = []
    for line in p.stdout.splitlines()[:8]:
        # формат rg: path:line:content
        parts = line.split(":", 2)
        if len(parts) != 3:
            continue
        path, lineno, content = parts
        results.append({"path": path, "line": int(lineno), "snippet": content.strip()})

    return jsonify({"query": q, "results": results})

@app.get("/open")
def open_file():
    try:
        p = safe_path(request.args.get("path") or "")
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    with open(p, "r", encoding="utf-8", errors="ignore") as f:
        data = f.read()

    if p.lower().endswith(".html"):
        data = strip_html(data)

    return jsonify({"path": p, "content": data[:14000]})

