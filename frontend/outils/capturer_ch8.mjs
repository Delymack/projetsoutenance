import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
import puppeteer from 'puppeteer-core';

const BASE = process.argv[2] ?? 'http://localhost:4200';
const OUT = process.argv[3] ?? '/run/media/delymack/691a3c27-7ff6-475e-8c83-0acc6d258824/projet_soutenance/livre_soutenance_memoire/captures';
const USER = process.env.CAP_USER ?? 'soutenance';
const PASS = process.env.CAP_PASS ?? 'Cap2026!';
const API = 'http://127.0.0.1:8000/api';
const ADMIN = 'http://127.0.0.1:8000';
const EXEC = '/usr/bin/chromium-browser';

mkdirSync(OUT, { recursive: true });
const roleMap = { ADMIN: 'admin', GESTIONNAIRE: 'gestionnaire', VENDEUR: 'vendeur', CLIENT: 'client' };

const CLIENT_PAGES = [
  ['fig8-1_connexion', '/connexion'],
  ['fig8-2_accueil', '/'],
  ['fig8-3_catalogue', '/catalogue'],
  ['fig8-4_promotions', '/promotions'],
  ['fig8-5_dashboard', '/dashboard'],
  ['fig8-6_caisse', '/caisse'],
  ['fig8-7_commandes', '/commandes'],
  ['fig8-8_rapports', '/rapports'],
  ['fig8-9_profil', '/profil'],
];
const ADMIN_PAGES = [
  ['fig8-10_admin_dashboard', '/admin/'],
  ['fig8-11_admin_produits', '/admin/produits/produit/'],
  ['fig8-12_admin_clients', '/admin/clients/client/'],
  ['fig8-13_admin_stocks', '/admin/stocks/stock/'],
  ['fig8-14_admin_promotions', '/admin/promotions/promotion/'],
  ['fig8-15_admin_ventes', '/admin/ventes/vente/'],
  ['fig8-16_admin_reservations', '/admin/ventes/reservation/'],
];

async function main() {
  const r = await fetch(`${API}/auth/login/`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: USER, password: PASS }),
  });
  const data = await r.json();
  const u = data.user;
  const utilisateur = {
    id: String(u.id),
    nom: [u.first_name, u.last_name].filter(Boolean).join(' ').trim() || u.username,
    email: u.email ?? '', telephone: u.telephone ?? '', avatarUrl: u.avatar_url ?? '',
    role: roleMap[u.role] ?? 'client',
    initiales: (u.username || 'U').slice(0, 2).toUpperCase(),
    token: data.access,
  };

  const browser = await puppeteer.launch({
    executablePath: EXEC, headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--force-device-scale-factor=1'],
  });
  const wait = (ms) => new Promise((res) => setTimeout(res, ms));

  try {
    // 1) Angular client pages with injected JWT
    const page = await browser.newPage();
    await page.setViewport({ width: 1920, height: 1080 });
    await page.evaluateOnNewDocument((ut, tok, ref) => {
      try {
        localStorage.setItem('lb.token', tok);
        localStorage.setItem('lb.refresh', ref);
        localStorage.setItem('lb.utilisateur', JSON.stringify(ut));
      } catch {}
    }, utilisateur, data.access, data.refresh);
    for (const [name, path] of CLIENT_PAGES) {
      if (process.env.SKIP_CLIENT === '1') break;
      try {
        await page.goto(BASE + path, { waitUntil: 'domcontentloaded', timeout: 45000 });
        await wait(3000);
        await page.screenshot({ path: join(OUT, name + '.png') });
        console.log('OK client', name);
      } catch (e) { console.log('FAIL client', name, e.message); }
    }
    await page.close();

    // 2) Django admin with session login
    const admin = await browser.newPage();
    await admin.setViewport({ width: 1920, height: 1080 });
    try {
      await admin.goto(ADMIN + '/admin/login/?next=/admin/', { waitUntil: 'domcontentloaded', timeout: 45000 });
      await admin.waitForSelector('input[name="username"]', { timeout: 30000 });
      await admin.type('input[name="username"]', USER, { delay: 20 });
      await admin.type('input[name="password"]', PASS, { delay: 20 });
      await Promise.all([
        admin.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 45000 }).catch(() => {}),
        admin.click('button[type="submit"]'),
      ]);
      await wait(3000);
      console.log('admin logged, url=', admin.url());
    } catch (e) { console.log('admin login fail', e.message); }

    for (const [name, path] of ADMIN_PAGES) {
      try {
        await admin.goto(ADMIN + path, { waitUntil: 'domcontentloaded', timeout: 45000 });
        await wait(2000);
        await admin.screenshot({ path: join(OUT, name + '.png') });
        console.log('OK admin', name);
      } catch (e) { console.log('FAIL admin', name, e.message); }
    }
    await admin.close();
  } finally {
    await browser.close();
  }
}
main().catch((e) => { console.error(e); process.exit(1); });
