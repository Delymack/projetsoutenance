// Karma : configuration locale pour `npm test`.
// Chrome est lancé en mode headless avec `--no-sandbox` (conteneur / CI) ;
// le binaire est résolu via CHROME_BIN si fourni, sinon via le cache Puppeteer.
const fs = require('node:fs');
const path = require('node:path');

// Resolve Chrome binary for Karma tests. Prefer user-provided CHROME_BIN, then
// Puppeteer's cached Chromium if available, otherwise fall back to system path.
(function resolveChromeBin() {
  if (process.env.CHROME_BIN) return (process.env.CHROME_BIN = process.env.CHROME_BIN);
  const cacheDir = path.join(process.env.HOME || '', '.cache', 'puppeteer', 'chrome');
  try {
    if (fs.existsSync(cacheDir)) {
      const entries = fs.readdirSync(cacheDir, { withFileTypes: true })
        .filter((d) => d.isDirectory())
        .map((d) => path.join(cacheDir, d.name, 'chrome-linux64', 'chrome'))
        .find((p) => fs.existsSync(p));
      if (entries) {
        process.env.CHROME_BIN = entries;
        return;
      }
    }
  } catch (err) {
    // Graceful fallback below
  }
  process.env.CHROME_BIN = process.env.CHROME_BIN || '/usr/bin/google-chrome';
})();

module.exports = function (config) {
  config.set({
    basePath: '',
    frameworks: ['jasmine', '@angular-devkit/build-angular'],
    plugins: [
      require('karma-jasmine'),
      require('karma-chrome-launcher'),
      require('karma-jasmine-html-reporter'),
      require('karma-coverage'),
      require('@angular-devkit/build-angular/plugins/karma'),
    ],
    client: {
      jasmine: {},
      clearContext: false,
    },
    jasmineHtmlReporter: {
      suppressAll: true,
    },
    coverageReporter: {
      dir: require('node:path').join(__dirname, './coverage/lazanibetsileo'),
      subdir: '.',
      reporters: [{ type: 'html' }, { type: 'text-summary' }],
    },
    reporters: ['progress', 'kjhtml'],
    browsers: ['ChromeHeadlessNoSandbox'],
    customLaunchers: {
      ChromeHeadlessNoSandbox: {
        base: 'ChromeHeadless',
        flags: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
      },
    },
    restartOnFileChange: true,
  });
};