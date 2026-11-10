#!/bin/bash
# Mise a jour de /home/dtech avec maj-dtech.tar.gz (28 fichiers : gabarits mobile + corrections).
# Usage (sur le serveur) :  cd /home/dtech && bash deploy_serveur.sh
set -e
cd /home/dtech

APPS="agenda-jalsat archive-app audit-app clients-perso facturation-app fiche-client-app huissiers-app maktaba-qanouniya shakayat taches-huissiers tasks-app tawer-qadaya"

[ -f maj-dtech.tar.gz ] || { echo "maj-dtech.tar.gz introuvable dans /home/dtech"; exit 1; }

# 1) Sauvegarde du code actuel (les donnees sont dans les volumes Docker : non touchees)
SAUV="backup-avant-maj-$(date +%F_%H%M).tar.gz"
tar czf "$SAUV" --exclude='*.db' $APPS
echo "Sauvegarde : $SAUV"

# 2) Extraction : ecrase uniquement les 28 fichiers de l'archive
tar xzf maj-dtech.tar.gz
echo "Fichiers mis a jour :"; tar tzf maj-dtech.tar.gz

# 3) Reconstruction des conteneurs (le Dockerfile fait COPY . . donc rebuild obligatoire)
for a in $APPS; do
  echo "=== $a ==="
  (cd "$a" && docker compose up -d --build)
done

echo; docker ps --format 'table {{.Names}}\t{{.Status}}' | grep -E 'agenda|archive|audit|clients|factur|fiche|huissiers|maktaba|shakayat|tasks|tawer'
