#!/usr/bin/env python3
"""Patch audit logging pour huissiers-app, taches-huissiers, archive-app + fix tawer-qadaya"""
import os, shutil
from datetime import datetime

HOME = os.path.expanduser('~')

AUDIT_IMPORT = '''
# ─── AUDIT LOGGING ───────────────────────────────────────────────
import os as _os
_os.environ.setdefault("AUDIT_URL", "http://audit-app:5010/api/log")
try:
    from audit_client import log_action as _log
except ImportError:
    def _log(*a, **k): pass
# ─────────────────────────────────────────────────────────────────
'''

def backup(path):
    bak = path + f'.bak.{datetime.now().strftime("%Y%m%d%H%M%S")}'
    shutil.copy2(path, bak)
    return bak

def add_import(code):
    if 'from audit_client import log_action' in code:
        return code
    lines = code.split('\n')
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith(('import ', 'from ')):
            insert_at = i + 1
        elif insert_at > 0 and not line.startswith(('import ', 'from ', '#', '')):
            break
    lines.insert(insert_at, AUDIT_IMPORT)
    return '\n'.join(lines)

# ── HUISSIERS-APP ────────────────────────────────────────────────
def patch_huissiers():
    path = os.path.join(HOME, 'huissiers-app', 'app.py')
    if not os.path.exists(path): return print("⚠️  huissiers-app introuvable")
    backup(path)
    with open(path) as f: c = f.read()
    c = add_import(c)
    # CREATE
    c = c.replace(
        "    new_id = cursor.lastrowid\n    conn.close()\n    data['id'] = new_id\n    return jsonify(data), 201",
        "    new_id = cursor.lastrowid\n    conn.close()\n    data['id'] = new_id\n"
        "    _log(request,'huissiers-app','create','huissier',new_id,\n"
        "         label=data.get('nom',''),details={'nom':data.get('nom','')})\n"
        "    return jsonify(data), 201"
    )
    # UPDATE
    c = c.replace(
        "    conn.commit()\n    conn.close()\n    return jsonify(data)\n\n\n@app.route('/api/huissiers/<int:hid>', methods=['DELETE'])",
        "    conn.commit()\n    conn.close()\n"
        "    _log(request,'huissiers-app','update','huissier',hid,\n"
        "         label=data.get('nom',''))\n"
        "    return jsonify(data)\n\n\n@app.route('/api/huissiers/<int:hid>', methods=['DELETE'])"
    )
    # DELETE
    c = c.replace(
        "    conn.commit()\n    conn.close()\n    return jsonify({'ok': True})",
        "    conn.commit()\n    conn.close()\n"
        "    _log(request,'huissiers-app','delete','huissier',hid)\n"
        "    return jsonify({'ok': True})"
    )
    with open(path, 'w') as f: f.write(c)
    print("✅ huissiers-app patché")

# ── TACHES-HUISSIERS ─────────────────────────────────────────────
def patch_taches():
    path = os.path.join(HOME, 'taches-huissiers', 'app.py')
    if not os.path.exists(path): return print("⚠️  taches-huissiers introuvable")
    backup(path)
    with open(path) as f: c = f.read()
    c = add_import(c)
    # CREATE
    c = c.replace(
        "    new_id = cursor.lastrowid\n    conn.close()\n    data['id'] = new_id\n    return jsonify(data), 201",
        "    new_id = cursor.lastrowid\n    conn.close()\n    data['id'] = new_id\n"
        "    _log(request,'taches-huissiers','create','tache',new_id,\n"
        "         label=data.get('titre',''),details={'titre':data.get('titre','')})\n"
        "    return jsonify(data), 201"
    )
    # UPDATE
    c = c.replace(
        "    conn.commit()\n    conn.close()\n    return jsonify(data)\n\n\n@app.route('/api/taches/<int:tid>', methods=['DELETE'])",
        "    conn.commit()\n    conn.close()\n"
        "    _log(request,'taches-huissiers','update','tache',tid,\n"
        "         label=data.get('titre',''))\n"
        "    return jsonify(data)\n\n\n@app.route('/api/taches/<int:tid>', methods=['DELETE'])"
    )
    # DELETE
    c = c.replace(
        "    conn.commit()\n    conn.close()\n    return jsonify({'deleted': True})",
        "    conn.commit()\n    conn.close()\n"
        "    _log(request,'taches-huissiers','delete','tache',tid)\n"
        "    return jsonify({'deleted': True})"
    )
    with open(path, 'w') as f: f.write(c)
    print("✅ taches-huissiers patché")

