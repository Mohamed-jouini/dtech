#!/usr/bin/env python3
"""
auto_patch.py — Patcher automatiquement toutes les apps pour l'audit logging
Exécuter sur le serveur : python3 ~/audit-app/auto_patch.py
"""
import os, re, shutil
from datetime import datetime

HOME = os.path.expanduser('~')
AUDIT_URL = 'http://audit-app:5010/api/log'

def backup(path):
    bak = path + f'.bak.{datetime.now().strftime("%Y%m%d%H%M%S")}'
    shutil.copy2(path, bak)
    return bak

def add_import(code, app_name):
    """Ajouter import audit_client si absent."""
    if 'from audit_client import log_action' in code:
        return code
    insert = (
        f'\n# ─── AUDIT LOGGING ───────────────────────────────────────────────\n'
        f'import os as _os\n'
        f'_os.environ.setdefault("AUDIT_URL", "{AUDIT_URL}")\n'
        f'try:\n'
        f'    from audit_client import log_action as _log\n'
        f'except ImportError:\n'
        f'    def _log(*a, **k): pass\n'
        f'# ─────────────────────────────────────────────────────────────────\n'
    )
    # Insérer après les imports
    lines = code.split('\n')
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith(('import ', 'from ')) or line.strip() == '':
            insert_at = i + 1
        elif insert_at > 0:
            break
    lines.insert(insert_at, insert)
    return '\n'.join(lines)


# ═══════════════════════════════════════════════════════════════════════
# FICHE-CLIENT
# ═══════════════════════════════════════════════════════════════════════
def patch_fiche_client():
    path = os.path.join(HOME, 'fiche-client-app', 'app.py')
    if not os.path.exists(path):
        print(f"⚠️  fiche-client-app/app.py introuvable")
        return False
    bak = backup(path)
    with open(path) as f: code = f.read()
    code = add_import(code, 'fiche-client')

    # Après INSERT dans api_create
    code = code.replace(
        'conn.commit()\n    new_id = cursor.lastrowid\n    conn.close()\n    data[\'id\'] = new_id\n    return jsonify(data), 201',
        'conn.commit()\n    new_id = cursor.lastrowid\n    conn.close()\n    data[\'id\'] = new_id\n'
        '    _log(request, \'fiche-client\', \'create\', \'client\', new_id,\n'
        '         label=data.get(\'client_nom\',\'\'), details={\'raqm_qadiya\': data.get(\'raqm_qadiya\',\'\')})\n'
        '    return jsonify(data), 201'
    )

    # Après UPDATE dans api_update
    code = code.replace(
        '"UPDATE clients SET data = ?, updated_at = ? WHERE id = ?",\n        (json.dumps(data, ensure_ascii=False), now, cid)\n    )\n    conn.commit()\n    conn.close()\n    data[\'id\'] = cid\n    return jsonify(data)',
        '"UPDATE clients SET data = ?, updated_at = ? WHERE id = ?",\n        (json.dumps(data, ensure_ascii=False), now, cid)\n    )\n    conn.commit()\n    conn.close()\n    data[\'id\'] = cid\n'
        '    _log(request, \'fiche-client\', \'update\', \'client\', cid,\n'
        '         label=data.get(\'client_nom\',\'\'), details={\'raqm_qadiya\': data.get(\'raqm_qadiya\',\'\')})\n'
        '    return jsonify(data)'
    )

    # Après DELETE dans api_delete
    code = code.replace(
        '"DELETE FROM clients WHERE id = ?", (cid,))\n    conn.commit()\n    conn.close()\n    return jsonify({\'ok\': True})',
        '"DELETE FROM clients WHERE id = ?", (cid,))\n    conn.commit()\n    conn.close()\n'
        '    _log(request, \'fiche-client\', \'delete\', \'client\', cid)\n'
        '    return jsonify({\'ok\': True})'
    )

    with open(path, 'w') as f: f.write(code)
    print(f"✅ fiche-client patché (backup: {os.path.basename(bak)})")
    return True


# ═══════════════════════════════════════════════════════════════════════
# AGENDA-JALSAT
# ═══════════════════════════════════════════════════════════════════════
def patch_agenda_jalsat():
    path = os.path.join(HOME, 'agenda-jalsat', 'app.py')
    if not os.path.exists(path):
        print(f"⚠️  agenda-jalsat/app.py introuvable")
        return False
    bak = backup(path)
    with open(path) as f: code = f.read()
    code = add_import(code, 'agenda-jalsat')

    # Chercher les routes POST qui créent/modifient/suppriment des jalsat
    # Pattern générique : après conn.commit() dans les routes d'écriture
    # On injecte via une approche regex sur les routes connues

    # Ajouter log après création jalsa (chercher INSERT INTO jalsat)
    code = re.sub(
        r'(conn\.execute\(["\']INSERT INTO jalsat.*?conn\.commit\(\))',
        r'\1\n    _log(request, \'agenda-jalsat\', \'create\', \'jalsa\', cur.lastrowid if hasattr(locals().get(\'cur\',None),\'lastrowid\') else \'\',\n         label=request.form.get(\'mahkama\',\'\')+\' — \'+request.form.get(\'adad_qadiya\',\'\'),\n         details={\'jalsa\': request.form.get(\'jalsa\',\'\')})',
        code, flags=re.DOTALL
    )

    with open(path, 'w') as f: f.write(code)
    print(f"✅ agenda-jalsat patché (backup: {os.path.basename(bak)})")
    return True


