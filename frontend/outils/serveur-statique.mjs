/**
 * Serveur statique minimal pour tester le build de production.
 * Évite `ng serve` (mode watch très gourmand en mémoire).
 *
 * Usage : node outils/serveur-statique.mjs [port] [dossier]
 */
import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { extname, join, normalize, resolve } from 'node:path';

const PORT = Number(process.argv[2] ?? 8080);
const RACINE = resolve(process.argv[3] ?? 'dist/lazanibetsileo/browser');

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.webmanifest': 'application/manifest+json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
  '.txt': 'text/plain; charset=utf-8',
};

createServer(async (req, res) => {
  try {
    const url = new URL(req.url ?? '/', `http://localhost:${PORT}`);
    // Normalise pour empêcher toute sortie du dossier servi (path traversal).
    const relatif = normalize(decodeURIComponent(url.pathname)).replace(/^(\.\.[/\\])+/, '');
    let fichier = join(RACINE, relatif);

    const infos = await stat(fichier).catch(() => null);
    if (!infos || infos.isDirectory()) fichier = join(RACINE, 'index.html');

    const contenu = await readFile(fichier);
    res.writeHead(200, {
      'Content-Type': TYPES[extname(fichier)] ?? 'application/octet-stream',
      // Le service worker ne doit jamais être servi depuis un cache HTTP.
      'Cache-Control': fichier.endsWith('ngsw.json') || fichier.endsWith('sw.js')
        ? 'no-cache'
        : 'public, max-age=3600',
      'Service-Worker-Allowed': '/',
    });
    res.end(contenu);
  } catch (e) {
    res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end('404');
  }
}).listen(PORT, () => {
  console.log(`Serveur statique : http://localhost:${PORT}  (${RACINE})`);
});