# ── ARCHIVE-APP ──────────────────────────────────────────────────
def patch_archive():
    path = os.path.join(HOME, 'archive-app', 'app.py')
    if not os.path.exists(path): return print("⚠️  archive-app introuvable")
    backup(path)
    with open(path) as f: c = f.read()
    c = add_import(c)
    # CREATE
    c = c.replace(
        "    new_id = cursor.lastrowid\n    conn.close()\n    data['id'] = new_id\n    return jsonify(data), 201",
        "    new_id = cursor.lastrowid\n    conn.close()\n    data['id'] = new_id\n"
        "    _log(request,'archive-app','create','dossier',new_id,\n"
        "         label=data.get('titre',''),details={'titre':data.get('titre','')})\n"
        "    return jsonify(data), 201"
    )
    # UPDATE
    c = c.replace(
        "    conn.commit()\n    conn.close()\n    return jsonify(data)\n\n\n@app.route('/api/archive/<int:did>', methods=['DELETE'])",
        "    conn.commit()\n    conn.close()\n"
        "    _log(request,'archive-app','update','dossier',did,\n"
        "         label=data.get('titre',''))\n"
        "    return jsonify(data)\n\n\n@app.route('/api/archive/<int:did>', methods=['DELETE'])"
    )
    # DELETE
    c = c.replace(
        "    conn.commit()\n    conn.close()\n    return jsonify({'ok': True})",
        "    conn.commit()\n    conn.close()\n"
        "    _log(request,'archive-app','delete','dossier',did)\n"
        "    return jsonify({'ok': True})"
    )
    with open(path, 'w') as f: f.write(c)
    print("✅ archive-app patché")

# ── TAWER-QADAYA (fix) ───────────────────────────────────────────
def fix_tawer():
    path = os.path.join(HOME, 'tawer-qadaya', 'app.py')
    if not os.path.exists(path): return print("⚠️  tawer-qadaya introuvable")
    with open(path) as f: c = f.read()
    # Vérifier si déjà patché correctement
    if '_log(request' in c:
        print("✅ tawer-qadaya — appels _log présents")
        # Juste s'assurer que l'import est correct
        if 'from audit_client import log_action' not in c:
            c = add_import(c)
            with open(path, 'w') as f: f.write(c)
    else:
        backup(path)
        c = add_import(c)
        # CREATE
        c = c.replace(
            "        conn.commit()\n        conn.close()\n        flash('تمت إضافة القضية بنجاح'",
            "        conn.commit()\n        new_id = cur.lastrowid if 'cur' in dir() else ''\n        conn.close()\n"
            "        _log(request,'tawer-qadaya','create','qadiya',new_id,\n"
            "             label=(data[0]+' — '+data[1]) if len(data)>1 else '',details={'tawar':data[-1] if data else ''})\n"
            "        flash('تمت إضافة القضية بنجاح'"
        )
        with open(path, 'w') as f: f.write(c)
        print("✅ tawer-qadaya repatché")

if __name__ == '__main__':
    print("═"*50)
    print("  📋 Patch apps restantes")
    print("═"*50)
    patch_huissiers()
    patch_taches()
    patch_archive()
    fix_tawer()
    print()
    print("Rebuilder:")
    for app in ['huissiers-app','taches-huissiers','archive-app','tawer-qadaya']:
        print(f"  cd ~/{app} && docker compose up -d --build")
    print("═"*50)
