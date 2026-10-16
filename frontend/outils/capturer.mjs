/**
 * Captures d'écran des pages client — vérification visuelle des changements.
 *
 * Usage : node outils/capturer.mjs [prefixe] [urlBase]
 *   Ex.  node outils/capturer.mjs apres http://127.0.0.1:4200
 *
 * Sortie : outils/captures/<prefixe>-<page>.png (bureau 1280×900) et
 *          outils/captures/<prefixe>-<page>-mobile.png (390×844).
 */
import { existsSync } from 'node:fs';
import { mkdir } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import puppeteer from 'puppeteer-core';

const PREFIXE = process.argv[2] ?? 'apres';
const BASE = process.argv[3] ?? 'http://127.0.0.1:4200';
const SEUL = process.argv[4]; // nom de page optionnel : capture une seule vue
const RACINE = resolve(dirname(fileURLToPath(import.meta.url)));
const SORTIE = join(RACINE, 'captures');

const PAGES = [
  ['accueil', '/'],
  ['catalogue', '/catalogue'],
  ['fiche-vin', '/vin/12'],
  ['panier', '/panier'],
  ['favoris', '/favoris'],
  ['connexion', '/connexion'],
  ['inscription', '/inscription'],
];

const FORMATS = [
  ['bureau', { width: 1280, height: 900 }],
  ['mobile', { width: 390, height: 844 }],
];

const EXECUTABLE =
  process.env.CHROME_PATH ??
  ['/usr/bin/google-chrome', '/usr/bin/chromium-browser', '/usr/bin/chromium'].find(existsSync) ??
  '/usr/bin/chromium-browser';

async function attendre(page) {
  // Laisse les lazy-chunks, les appels API et les animations d'entrée se poser.
  await new Promise((r) => setTimeout(r, 2600));
  await page.evaluate(() => document.fonts?.ready).catch(() => {});
  // Le bandeau d'installation PWA apparaît après coup : on le retire au dernier moment.
  await page.evaluate(() => {
    document.querySelectorAll('body *').forEach((n) => {
      const t = (n.textContent ?? '').trim();
      if (t.startsWith("Installer l'application") && t.length < 120 && n.children.length <= 4) n.remove();
    });
  }).catch(() => {});
}
async function main() {
  await mkdir(SORTIE, { recursive: true });
  const navigateur = await puppeteer.launch({
    executablePath: EXECUTABLE,
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--force-device-scale-factor=1'],
  });

  try {
    for (const [format, viewport] of FORMATS) {
      const page = await navigateur.newPage();
      await page.setViewport(viewport);
      // `THEME=sombre` capture le site dans le thème sombre.
      if (process.env.THEME === 'sombre') {
        await page.evaluateOnNewDocument(() => {
          try {
            localStorage.setItem('lb.theme', 'sombre');
          } catch {
            /* stockage indisponible */
          }
        });
      }

      for (const [nom, chemin] of PAGES) {
        if (SEUL && nom !== SEUL) continue;
        const fichier = join(SORTIE, `${PREFIXE}-${nom}${format === 'mobile' ? '-mobile' : ''}.png`);
        // La page peut recharger pendant la première frappe réseau (SW / redirect).
        // On retente une fois avant d'abandonner la vue.
        for (let tentative = 0; tentative < 2; tentative++) {
          try {
            await page.goto(BASE + chemin, {
              waitUntil: 'domcontentloaded',
              timeout: 30000,
            });
            // Le bandeau d'installation PWA masque le bas de l'écran : on le retire.
            await page.evaluate(() => {
              document.querySelectorAll('body *').forEach((n) => {
                const t = (n.textContent ?? '').trim();
                if (t.startsWith("Installer l'application") && t.length < 120 && n.children.length <= 4)
                  n.remove();
              });
            });
            await attendre(page);
            await page.screenshot({ path: fichier });
            console.log('✓', fichier);
            // Vue du pied de page (bureau seulement) : on descend tout en bas.
            if (format === 'bureau') {
              await page.evaluate(() =>
                window.scrollTo({ top: document.body.scrollHeight, behavior: 'instant' }),
              );
              await new Promise((r) => setTimeout(r, 700));
              const pied = join(
                SORTIE,
                `${PREFIXE}-${nom}-pied.png`,
              );
              await page.screenshot({ path: pied });
              console.log('✓', pied);
              await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
            }
            break;
          } catch (e) {
            if (tentative === 1) {
              console.error('✗', fichier, e.message);
              break;
            }
            await new Promise((r) => setTimeout(r, 1200));
          }
        }
      }
      await page.close();
    }
  } finally {
    await navigateur.close();
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
