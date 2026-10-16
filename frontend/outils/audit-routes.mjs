/**
 * Audit navigateur automatisé - Lazan'i Betsileo
 *
 * Parcourt chaque route, collecte :
 *   - les erreurs et avertissements de la console ;
 *   - les requêtes réseau en échec (404, 500…) ;
 *   - les exceptions JavaScript non interceptées ;
 *   - un indicateur « contenu vide » (page rendue mais sans texte utile).
 *
 * Lancement :  node outils/audit-routes.mjs [urlBase]
 * Sortie    :  rapport console + captures dans outils/captures/
 */
import puppeteer from 'puppeteer-core';
import { existsSync, readdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ICI = dirname(fileURLToPath(import.meta.url));
const BASE = process.argv[2] ?? 'http://localhost:4200';
const DOSSIER = resolve(ICI, 'captures');
mkdirSync(DOSSIER, { recursive: true });

/** Routes à auditer. `connexion` = il faut se connecter avant (rôle admin).
 *  `anonyme` = on purge le stockage pour vérifier le rendu déconnecté. */
const ROUTES = [
  { chemin: '/', nom: 'accueil' },
  { chemin: '/catalogue', nom: 'catalogue' },
  { chemin: '/scanner', nom: 'scanner' },
  { chemin: '/promotions', nom: 'promotions' },
  { chemin: '/promotions/roue', nom: 'roue' },
  { chemin: '/promotions/carte-a-gratter', nom: 'carte-gratter' },
  { chemin: '/panier', nom: 'panier' },
  { chemin: '/favoris', nom: 'favoris' },
  { chemin: '/vin/v-001', nom: 'fiche-vin' },
  { chemin: '/commande', nom: 'commande', connexion: true },
  { chemin: '/historique', nom: 'historique', connexion: true },
  { chemin: '/profil', nom: 'profil', connexion: true },
  { chemin: '/caisse', nom: 'caisse', connexion: true },
  { chemin: '/ecran-client', nom: 'ecran-client', connexion: true },
  { chemin: '/dashboard', nom: 'dashboard', connexion: true },
  { chemin: '/commandes', nom: 'commandes-recues', connexion: true },
  { chemin: '/rapports', nom: 'rapports', connexion: true },
  { chemin: '/admin', nom: 'admin', connexion: true },
  { chemin: '/admin/commandes', nom: 'admin-commandes', connexion: true },
  { chemin: '/admin/clients', nom: 'admin-clients', connexion: true },
  { chemin: '/connexion', nom: 'connexion', anonyme: true },
  { chemin: '/inscription', nom: 'inscription', anonyme: true },
  { chemin: '/route-inexistante', nom: '404', anonyme: true },
];

/** Localise le Chrome téléchargé par `npx puppeteer browsers install chrome`. */
function trouverChrome() {
  if (process.env.CHROME_PATH && existsSync(process.env.CHROME_PATH)) return process.env.CHROME_PATH;
  const base = join(homedir(), '.cache/puppeteer/chrome');
  if (!existsSync(base)) {
    throw new Error(
      'Chrome introuvable. Lancez : npx puppeteer browsers install chrome ' +
        "ou définissez la variable d'environnement CHROME_PATH.",
    );
  }
  for (const version of readdirSync(base)) {
    for (const suffixe of ['chrome-linux64/chrome', 'chrome-linux/chrome']) {
      const candidat = join(base, version, suffixe);
      if (existsSync(candidat)) return candidat;
    }
  }
  throw new Error('Binaire Chrome introuvable dans ' + base);
}

const navigateur = await puppeteer.launch({
  executablePath: trouverChrome(),
  headless: true,
  args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
});

const rapport = [];
let totalPb = 0;

/** Crée un onglet instrumenté (collecte console + réseau + exceptions). */
async function nouvelOnglet() {
  const page = await navigateur.newPage();
  await page.setViewport({ width: 1280, height: 900 });
  const problemes = [];

  page.on('console', (msg) => {
    const type = msg.type();
    if (type !== 'error' && type !== 'warning') return;
    const texte = msg.text();
    // Les 404 réseau pendant la navigation sont traités plus bas.
    if (texte.includes('favicon')) return;
    problemes.push({ type: `console.${type}`, texte: texte.slice(0, 300) });
  });

  page.on('pageerror', (err) => {
    problemes.push({ type: 'exception', texte: String(err).slice(0, 300) });
  });

  page.on('requestfailed', (req) => {
    const url = req.url();
    if (url.includes('favicon')) return;
    problemes.push({ type: 'requete.échouée', texte: `${req.method()} ${url} - ${req.failure()?.errorText}` });
  });

  page.on('response', (res) => {
    if (res.status() >= 400 && !res.url().includes('favicon')) {
      problemes.push({ type: `http.${res.status()}`, texte: res.url() });
    }
  });

  return { page, problemes };
}

/** Base API utilisée par l'application (doit correspondre à environment.ts). */
const API = process.env.API_BASE ?? 'http://127.0.0.1:8000/api';

/** Jeton d'audit : une seule connexion réutilisée pour toutes les routes. */
let jetonsAudit = null;

async function obtenirJetons() {
  if (jetonsAudit) return jetonsAudit;
  const reponse = await fetch(`${API}/auth/login/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      username: process.env.AUDIT_USER ?? 'audit_bot',
      password: process.env.AUDIT_PASS ?? 'AuditFront2026',
    }),
  });
  if (!reponse.ok) throw new Error(`Connexion audit échouée (HTTP ${reponse.status})`);
  jetonsAudit = await reponse.json();
  return jetonsAudit;
}

/**
 * Prépare la session du prochain onglet : injecte les clés JWT exactes lues
 * par `AuthService` (`lb.token`, `lb.refresh`, `lb.utilisateur`), ou les
 * purge pour auditer une page anonymement.
 *
 * On doit d'abord charger l'origine du dev-server : localStorage n'est
 * accessible que pour l'origine courante.
 */
async function preparerSession(page, connecte) {
  await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 45000 });

  if (!connecte) {
    await page.evaluate(() => {
      localStorage.removeItem('lb.token');
      localStorage.removeItem('lb.refresh');
      localStorage.removeItem('lb.utilisateur');
    });
    return;
  }

  const jetons = await obtenirJetons();
  await page.evaluate((jetons) => {
    const VERS_ROLE = {
      ADMIN: 'admin',
      GESTIONNAIRE: 'gestionnaire',
      VENDEUR: 'vendeur',
      CLIENT: 'client',
    };
    const api = jetons.user;
    const nom =
      [api.first_name, api.last_name].filter(Boolean).join(' ').trim() || api.username;
    const initiales = nom
      .split(' ')
      .filter(Boolean)
      .slice(0, 2)
      .map((m) => m[0]?.toUpperCase() ?? '')
      .join('');
    const utilisateur = {
      id: String(api.id),
      nom,
      email: api.email ?? '',
      telephone: api.telephone ?? '',
      avatarUrl: api.avatar_url ?? '',
      role: VERS_ROLE[api.role] ?? 'client',
      initiales,
      token: jetons.access,
    };
    localStorage.setItem('lb.token', jetons.access);
    localStorage.setItem('lb.refresh', jetons.refresh);
    localStorage.setItem('lb.utilisateur', JSON.stringify(utilisateur));
  }, jetons);
}

/**
 * Résout une vraie fiche produit depuis le catalogue.
 *
 * Les identifiants viennent de l'API Django (`/vin/2`), `v-001` n'existe
 * qu'avec le catalogue mocké : l'audit ne doit pas tester une URL morte.
 */
async function urlPremiereFiche() {
  const { page } = await nouvelOnglet();
  try {
    await page.goto(`${BASE}/catalogue`, { waitUntil: 'networkidle2', timeout: 45000 });
    await page.waitForSelector('a[href*="/vin/"]', { timeout: 15000 });
    return await page.$eval('a[href*="/vin/"]', (a) => new URL(a.href).pathname);
  } catch {
    return '/catalogue';
  } finally {
    await page.close();
  }
}

ROUTES.find((r) => r.nom === 'fiche-vin').chemin = await urlPremiereFiche();

for (const route of ROUTES) {
  const { page, problemes } = await nouvelOnglet();

  if (route.connexion || route.anonyme) await preparerSession(page, !!route.connexion);

  try {
    await page.goto(`${BASE}${route.chemin}`, { waitUntil: 'networkidle2', timeout: 45000 });
  } catch (e) {
    problemes.push({ type: 'navigation', texte: String(e).slice(0, 200) });
  }

  // Laisse le temps aux animations et aux chargements simulés (600 ms).
  await new Promise((r) => setTimeout(r, 1400));

  const infos = await page.evaluate(() => {
    const racine = document.querySelector('app-root');
    const texte = (racine?.innerText ?? '').replace(/\s+/g, ' ').trim();
    return {
      titre: document.title,
      dataTheme: document.documentElement.getAttribute('data-theme'),
      lang: document.documentElement.getAttribute('lang'),
      longueurTexte: texte.length,
      extrait: texte.slice(0, 160),
      imagesCassees: [...document.querySelectorAll('img')]
        .filter((i) => i.complete && i.naturalWidth === 0)
        .map((i) => i.getAttribute('src')),
      squelettes: document.querySelectorAll('.skeleton-bloc, .skeleton-card').length,
    };
  });

  await page.screenshot({ path: resolve(DOSSIER, `${route.nom}.png`), fullPage: false });

  const vide = infos.longueurTexte < 120;
  const pb = problemes.length;
  totalPb += pb;

  rapport.push({ route: route.chemin, nom: route.nom, ...infos, vide, problemes });

  const marque = pb === 0 ? (vide ? 'VIDE' : 'OK  ') : 'PB  ';
  console.log(`[${marque}] ${route.chemin.padEnd(26)} ${String(infos.longueurTexte).padStart(5)} car.  img cassées: ${infos.imagesCassees.length}`);
  for (const p of problemes.slice(0, 6)) {
    console.log(`        └─ [${p.type}] ${p.texte}`);
  }
  if (infos.imagesCassees.length) console.log(`        └─ [img] ${infos.imagesCassees.join(', ')}`);

  await page.close();
}

await navigateur.close();

console.log('\n' + '═'.repeat(70));
console.log(`Routes auditées : ${rapport.length}   Problèmes : ${totalPb}`);
const vides = rapport.filter((r) => r.vide);
if (vides.length) {
  console.log(`Pages quasi vides : ${vides.map((r) => r.route).join(', ')}`);
}
console.log(`Captures : ${DOSSIER}`);
process.exit(totalPb > 0 || vides.length > 0 ? 1 : 0);