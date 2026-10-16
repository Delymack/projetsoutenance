/**
 * Diagnose contrast: dump computed colors of suspect elements.
 * Usage: node outils/diagnostic-couleurs.mjs [baseUrl]
 */
import puppeteer from 'puppeteer-core';
import { existsSync, readdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const BASE = process.argv[2] ?? 'http://localhost:4200';
const API = process.env.API_BASE ?? 'http://127.0.0.1:8000/api';

function trouverChrome() {
  if (process.env.CHROME_PATH && existsSync(process.env.CHROME_PATH)) return process.env.CHROME_PATH;
  const base = join(homedir(), '.cache/puppeteer/chrome');
  for (const version of readdirSync(base)) {
    for (const suffixe of ['chrome-linux64/chrome', 'chrome-linux/chrome']) {
      const candidat = join(base, version, suffixe);
      if (existsSync(candidat)) return candidat;
    }
  }
  throw new Error('Chrome introuvable');
}

const nav = await puppeteer.launch({
  executablePath: trouverChrome(),
  headless: true,
  args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'],
});

/** Jetons JWT pour auditer les pages protégées. */
const reponse = await fetch(`${API}/auth/login/`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'audit_bot', password: 'AuditFront2026' }),
});
if (!reponse.ok) throw new Error(`login audit: HTTP ${reponse.status}`);
const jetons = await reponse.json();

async function preparerSession(page, connecte) {
  await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.evaluate((connecte, jetons) => {
    if (!connecte) {
      for (const c of ['lb.token', 'lb.refresh', 'lb.utilisateur']) localStorage.removeItem(c);
      return;
    }
    const VERS_ROLE = { ADMIN: 'admin', GESTIONNAIRE: 'gestionnaire', VENDEUR: 'vendeur', CLIENT: 'client' };
    const api = jetons.user;
    const nom = [api.first_name, api.last_name].filter(Boolean).join(' ').trim() || api.username;
    const utilisateur = {
      id: String(api.id),
      nom,
      email: api.email ?? '',
      telephone: api.telephone ?? '',
      avatarUrl: api.avatar_url ?? '',
      role: VERS_ROLE[api.role] ?? 'client',
      initiales: nom.split(' ').filter(Boolean).slice(0, 2).map((m) => m[0]?.toUpperCase() ?? '').join(''),
      token: jetons.access,
    };
    localStorage.setItem('lb.token', jetons.access);
    localStorage.setItem('lb.refresh', jetons.refresh);
    localStorage.setItem('lb.utilisateur', JSON.stringify(utilisateur));
  }, connecte, jetons);
}

async function inspecter(chemin, selecteurs, connecte = false) {
  const page = await nav.newPage();
  await page.setViewport({ width: 1280, height: 900 });
  await preparerSession(page, connecte);
  await page.goto(`${BASE}${chemin}`, { waitUntil: 'networkidle2', timeout: 45000 });
  await new Promise((r) => setTimeout(r, 1600));
  const sortie = await page.evaluate((selecteurs) => {
    const info = (el) => {
      if (!el) return null;
      const cs = getComputedStyle(el);
      return { color: cs.color, bg: cs.backgroundColor, opacity: cs.opacity, texte: (el.textContent ?? '').trim().slice(0, 40) };
    };
    const out = {};
    for (const sel of selecteurs) out[sel] = [...document.querySelectorAll(sel)].slice(0, 3).map(info);
    return out;
  }, selecteurs);
  console.log(`\n=== ${chemin} ===`);
  for (const [sel, vals] of Object.entries(sortie)) {
    if (!vals.length) { console.log(`  ${sel}: ABSENT`); continue; }
    for (const v of vals) console.log(`  ${sel}: color=${v.color} bg=${v.bg} op=${v.opacity} « ${v.texte} »`);
  }
  await page.close();
}

await inspecter('/catalogue', [
  '.mat-mdc-form-field .mdc-floating-label',
  '.mat-mdc-select-value-text',
  '.mat-mdc-checkbox .mdc-label',
]);
await inspecter('/vin/12', [
  '.mat-mdc-tab .mat-mdc-tab-text-content',
  '.mat-mdc-tab .mat-mdc-tab-label',
  'mat-tab-group .mat-mdc-tab .mdc-tab__text-label',
  '.mat-mdc-tab',
]);
await inspecter('/profil', [
  '.profil__stat strong',
  '.profil__stat small',
  '.profil__completure-tete span',
  '.profil__onglet',
  '.commande__statut',
], true);

await nav.close();

