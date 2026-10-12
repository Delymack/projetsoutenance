/* ============================================================
   WineAdmin Actions — icônes sur les boutons d'action
   Attache automatiquement une icône Font Awesome (cover FR/EN)
   à chaque action de l'interface (formulaires, confirmations,
   object-tools) qui n'en possède pas encore.
   Les inputs "submit" deviennent de vrais <button> pour porter
   l'icône (le comportement du formulaire est préservé).
   ============================================================ */
(function () {
  'use strict';

  function normalise(value) {
    return (value || '')
      .toLocaleLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  var RULES = [
    { re: /enregistrer et continuer|save and continue editing|save and view/, icon: 'fas fa-pencil-alt' },
    { re: /enregistrer et ajouter|save and add another/, icon: 'fas fa-plus-circle' },
    { re: /enregistrer comme copie|save as new/, icon: 'fas fa-clone' },
    { re: /^enregistrer$|^save$/, icon: 'fas fa-save' },
    { re: /oui.*(sure|supprimer|confirme|annuler)|yes.*(sure|delete|confirm)/, icon: 'fas fa-check-circle' },
    { re: /^supprimer$|^delete$/, icon: 'fas fa-trash-alt' },
    { re: /^dupliquer$|^duplicate$/, icon: 'fas fa-copy' },
    { re: /^conserver$|^annuler$|^cancel$/, icon: 'fas fa-times-circle' },
    { re: /non, ramene|take me back/, icon: 'fas fa-arrow-left' },
    { re: /^retour$|^back$|^fermer$|^close$/, icon: 'fas fa-arrow-left' },
    { re: /^voir$|^view$|^afficher$/, icon: 'fas fa-eye' },
    { re: /^exporter$|^export$/, icon: 'fas fa-file-export' },
    { re: /^imprimer$|^print$/, icon: 'fas fa-print' },
    { re: /^ajouter|^add\b/, icon: 'fas fa-plus' },
  ];

  function findIcon(text) {
    for (var i = 0; i < RULES.length; i++) {
      if (RULES[i].re.test(text)) return RULES[i].icon;
    }
    return null;
  }

  function decorateElement(el, icon) {
    if (el.querySelector('i, svg, img')) return;
    if (el.dataset.wineAction) return;
    el.dataset.wineAction = '1';
    el.insertAdjacentHTML('afterbegin', '<i class="' + icon + ' mr-1"></i>');
  }

  function decorateInput(input) {
    if (input.type !== 'submit') return;
    if (input.parentElement && input.parentElement.querySelector('i')) return;
    if (input.dataset.wineAction) return;
    var label = input.value || input.getAttribute('value');
    var icon = findIcon(normalise(label));
    if (!icon) return;

    var btn = document.createElement('button');
    btn.type = 'submit';
    btn.name = input.name || '';
    btn.value = input.value || '';
    btn.className = input.className || '';
    btn.dataset.wineAction = '1';
    btn.title = label;
    btn.innerHTML = '<i class="' + icon + ' mr-1"></i> ' + label;
    input.parentNode.replaceChild(btn, input);
  }

  function applyActions(root) {
    if (!root) return;

    root.querySelectorAll('button.btn, a.btn').forEach(function (el) {
      if (el.closest('.sb-fav-btn')) return;
      var text = el.textContent;
      if (!text || !text.trim()) return;
      var icon = findIcon(normalise(text));
      if (icon) decorateElement(el, icon);
    });

    root.querySelectorAll('input.btn, input[type="submit"]').forEach(decorateInput);
  }

  function init() {
    applyActions(document.body);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();