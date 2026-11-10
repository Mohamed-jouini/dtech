#!/usr/bin/env python3
"""
Script de synchronisation agenda-jalsat → tawer-qadaya
Cron : toutes les 5 minutes
"""
import sqlite3
import json
import os
from datetime import datetime

JALSAT_DB = os.environ.get('JALSAT_DB', '/var/lib/docker/volumes/agenda-jalsat_jalsat-data/_data/jalsat.db')
TAWER_DB  = os.environ.get('TAWER_DB',  '/var/lib/docker/volumes/tawer-qadaya_tawer-data/_data/qadaya.db')

TAWER_MAP = {
    'جارية':        'جارية',
    'تصريح':        'تصريح بالحكم',
    'تصريح بالحكم': 'تصريح بالحكم',
    'محكوم فيها':   'محكوم فيها',
}

def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def sync():
    if not os.path.exists(JALSAT_DB):
        log(f"❌ JALSAT_DB introuvable: {JALSAT_DB}")
        return
    if not os.path.exists(TAWER_DB):
        log(f"❌ TAWER_DB introuvable: {TAWER_DB}")
        return

    jconn = sqlite3.connect(JALSAT_DB)
    jconn.row_factory = sqlite3.Row

    # Récupérer le dernier طور pour chaque عدد القضية
    rows = jconn.execute("""
        SELECT adad_qadiya,
               mahkama, daira, manoub, mustafid, ded, jalsa, gharad,
               tawer
        FROM jalsat
        WHERE adad_qadiya != ''
          AND tawer != ''
          AND jalsa = (
              SELECT MAX(j2.jalsa) FROM jalsat j2
              WHERE j2.adad_qadiya = jalsat.adad_qadiya
                AND j2.tawer != ''
          )
        GROUP BY adad_qadiya
    """).fetchall()
    jconn.close()

    if not rows:
        log("Aucune affaire à synchroniser")
        return

    tconn = sqlite3.connect(TAWER_DB)
    tconn.row_factory = sqlite3.Row
    now = datetime.now().isoformat()

    updated = 0
    inserted = 0

    for r in rows:
        adad   = r['adad_qadiya']
        tawer  = r['tawer']

        if tawer not in TAWER_MAP:
            continue

        tawar_tawer = TAWER_MAP[tawer]

        manoub    = r['manoub'] or ''
        mustafid  = r['mustafid'] or ''
        ded       = r['ded'] or ''
        mandubeen = json.dumps([{'nom': manoub, 'sifa': ''}, {'nom': mustafid, 'sifa': ''}] if mustafid else [{'nom': manoub, 'sifa': ''}], ensure_ascii=False)
        addad_json= json.dumps([{'nom': ded, 'sifa': ''}], ensure_ascii=False) if ded else '[]'

        existing = tconn.execute("SELECT id, tawar FROM qadaya WHERE adad=?", (adad,)).fetchone()

        if existing:
            if existing['tawar'] != tawar_tawer:
                tconn.execute("""
                    UPDATE qadaya SET mahkama=?, daira=?, mandubeen=?, addad=?,
                        tarikh=?, gharad=?, tawar=?, updated_at=datetime('now')
                    WHERE id=?
                """, (r['mahkama'] or '', r['daira'] or '', mandubeen, addad_json,
                      r['jalsa'] or '', r['gharad'] or '', tawar_tawer, existing['id']))
                log(f"🔄 {adad} : {existing['tawar']} → {tawar_tawer}")
                updated += 1
        else:
            tconn.execute("""
                INSERT INTO qadaya (mahkama, adad, daira, mandubeen, addad,
                    tarikh, mawdu3, gharad, mulahazat, tawar)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (r['mahkama'] or '', adad, r['daira'] or '', mandubeen, addad_json,
                  r['jalsa'] or '', '', r['gharad'] or '', '', tawar_tawer))
            log(f"✅ {adad} : inséré ({tawar_tawer})")
            inserted += 1

    tconn.commit()
    tconn.close()
    log(f"Terminé — {updated} mis à jour, {inserted} insérés")

if __name__ == '__main__':
    log("Démarrage sync agenda → tawer")
    sync()