# ═══════════════════════════════════════════════════════════════════════
# TAWER-QADAYA
# ═══════════════════════════════════════════════════════════════════════
def patch_tawer_qadaya():
    path = os.path.join(HOME, 'tawer-qadaya', 'app.py')
    if not os.path.exists(path):
        print(f"⚠️  tawer-qadaya/app.py introuvable")
        return False
    bak = backup(path)
    with open(path) as f: code = f.read()
    code = add_import(code, 'tawer-qadaya')

    # Après INSERT (new_qadiya)
    code = code.replace(
        "conn.commit()\n        conn.close()\n        flash('تمت إضافة القضية بنجاح', 'success')\n        return redirect(f\"{BASE_PATH}/?tab={TOURS.get(data[-1],'jariya')}\")",
        "conn.commit()\n        conn.close()\n"
        "        _log(request, 'tawer-qadaya', 'create', 'qadiya', cur.lastrowid,\n"
        "             label=data[0]+' — '+data[1], details={'tawar': data[-1], 'adad': data[1]})\n"
        "        flash('تمت إضافة القضية بنجاح', 'success')\n"
        "        return redirect(f\"{BASE_PATH}/?tab={TOURS.get(data[-1],'jariya')}\")"
    )

    # Après UPDATE (edit_qadiya)
    code = code.replace(
        "conn.commit()\n        conn.close()\n        flash('تم تحديث القضية بنجاح', 'success')\n        return redirect(f\"{BASE_PATH}/?tab={TOURS.get(data[-1],'jariya')}\")",
        "conn.commit()\n        conn.close()\n"
        "        _log(request, 'tawer-qadaya', 'update', 'qadiya', qid,\n"
        "             label=data[0]+' — '+data[1], details={'tawar': data[-1], 'adad': data[1]})\n"
        "        flash('تم تحديث القضية بنجاح', 'success')\n"
        "        return redirect(f\"{BASE_PATH}/?tab={TOURS.get(data[-1],'jariya')}\")"
    )

    # Après DELETE
    code = code.replace(
        "conn.execute(\"DELETE FROM qadaya WHERE id=?\", (qid,))\n    conn.commit()\n    conn.close()\n    flash('تم حذف القضية', 'warning')",
        "conn.execute(\"DELETE FROM qadaya WHERE id=?\", (qid,))\n    conn.commit()\n    conn.close()\n"
        "    _log(request, 'tawer-qadaya', 'delete', 'qadiya', qid)\n"
        "    flash('تم حذف القضية', 'warning')"
    )

    # Après changement طور (api_change_tawar)
    code = code.replace(
        "conn.execute(\n        \"UPDATE qadaya SET tawar=?,updated_at=datetime('now') WHERE id=?\",\n        (tawar, qid)\n    )\n    conn.commit()\n    conn.close()\n    return jsonify({'ok': True, 'tab': TOURS[tawar]})",
        "conn.execute(\n        \"UPDATE qadaya SET tawar=?,updated_at=datetime('now') WHERE id=?\",\n        (tawar, qid)\n    )\n    conn.commit()\n    conn.close()\n"
        "    _log(request, 'tawer-qadaya', 'update', 'qadiya', qid,\n"
        "         label=f'تغيير الطور → {tawar}', details={'tawar': tawar})\n"
        "    return jsonify({'ok': True, 'tab': TOURS[tawar]})"
    )

    with open(path, 'w') as f: f.write(code)
    print(f"✅ tawer-qadaya patché (backup: {os.path.basename(bak)})")
    return True


# ═══════════════════════════════════════════════════════════════════════
# DOCKER-COMPOSE — ajouter AUDIT_URL dans chaque app
# ═══════════════════════════════════════════════════════════════════════
def patch_compose(app_dir, container_name):
    path = os.path.join(HOME, app_dir, 'docker-compose.yml')
    if not os.path.exists(path):
        return
    with open(path) as f: code = f.read()
    if 'AUDIT_URL' in code:
        return
    # Ajouter AUDIT_URL dans la section environment
    code = code.replace(
        '      - PORT=',
        f'      - AUDIT_URL={AUDIT_URL}\n      - PORT='
    )
    with open(path, 'w') as f: f.write(code)
    print(f"  ✅ AUDIT_URL ajouté dans {app_dir}/docker-compose.yml")


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print("═" * 50)
    print("  📋 Auto-patch Audit Logging")
    print("═" * 50)

    # Copier audit_client.py dans toutes les apps
    client_src = os.path.join(HOME, 'audit-app', 'audit_client.py')
    for d in ['fiche-client-app', 'agenda-jalsat', 'huissiers-app',
              'taches-huissiers', 'archive-app', 'tawer-qadaya', 'maktaba-qanouniya']:
        dst = os.path.join(HOME, d, 'audit_client.py')
        if os.path.exists(os.path.join(HOME, d)) and os.path.exists(client_src):
            shutil.copy2(client_src, dst)
            print(f"  📋 audit_client.py → {d}/")

    print()

    # Patcher les app.py
    patch_fiche_client()
    patch_tawer_qadaya()
    patch_agenda_jalsat()

    print()

    # Patcher les docker-compose.yml
    for app_dir in ['fiche-client-app', 'agenda-jalsat', 'huissiers-app',
                    'taches-huissiers', 'archive-app', 'tawer-qadaya', 'maktaba-qanouniya']:
        patch_compose(app_dir, app_dir)

    print()
    print("─" * 50)
    print("📦 Redémarre les apps patchées :")
    print()
    for d in ['fiche-client-app', 'tawer-qadaya', 'agenda-jalsat']:
        print(f"  cd ~/{d} && docker compose up -d --build")
    print()
    print("✅ Terminé.")
    print("═" * 50)
