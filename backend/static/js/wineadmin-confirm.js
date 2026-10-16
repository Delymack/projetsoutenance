/* ============================================================
   WineAdmin Confirm — petite fenêtre avant suppression
   Intercepte le bouton « Supprimer » de la colonne Actions de
   toutes les tables et demande confirmation avant d'envoyer la
   suppression (POST). Sans JavaScript, le lien retombe sur la
   page de confirmation Django (dégradation progressive).
   ============================================================ */
(function () {
  'use strict';

  var dialog = document.getElementById('wine-confirm');
  var form = document.getElementById('wine-confirm-form');
  var message = document.getElementById('wine-confirm-message');
  var annuler = dialog ? dialog.querySelector('.wine-confirm-cancel') : null;
  var dernierFocus = null;

  if (!dialog || !form || !message) return;

  function ouvrir(lien) {
    dernierFocus = document.activeElement;
    form.setAttribute('action', lien.href);

    var nom = (lien.getAttribute('data-confirm-name') || '').trim();
    var libelle = nom || lien.getAttribute('aria-label') || 'cet élément';

    message.textContent = 'Supprimer ';
    var fort = document.createElement('strong');
    fort.textContent = libelle;
    message.appendChild(fort);
    message.appendChild(document.createTextNode(' ? Cette action est définitive.'));

    dialog.setAttribute('aria-hidden', 'false');
    document.body.classList.add('wine-confirm-open');
    if (annuler) annuler.focus();
  }

  function fermer() {
    if (dialog.getAttribute('aria-hidden') === 'true') return;
    dialog.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('wine-confirm-open');
    if (dernierFocus && typeof dernierFocus.focus === 'function') dernierFocus.focus();
  }

  document.addEventListener('click', function (event) {
    if (event.button !== undefined && event.button !== 0) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

    var lien = event.target.closest('a.databtn-delete');
    if (lien) {
      event.preventDefault();
      ouvrir(lien);
      return;
    }

    if (event.target.closest('[data-confirm-close]')) {
      event.preventDefault();
      fermer();
    }
  });

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') fermer();
  });
})();
