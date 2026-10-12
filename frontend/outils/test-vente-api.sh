#!/usr/bin/env bash
# Creates a real one-bottle sale; use only with an approved test backend.
# Example: CONFIRM_TEST_SALE=YES API_TOKEN=... PRODUCT_ID=123 bash outils/test-vente-api.sh
set -euo pipefail

: "${API_TOKEN:?Define API_TOKEN avec un jeton vendeur/admin}"
: "${PRODUCT_ID:?Define PRODUCT_ID avec un identifiant produit numérique}"
: "${CONFIRM_TEST_SALE:?Set CONFIRM_TEST_SALE=YES pour autoriser une vente de test}"

if [[ "$CONFIRM_TEST_SALE" != "YES" ]]; then
  echo "Vente de test annulée : définir CONFIRM_TEST_SALE=YES après vérification du produit." >&2
  exit 2
fi
if [[ ! "$PRODUCT_ID" =~ ^[1-9][0-9]*$ ]]; then
  echo "PRODUCT_ID doit être un identifiant numérique positif." >&2
  exit 2
fi
if ! command -v curl >/dev/null 2>&1 || ! command -v jq >/dev/null 2>&1; then
  echo "Ce script nécessite curl et jq." >&2
  exit 2
fi

API_BASE="${API_BASE:-http://localhost:8000/api}"
API_BASE="${API_BASE%/}"
payload=$(jq -n --argjson id "$PRODUCT_ID" \
  '{mode_paiement:"ESPECES", lignes:[{produit_id:$id, quantite:1, unite:"BOUTEILLE"}]}')
response=$(curl --fail --silent --show-error \
  -X POST "$API_BASE/ventes/" \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  --data "$payload")
reference=$(jq -er '.data.reference | strings' <<<"$response")

history=$(curl --fail --silent --show-error \
  "$API_BASE/ventes/?search=$reference" \
  -H "Authorization: Bearer $API_TOKEN")
jq -e --arg reference "$reference" \
  '(.results // .data.results // .) as $ventes
   | ($ventes | type == "array")
     and any($ventes[]; .reference == $reference and .statut == "PAYEE")' \
  <<<"$history" >/dev/null

printf 'Vente %s créée et retrouvée dans GET /ventes/ (statut PAYEE).\n' "$reference"
