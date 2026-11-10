#!/usr/bin/env python3
"""
سجل التعديلات — Audit Log Centralisé
Reçoit les logs de toutes les apps et les affiche
Port 5010 — cabinet.mwj-lawyers.com/audit
"""
from flask import Flask, request, jsonify, render_template
import sqlite3, os, json
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'audit-secret-2024')

DB_PATH      = os.environ.get('DB_PATH', '/data/audit.db')
BASE_PATH    = os.environ.get('BASE_PATH', '')
NEXTCLOUD_URL= os.environ.get('NEXTCLOUD_URL', 'http://cabinet.mwj-lawyers.com')

APPS = {
    'fiche-client':     {'label': 'ملف المنوب',       'icon': '👤'},
    'agenda-jalsat':    {'label': 'أجندة الجلسات',    'icon': '📅'},
    'huissiers-app':    {'label': 'قائمة العدول',      'icon': '⚖️'},
    'taches-huissiers': {'label': 'مهام العدول',        'icon': '✅'},
    'archive-app':      {'label': 'الأرشيف',           'icon': '🗄️'},
    'tawer-qadaya':     {'label': 'طور القضايا',       'icon': '📋'},
    'maktaba-qanouniya':{'label': 'المكتبة القانونية', 'icon': '📚'},
}

ACTIONS = {
    'create': {'label': 'إضافة',   'color': '#27ae60'},
    'update': {'label': 'تعديل',   'color': '#e67e22'},
    'delete': {'label': 'حذف',     'color': '#e74c3c'},
    'view':   {'label': 'عرض',     'color': '#3498db'},
    'upload': {'label': 'رفع ملف', 'color': '#9b59b6'},
    'login':  {'label': 'دخول',    'color': '#1abc9c'},
}


# ─── PROTECTION ───────────────────────────────────────────────────────────────
@app.before_request
def require_nextcloud():
    if request.path.startswith(('/api/', '/static/')):
        return  # API ouverte
    if not NEXTCLOUD_URL:
        return
    ref  = request.headers.get('Referer', '')
    dest = request.headers.get('Sec-Fetch-Dest', '')
    site = request.headers.get('Sec-Fetch-Site', '')
    if dest == 'iframe' or site == 'same-origin':
        return
    if ref and (NEXTCLOUD_URL in ref or request.host in ref):
        return
    if any(k.startswith(('nc_', 'oc_')) for k in request.cookies):
        return
    return ('<html><body dir="rtl" style="font-family:Arial;text-align:center;padding:60px">'
            '<h2>🔒 يرجى الدخول عبر Nextcloud</h2></body></html>'), 403

@app.after_request
def add_headers(r):
    if NEXTCLOUD_URL:
        r.headers['Content-Security-Policy'] = f"frame-ancestors 'self' {NEXTCLOUD_URL}"
    return r

@app.context_processor
def inject_globals():
    return {'BASE': BASE_PATH, 'APPS': APPS, 'ACTIONS': ACTIONS}


# ─── DATABASE ─────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            app         TEXT NOT NULL DEFAULT '',
            action      TEXT NOT NULL DEFAULT '',
            entity_type TEXT NOT NULL DEFAULT '',
            entity_id   TEXT NOT NULL DEFAULT '',
            entity_label TEXT NOT NULL DEFAULT '',
            nc_user     TEXT NOT NULL DEFAULT '',
            nc_display  TEXT NOT NULL DEFAULT '',
            details     TEXT NOT NULL DEFAULT '{}',
            ip          TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    # Index pour performance
    conn.execute("CREATE INDEX IF NOT EXISTS idx_app ON logs(app)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_action ON logs(action)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_user ON logs(nc_user)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_date ON logs(created_at)")
    conn.commit()
    conn.close()


# ─── API RÉCEPTION LOGS ──────────────────────────────────────────────────────
@app.route('/api/log', methods=['POST'])
def api_receive_log():
    """Endpoint appelé par toutes les apps pour logger une action."""
    try:
        data = request.get_json(force=True) or {}
        conn = get_db()
        conn.execute("""
            INSERT INTO logs
              (app, action, entity_type, entity_id, entity_label,
               nc_user, nc_display, details, ip, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))
        """, (
            data.get('app', ''),
            data.get('action', ''),
            data.get('entity_type', ''),
            str(data.get('entity_id', '')),
            data.get('entity_label', ''),
            data.get('nc_user', 'inconnu'),
            data.get('nc_display', ''),
            json.dumps(data.get('details', {}), ensure_ascii=False),
            data.get('ip', request.remote_addr or ''),
        ))
        conn.commit()
        conn.close()
        return jsonify({'ok': True}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─── PAGE PRINCIPALE ──────────────────────────────────────────────────────────
@app.route('/')
def index():
    # Filtres
    f_app    = request.args.get('app', '')
    f_action = request.args.get('action', '')
    f_user   = request.args.get('user', '')
    f_date   = request.args.get('date', '')
    f_q      = request.args.get('q', '').strip()
    page     = max(1, int(request.args.get('page', 1)))
    per_page = 50

    conn = get_db()

    # Construire la requête
    where = ["1=1"]
    params = []
    if f_app:    where.append("app=?");          params.append(f_app)
    if f_action: where.append("action=?");       params.append(f_action)
    if f_user:   where.append("nc_user=?");      params.append(f_user)
    if f_date:   where.append("date(created_at)=?"); params.append(f_date)
    if f_q:
        where.append("(entity_label LIKE ? OR nc_display LIKE ? OR details LIKE ?)")
        params += [f'%{f_q}%', f'%{f_q}%', f'%{f_q}%']

    where_sql = ' AND '.join(where)
    total = conn.execute(f"SELECT COUNT(*) FROM logs WHERE {where_sql}", params).fetchone()[0]
    logs  = conn.execute(
        f"SELECT * FROM logs WHERE {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [per_page, (page-1)*per_page]
    ).fetchall()

    # Statistiques
    stats = {
        'total': conn.execute("SELECT COUNT(*) FROM logs").fetchone()[0],
        'today': conn.execute("SELECT COUNT(*) FROM logs WHERE date(created_at)=date('now')").fetchone()[0],
        'users': conn.execute("SELECT COUNT(DISTINCT nc_user) FROM logs WHERE nc_user != ''").fetchone()[0],
    }

    # Listes pour filtres
    users = [r[0] for r in conn.execute(
        "SELECT DISTINCT nc_user FROM logs WHERE nc_user != '' ORDER BY nc_user"
    ).fetchall()]
    conn.close()

    return render_template('index.html',
                           logs=[dict(l) for l in logs],
                           total=total, page=page, per_page=per_page,
                           pages=((total-1)//per_page)+1,
                           stats=stats, users=users,
                           f_app=f_app, f_action=f_action,
                           f_user=f_user, f_date=f_date, f_q=f_q)


@app.route('/api/stats')
def api_stats():
    conn = get_db()
    by_app = dict(conn.execute(
        "SELECT app, COUNT(*) FROM logs GROUP BY app ORDER BY COUNT(*) DESC"
    ).fetchall())
    by_action = dict(conn.execute(
        "SELECT action, COUNT(*) FROM logs GROUP BY action"
    ).fetchall())
    by_day = conn.execute(
        "SELECT date(created_at) as d, COUNT(*) FROM logs GROUP BY d ORDER BY d DESC LIMIT 30"
    ).fetchall()
    conn.close()
    return jsonify({'by_app': by_app, 'by_action': by_action,
                    'by_day': [dict(r) for r in by_day]})


# ─── MAIN ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5010)), debug=False)

init_db()
