(function () {
  'use strict';

  function colonneAction(th) {
    const classes = Array.from(th.classList);
    return classes.some((nom) =>
      /^(column-)?(action-checkbox(?:-column)?|.*actions?_col|contact_actions)$/.test(nom)
    ) || th.textContent.trim().toLocaleLowerCase('fr') === 'actions';
  }

  function ouvrirImpression(table) {
    const fenetre = window.open('', '_blank', 'popup,width=1100,height=800');
    if (!fenetre) {
      window.alert("Autorisez les fenêtres contextuelles pour imprimer cette liste.");
      return;
    }

    fenetre.opener = null;
    const doc = fenetre.document;
    doc.documentElement.lang = document.documentElement.lang || 'fr';
    doc.title = document.querySelector('.client-list-toolbar h1, .app-content-header h3')?.textContent.trim()
      || document.title.split('|')[0].trim();

    const style = doc.createElement('style');
    style.textContent = `
      @page { size: A4 landscape; margin: 12mm; }
      * { box-sizing: border-box; }
      body { color: #202027; font: 10pt/1.4 Arial, sans-serif; margin: 0; }
      header { border-bottom: 2px solid #641b2c; margin-bottom: 14px; padding-bottom: 9px; }
      h1 { color: #641b2c; font-size: 19pt; margin: 0 0 4px; }
      p { color: #555; font-size: 9pt; margin: 0; }
      table { border-collapse: collapse; table-layout: auto; width: 100%; }
      thead { display: table-header-group; }
      tr { break-inside: avoid; page-break-inside: avoid; }
      th, td { border: 1px solid #b8b8b8; color: #202027; padding: 6px 7px; text-align: left; vertical-align: top; }
      th { background: #f1e9e5; color: #38131f; font-weight: 700; }
      tbody tr:nth-child(even) { background: #faf8f7; }
      a { color: inherit; text-decoration: none; }
      @media print { body { print-color-adjust: exact; -webkit-print-color-adjust: exact; } }
    `;
    doc.head.appendChild(style);

    const header = doc.createElement('header');
    const title = doc.createElement('h1');
    title.textContent = doc.title;
    const details = doc.createElement('p');
    const lignes = table?.tBodies[0]?.rows.length || 0;
    details.textContent = `${lignes} ligne${lignes === 1 ? '' : 's'} · Imprimé le ${new Intl.DateTimeFormat('fr-FR', {
      dateStyle: 'short',
      timeStyle: 'short',
    }).format(new Date())}`;
    header.append(title, details);
    doc.body.replaceChildren(header);

    if (!table) {
      const empty = doc.createElement('p');
      empty.textContent = 'Aucun résultat à imprimer.';
      doc.body.appendChild(empty);
      fenetre.focus();
      window.setTimeout(() => {
        fenetre.print();
        fenetre.close();
      }, 250);
      return;
    }

    const copie = table.cloneNode(true);
    const entetes = Array.from(copie.tHead?.rows[0]?.cells || []);
    const indices = entetes
      .map((cellule, index) => colonneAction(cellule) ? index : -1)
      .filter((index) => index >= 0)
      .sort((a, b) => b - a);

    indices.forEach((index) => {
      Array.from(copie.rows).forEach((ligne) => ligne.cells[index]?.remove());
    });

    copie.querySelectorAll('input, button, select, textarea, .databtn-group, .fa-sort-alpha-down, .fa-sort-alpha-up')
      .forEach((element) => element.remove());
    copie.querySelectorAll('a').forEach((lien) => {
      lien.replaceWith(doc.createTextNode(lien.textContent.trim()));
    });
    doc.body.appendChild(copie);
    fenetre.focus();
    window.setTimeout(() => {
      fenetre.print();
      fenetre.close();
    }, 250);
  }

  document.addEventListener('click', (event) => {
    const bouton = event.target.closest('[data-admin-print-list]');
    if (!bouton) return;
    event.preventDefault();
    const table = document.querySelector('#result_list');
    ouvrirImpression(table);
  });
})();
