// Karma : configuration locale pour `npm test`.
// Chrome est lancé en mode headless avec `--no-sandbox` (conteneur / CI) ;
// le binaire est résolu via CHROME_BIN si fourni, sinon via le cache Puppeteer.
process.env.CHROME_BIN =
  process.env.CHROME_BIN ||
  require('node:fs')
    .readdirSync(`${process.env.HOME}/.cache/puppeteer/chrome`, { withFileTypes: true })
    .filter((entree) => entree.isDirectory())
    .map((entree) => `${process.env.HOME}/.cache/puppeteer/chrome/${entree.name}/chrome-linux64/chrome`)
    .find((chemin) => require('node:fs').existsSync(chemin)) ||
  '/usr/bin/google-chrome';

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