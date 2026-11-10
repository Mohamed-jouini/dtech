#!/bin/bash
# patch_apps.sh — Ajouter audit logging dans toutes les apps
# Exécuter depuis le serveur : bash patch_apps.sh

AUDIT_URL="http://localhost:5010/api/log"
APPS=(
  "fiche-client-app:fiche-client"
  "agenda-jalsat:agenda-jalsat"
  "huissiers-app:huissiers-app"
  "taches-huissiers:taches-huissiers"
  "archive-app:archive-app"
  "tawer-qadaya:tawer-qadaya"
  "maktaba-qanouniya:maktaba-qanouniya"
)

echo "═══════════════════════════════════════════"
echo "  📋 Patch Audit Logging — سجل التعديلات"
echo "═══════════════════════════════════════════"

# Copier audit_client.py dans chaque app
for entry in "${APPS[@]}"; do
  dir="${entry%%:*}"
  if [ -d "$HOME/$dir" ]; then
    cp ~/audit-app/audit_client.py "$HOME/$dir/audit_client.py"
    echo "✅ audit_client.py copié dans $dir"
  else
    echo "⚠️  Répertoire $HOME/$dir introuvable"
  fi
done

echo ""
echo "📋 INSTRUCTIONS pour chaque app.py :"
echo ""
echo "1. Ajouter en haut du fichier :"
echo "   from audit_client import log_action"
echo "   import os"
echo "   os.environ.setdefault('AUDIT_URL', 'http://localhost:5010/api/log')"
echo ""
echo "2. Dans chaque route POST/DELETE, ajouter APRÈS l'opération DB :"
echo ""
echo "   ── fiche-client (api_create) ──"
echo "   log_action(request, 'fiche-client', 'create', 'client', new_id,"
echo "              label=data.get('client_nom',''), details={'nom': data.get('client_nom')})"
echo ""
echo "   ── fiche-client (api_update) ──"
echo "   log_action(request, 'fiche-client', 'update', 'client', cid,"
echo "              label=data.get('client_nom',''))"
echo ""
echo "   ── fiche-client (api_delete) ──"
echo "   log_action(request, 'fiche-client', 'delete', 'client', cid)"
echo ""
echo "   ── agenda-jalsat (créer jalsa) ──"
echo "   log_action(request, 'agenda-jalsat', 'create', 'jalsa', new_id,"
echo "              label=f\"{mahkama} — {adad_qadiya}\","
echo "              details={'jalsa': jalsa, 'mahkama': mahkama})"
echo ""
echo "3. Redémarrer chaque app :"
echo "   cd ~/fiche-client-app && docker compose restart"
echo "   cd ~/agenda-jalsat && docker compose restart"
echo "   etc."

echo ""
echo "═══════════════════════════════════════════"
echo "✅ Prêt. Modifie les app.py et relance."
echo "═══════════════════════════════════════════"
