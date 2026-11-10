#!/bin/bash
# Ajouter "COPY audit_client.py ." dans tous les Dockerfiles

APPS=(
  "fiche-client-app"
  "agenda-jalsat"
  "huissiers-app"
  "taches-huissiers"
  "archive-app"
  "tawer-qadaya"
  "maktaba-qanouniya"
)

for app in "${APPS[@]}"; do
  dockerfile="$HOME/$app/Dockerfile"
  if [ ! -f "$dockerfile" ]; then
    echo "⚠️  $app/Dockerfile introuvable"
    continue
  fi
  if grep -q "audit_client.py" "$dockerfile"; then
    echo "✅ $app — déjà patché"
    continue
  fi
  # Ajouter après "COPY app.py ."
  sed -i 's/^COPY app\.py \./COPY app.py .\nCOPY audit_client.py ./' "$dockerfile"
  echo "✅ $app/Dockerfile patché"
done

echo ""
echo "Rebuilder toutes les apps :"
echo ""
for app in "${APPS[@]}"; do
  echo "cd ~/$app && docker compose build --no-cache && docker compose up -d"
done
