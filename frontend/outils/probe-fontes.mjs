import puppeteer from 'puppeteer-core';
import { existsSync } from 'node:fs';

const BASE = 'http://localhost:4200';
const EXECUTABLE =
  ['/usr/bin/google-chrome', '/usr/bin/chromium-browser', '/usr/bin/chromium'].find(existsSync);

const nav = await puppeteer.launch({
  executablePath: EXECUTABLE,
  headless: true,
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
});
const page = await nav.newPage();
const evenements = [];
page.on('requestfailed', (r) => {
  if (/fonts\.(googleapis|gstatic)/.test(r.url())) evenements.push(`FAIL ${r.url()} :: ${r.failure()?.errorText}`);
});
page.on('response', (r) => {
  if (/fonts\.(googleapis|gstatic)/.test(r.url())) evenements.push(`${r.status()} ${r.url().slice(0, 110)}`);
});
await page.goto(BASE, { waitUntil: 'networkidle2' });
// Force réellement le chargement de la FontFace (fonts.ready peut résoudre
// avant que les glyphes des icônes soient réclamés par le rendu).
await page.evaluate(async () => {
  try {
    await document.fonts.load('24px "Material Icons"', 'home inbox receipt_long');
    await document.fonts.ready;
  } catch { /* ignore */ }
});
await new Promise((r) => setTimeout(r, 1500));
const etat = await page.evaluate(() => {
  const icone = document.querySelector('mat-icon, .mat-icon');
  return {
    lienCss: [...document.querySelectorAll('link[rel=stylesheet]')].map((l) => l.href).filter((h) => /fonts\.googleapis/.test(h)),
    famille: icone ? getComputedStyle(icone).fontFamily : 'PAS DE MAT-ICON',
    texte: icone?.textContent,
    liga: icone ? getComputedStyle(icone).fontFeatureSettings : 'n/a',
    dispoIcons: document.fonts.check('24px "Material Icons"'),
    families: [...document.fonts].map((f) => `${f.family}:${f.status}`).filter((s) => /Material/i.test(s)),
    href: location.href,
  };
});
console.log(JSON.stringify(etat, null, 2));
console.log('--- événements polices ---');
console.log(evenements.join('\n') || '(aucun échange fonts.* observé)');
await page.screenshot({ path: '/tmp/probe-navbar.png', clip: { x: 0, y: 0, width: 1280, height: 110 } });
console.log('capture: /tmp/probe-navbar.png');
await nav.close();
