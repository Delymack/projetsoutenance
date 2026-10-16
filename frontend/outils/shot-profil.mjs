import puppeteer from 'puppeteer-core';
import { existsSync } from 'node:fs';
import { join } from 'node:path';

const BASE = 'http://localhost:4200';
const API = 'http://127.0.0.1:8000/api';
const SORTIE = process.argv[2] ?? '/tmp/profil-shot.png';

const EXECUTABLE =
  ['/usr/bin/google-chrome', '/usr/bin/chromium-browser', '/usr/bin/chromium'].find(existsSync);

const jetons = await (await fetch(`${API}/auth/login/`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'audit_bot', password: 'AuditFront2026' }),
})).json();

const nav = await puppeteer.launch({
  executablePath: EXECUTABLE,
  headless: true,
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
});
const page = await nav.newPage();
await page.setViewport({ width: 1280, height: 900 });
await page.goto(BASE, { waitUntil: 'domcontentloaded' });
await page.evaluate((jetons) => {
  const VERS_ROLE = { ADMIN: 'admin', GESTIONNAIRE: 'gestionnaire', VENDEUR: 'vendeur', CLIENT: 'client' };
  const api = jetons.user;
  const nom = [api.first_name, api.last_name].filter(Boolean).join(' ').trim() || api.username;
  localStorage.setItem('lb.theme', 'sombre');
  localStorage.setItem('lb.token', jetons.access);
  localStorage.setItem('lb.refresh', jetons.refresh);
  localStorage.setItem('lb.utilisateur', JSON.stringify({
    id: String(api.id), nom, email: api.email ?? '', telephone: api.telephone ?? '',
    avatarUrl: api.avatar_url ?? '', role: VERS_ROLE[api.role] ?? 'client',
    initiales: 'AU', token: jetons.access,
  }));
}, jetons);
await page.goto(`${BASE}/profil`, { waitUntil: 'networkidle2' });
// Ordre du capturer.mjs : d'abord laisser le rendu réclamer les glyphes,
// puis attendre fonts.ready (sinon ready résout avant tout chargement).
await new Promise((r) => setTimeout(r, 2600));
await page.evaluate(() => document.fonts?.ready).catch(() => {});
await new Promise((r) => setTimeout(r, 400));
await page.screenshot({ path: SORTIE });
console.log('OK', SORTIE, 'theme=', await page.evaluate(() => document.documentElement.getAttribute('data-theme')));
await nav.close();
