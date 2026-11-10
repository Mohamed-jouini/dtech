#!/bin/bash
# Ajouter AUDIT_URL dans tous les docker-compose.yml
APPS=(fiche-client-app tawer-qadaya agenda-jalsat huissiers-app taches-huissiers archive-app maktaba-qanouniya)
for app in "${APPS[@]}"; do
  dc="$HOME/$app/docker-compose.yml"
  [ -f "$dc" ] || continue
  if grep -q "AUDIT_URL" "$dc"; then
    echo "✅ $app — déjà présent"
  else
    sed -i '/environment:/a\      - AUDIT_URL=http://audit-app:5010/api/log' "$dc"
    echo "✅ $app — AUDIT_URL ajouté"
  fi
done
echo ""
echo "Rebuilder toutes les apps:"
for app in "${APPS[@]}"; do
  echo "  cd ~/$app && docker compose up -d --build"
done
