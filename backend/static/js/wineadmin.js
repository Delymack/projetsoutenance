/* Bascule de thème : le menu palette Jazzmin est désactivé dans la configuration,
   cet unique contrôle conserve donc le choix clair/sombre accessible. */
(function () {
  'use strict';

  var KEY = 'jazzmin-theme-mode';
  var CELLS = { light: ['fa-moon', 'Mode sombre'], dark: ['fa-sun', 'Mode clair'] };

  function currentMode() {
    return document.documentElement.getAttribute('data-bs-theme') === 'dark' ? 'dark' : 'light';
  }

  function setMode(mode) {
    document.documentElement.setAttribute('data-bs-theme', mode);
    try { localStorage.setItem(KEY, mode); } catch (e) {}

    var html = document.documentElement;
    html.classList.add('wine-theme-switching');
    window.clearTimeout(html._wineThemeTimer);
    html._wineThemeTimer = window.setTimeout(function () {
      html.classList.remove('wine-theme-switching');
    }, 320);

    var cell = CELLS[mode];
    document.querySelectorAll('.wine-theme-toggle i').forEach(function (icon) {
      icon.className = 'fas ' + cell[0];
    });
    document.querySelectorAll('.wine-theme-toggle').forEach(function (button) {
      button.setAttribute('aria-pressed', mode === 'dark');
      button.setAttribute('title', cell[1]);
    });
  }

  function init() {
    var nav = document.querySelector('#jazzy-navbar .navbar-nav.ms-auto');
    if (!nav || nav.querySelector('.wine-theme-toggle')) return;

    var cfg = window.WINE_CONFIG || {};
    var pref = null;
    try { pref = localStorage.getItem(KEY); } catch (e) {}
    if (pref === null && cfg.appearance_mode_defaut === 'sombre') {
      setMode('dark');
    }

    var mode = currentMode();
    var cell = CELLS[mode];
    var item = document.createElement('li');
    item.className = 'nav-item';
    item.innerHTML =
      '<a class="nav-link btn wine-theme-toggle" href="#" role="button"' +
      ' aria-label="Basculer le thème clair/sombre" aria-pressed="' + (mode === 'dark') + '"' +
      ' title="' + cell[1] + '"><i class="fas ' + cell[0] + '" aria-hidden="true"></i></a>';

    item.querySelector('.wine-theme-toggle').addEventListener('click', function (event) {
      event.preventDefault();
      setMode(currentMode() === 'dark' ? 'light' : 'dark');
    });

    nav.insertBefore(item, nav.firstChild);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

/* La navigation latérale (recherche, favoris, sections, raccourcis clavier)
   est gérée dans static/js/wineadmin-sidebar.js. */
