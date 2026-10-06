#!/bin/bash
# Chaîne complète, exécutée chaque semaine sur le serveur (crontab de l'utilisateur ubuntu) :
#   10 4 * * 1 bash /home/ubuntu/nexo-data-pipeline/scripts/chaine_hebdomadaire.sh
# extraction → agrégation → import → tri RGPD. Chaque étape ne s'exécute que si la précédente
# a réussi ; le journal de la semaine est écrit dans data/journaux/.
set -uo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/journaux
JOURNAL="data/journaux/chaine-$(date -u +%Y%m%dT%H%M%SZ).log"
lancer() {
  docker compose -f docker-compose.yml -f docker-compose.serveur.yml --profile pipeline \
    run --rm -T pipeline python -m "$@" >> "$JOURNAL" 2>&1
}
for etape in referentiel.extraire referentiel.agreger referentiel.importer referentiel.purger; do
  if ! lancer "$etape"; then
    echo "$(date -u +%FT%TZ) ECHEC $etape" >> "$JOURNAL"
    exit 1
  fi
  echo "$(date -u +%FT%TZ) OK $etape" >> "$JOURNAL"
done
# Les journaux de la chaîne suivent la même durée de conservation que les fichiers (30 jours).
find data/journaux -name 'chaine-*.log' -mtime +30 -delete
