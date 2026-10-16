/**
 * Audit de parité i18n — fr / mg / en.
 *
 * Compare les clés (imbriquées) des fichiers de traduction et affiche les
 * clés manquantes ou présentes uniquement dans certaines langues.
 *
 * Usage : node outils/verifier-i18n.mjs   (sortie : code retour 1 si écart)
 */
import { readdirSync, readFileSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const RACINE = resolve(dirname(fileURLToPath(import.meta.url)), '../src/assets/i18n');
const dossiers = readdirSync(RACINE).filter((f) => f.endsWith('.json'));
if (dossiers.length < 2) {
  console.error('Fichiers de traduction introuvables dans', RACINE);
  process.exit(2);
}

const aplatir = (obj, prefixe = '', sortie = new Map()) => {
  for (const [cle, valeur] of Object.entries(obj)) {
    const chemin = prefixe ? `${prefixe}.${cle}` : cle;
    if (valeur && typeof valeur === 'object' && !Array.isArray(valeur)) aplatir(valeur, chemin, sortie);
    else sortie.set(chemin, typeof valeur);
  }
  return sortie;
};

const parLangue = new Map();
for (const fichier of dossiers) {
  const langue = fichier.replace(/\.json$/, '');
  parLangue.set(langue, aplatir(JSON.parse(readFileSync(join(RACINE, fichier), 'utf8'))));
}

const toutes = [...new Set([...parLangue.values()].flatMap((m) => [...m.keys()]))].sort();
const ref = [...parLangue.keys()].sort()[0];
let totalManquantes = 0;

for (const [langue, cartes] of parLangue) {
  const manquantes = toutes.filter((k) => !cartes.has(k));
  const types = toutes.filter((k) => cartes.has(k) && parLangue.get(ref)?.has(k) && cartes.get(k) !== parLangue.get(ref).get(k));
  console.log(`${langue}: ${cartes.size} clés — manquantes: ${manquantes.length}${types.length ? ` — types différents (vs ${ref}): ${types.length}` : ''}`);
  for (const k of manquantes) console.log(`   ✗ ${k}`);
  for (const k of types) console.log(`   ⚠ type ${k}: ${cartes.get(k)} ≠ ${ref}:${parLangue.get(ref).get(k)}`);
  totalManquantes += manquantes.length + types.length;
}

console.log(`\nTotal clés distinctes: ${toutes.length} — écarts: ${totalManquantes}`);
process.exit(totalManquantes ? 1 : 0);
