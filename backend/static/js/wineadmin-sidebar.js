/* ============================================================
   WineAdmin Sidebar — interactivité du menu latéral
   - Recherche locale (accent-insensible) avec navigation clavier
   - Groupes de navigation sans séparateurs visibles
   - Favoris épingles (localStorage)
   - Raccourcis : Ctrl/Cmd+K ou « / » pour chercher, Échap pour fermer
   ============================================================ */
(function () {
  'use strict';

  var LS_FAVS = 'wineadmin-favs';

  function normalise(value) {
    return (value || '').toLocaleLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  }

  function readLS(key, fallback) {
    try {
      var raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (e) { return fallback; }
  }

  function writeLS(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) {}
  }

  function initSidebar() {
    var sidebar = document.getElementById('jazzy-sidebar');
    var nav = document.getElementById('jazzy-navigation');
    var search = document.getElementById('sb-find-input');
    var empty = document.getElementById('sb-find-empty');
    if (!sidebar || !nav) return;

    var favSection = document.getElementById('sb-fav-section');
    if (favSection) favSection.dataset.sbSection = '';
    var favs = readLS(LS_FAVS, []);
    var isSearching = false;

    /* ----------------------------------------------------------
       Items d'une section : freres jusqu'à la section suivante
       ---------------------------------------------------------- */
    function sectionItems(section) {
      var items = [];
      var el = section.nextElementSibling;
      while (el && !el.classList.contains('nav-section')) {
        if (el.classList.contains('nav-item')) items.push(el);
        el = el.nextElementSibling;
      }
      return items;
    }

    function textOf(item) {
      return ((item.querySelector('.nav-label') || item).textContent || '').toLowerCase();
    }

    /* ==========================================================
       Groupes de navigation : structurels, sans en-têtes visibles
       ========================================================== */
    var sections = nav.querySelectorAll('li.nav-section[data-sb-section]');

    sections.forEach(function (section) {
      section.removeAttribute('role');
      section.removeAttribute('tabindex');
      section.removeAttribute('title');
      section.classList.remove('sb-sect-closed');
      sectionItems(section).forEach(function (li) { li.hidden = false; });
    });

    /* ==========================================================
       FAVORIS
       ========================================================== */
    function refreshFavButtons() {
      var favSet = {};
      favs.forEach(function (f) { favSet[f.href] = true; });
      nav.querySelectorAll('button.sb-fav-btn').forEach(function (btn) {
        var href = btn.getAttribute('data-sb-fav-href') || '';
        var active = Boolean(favSet[href]);
        btn.classList.toggle('sb-is-fav', active);
        btn.setAttribute('aria-pressed', active ? 'true' : 'false');
        btn.title = active ? 'Retirer des favoris' : 'Épingler';
      });
    }

    function renderFavs() {
      if (!favSection) return;
      nav.querySelectorAll('li.sb-fav-item').forEach(function (li) { li.remove(); });
      if (!favs.length) {
        favSection.hidden = true;
        return;
      }
      favSection.hidden = false;
      var ref = favSection;
      favs.forEach(function (fav) {
        var li = document.createElement('li');
        li.className = 'nav-item sb-fav-item';
        var a = document.createElement('a');
        a.className = 'nav-link';
        a.href = fav.href;
        var wrap = document.createElement('span');
        wrap.className = 'nav-icon-wrap nav-icon-dashboard';
        if (fav.png) {
          var img = document.createElement('img');
          img.className = 'sb-png';
          img.src = fav.png;
          img.alt = '';
          wrap.appendChild(img);
        } else {
          wrap.innerHTML = '<i class="' + (fav.icon || 'fas fa-star') + '"></i>';
        }
        a.appendChild(wrap);
        var label = document.createElement('span');
        label.className = 'nav-label';
        label.textContent = fav.label || fav.href;
        a.appendChild(label);
        li.appendChild(a);
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'sb-fav-btn';
        btn.setAttribute('data-sb-fav-href', fav.href);
        btn.setAttribute('aria-label', 'Retirer des favoris');
        btn.innerHTML = '<i class="fas fa-star"></i>';
        li.appendChild(btn);
        ref.after(li);
        ref = li;
      });
      refreshFavButtons();
    }

    nav.addEventListener('click', function (e) {
      var btn = e.target.closest('button.sb-fav-btn');
      if (!btn) return;
      e.preventDefault();
      e.stopPropagation();

      var item = btn.closest('.nav-item');
      var a = item ? item.querySelector('a.nav-link') : null;
      var href = btn.getAttribute('data-sb-fav-href') || (a ? a.getAttribute('href') : '');
      if (!href) return;

      var exists = favs.some(function (f) { return f.href === href; });
      if (exists) {
        favs = favs.filter(function (f) { return f.href !== href; });
      } else {
        var icon = a ? ((a.querySelector('.nav-icon-wrap i') || {}).className || 'fas fa-star') : 'fas fa-star';
        var png = a && a.querySelector('.sb-png') ? a.querySelector('.sb-png').getAttribute('src') : '';
        favs.push({
          href: href,
          label: a ? ((a.querySelector('.nav-label') || {}).textContent || '').trim() : '',
          icon: icon,
          png: png
        });
        favs.sort(function (x, y) { return (x.label || '').localeCompare(y.label || ''); });
      }
      writeLS(LS_FAVS, favs);
      renderFavs();
      if (isSearching) applyFilter();
    });

    /* ==========================================================
       RECHERCHE + NAVIGATION CLAVIER
       ========================================================== */
    function applyFilter() {
      var q = normalise(search ? search.value.trim() : '');
      isSearching = q.length > 0;
      var matches = [];
      var showFavSection = favs.length > 0;

      nav.querySelectorAll('li.nav-item').forEach(function (item) {
        var hit = !q || normalise(textOf(item)).indexOf(q) !== -1;
        item.hidden = !hit;
        if (hit) matches.push(item);
      });

      if (isSearching) {
        sections.forEach(function (section) {
          var hasVisibleItems = sectionItems(section).some(function (li) { return !li.hidden; });
          section.hidden = !hasVisibleItems;
        });
      } else {
        nav.querySelectorAll('li.nav-section').forEach(function (s) {
          s.hidden = s.id === 'sb-fav-section' && !showFavSection ? true : false;
        });
        highlightItem(null);
      }

      if (empty) empty.classList.toggle('sb-show', !isSearching ? false : matches.length === 0);
      return matches;
    }

    function visibleMatches(items) {
      return items.filter(function (li) {
        return !li.hidden && li.querySelector('a.nav-link');
      });
    }

    function highlightItem(li) {
      nav.querySelectorAll('.sb-kbd-active').forEach(function (el) {
        el.classList.remove('sb-kbd-active');
      });
      if (li) {
        var a = li.querySelector('a.nav-link');
        if (a) a.classList.add('sb-kbd-active');
      }
    }

    var kbdIndex = -1;
    var kbdItems = [];

    function resetKbd() {
      kbdIndex = -1;
      kbdItems = [];
      highlightItem(null);
    }

    if (search) {
      search.addEventListener('input', function () {
        kbdItems = applyFilter();
        kbdIndex = -1;
        highlightItem(null);
      });

      search.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
          search.value = '';
          resetKbd();
          applyFilter();
          search.blur();
          return;
        }
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
          e.preventDefault();
          var items = visibleMatches(kbdItems);
          if (!items.length) return;
          if (kbdIndex < 0) {
            kbdIndex = e.key === 'ArrowDown' ? 0 : items.length - 1;
          } else {
            kbdIndex = e.key === 'ArrowDown'
              ? Math.min(kbdIndex + 1, items.length - 1)
              : Math.max(kbdIndex - 1, 0);
          }
          highlightItem(items[kbdIndex]);
          var a = items[kbdIndex].querySelector('a.nav-link');
          if (a && a.scrollIntoView) a.scrollIntoView({ block: 'nearest' });
          return;
        }
        if (e.key === 'Enter') {
          var active = nav.querySelector('.sb-kbd-active') || nav.querySelector('.nav-link.active');
          if (active) {
            e.preventDefault();
            window.location.href = active.getAttribute('href');
          }
        }
      });
    }

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && search && search.value) {
        search.value = '';
        resetKbd();
        applyFilter();
      }
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        if (search) { search.focus(); search.select(); }
      } else if (e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey &&
                 document.activeElement !== search &&
                 !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) {
        e.preventDefault();
        if (search) search.focus();
      }
    });

    renderFavs();
    applyFilter();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSidebar);
  } else {
    initSidebar();
  }
})();