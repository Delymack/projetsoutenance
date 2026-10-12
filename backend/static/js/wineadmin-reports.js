(function () {
  'use strict';

  var root = document.getElementById('wine-reports');
  if (!root) return;

  var form = document.getElementById('report-filters');
  var start = document.getElementById('report-start');
  var end = document.getElementById('report-end');
  var grouping = document.getElementById('report-group');
  var message = document.getElementById('report-message');
  var apiUrl = root.dataset.apiUrl;
  var currency = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 });
  var labels = {
    periode: 'Période',
    vin: 'Vin',
    categorie: 'Catégorie',
    vendeur: 'Vendeur',
    ventes: 'Ventes',
    quantite: 'Quantité',
    chiffre_affaires: "Chiffre d'affaires",
    panier_moyen: 'Panier moyen'
  };

  function isoDate(date) {
    var local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
    return local.toISOString().slice(0, 10);
  }

  function montant(value) {
    var number = Number(value || 0);
    return currency.format(Number.isFinite(number) ? number : 0) + ' Ar';
  }

  function setText(id, value) {
    document.getElementById(id).textContent = value;
  }

  function fillTable(headId, bodyId, rows, columns) {
    var head = document.getElementById(headId);
    var body = document.getElementById(bodyId);
    head.replaceChildren();
    body.replaceChildren();
    columns.forEach(function (column) {
      var cell = document.createElement('th');
      cell.scope = 'col';
      cell.textContent = labels[column] || column;
      head.appendChild(cell);
    });
    if (!rows.length) {
      var empty = document.createElement('tr');
      var cell = document.createElement('td');
      cell.colSpan = columns.length;
      cell.textContent = 'Aucune donnée pour cette période.';
      empty.appendChild(cell);
      body.appendChild(empty);
      return;
    }
    rows.forEach(function (row) {
      var tr = document.createElement('tr');
      columns.forEach(function (column) {
        var td = document.createElement('td');
        var value = row[column];
        td.textContent = ['chiffre_affaires', 'panier_moyen', 'remise_accordee', 'chiffre_affaires_net'].indexOf(column) !== -1
          ? montant(value)
          : (value == null ? '—' : String(value));
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
  }

  function queryString(format) {
    var params = new URLSearchParams({
      debut: start.value,
      fin: end.value,
      par: grouping.value
    });
    if (format) params.set('format', format);
    return params.toString();
  }

  function updateExportLinks() {
    ['csv', 'xlsx', 'pdf'].forEach(function (format) {
      document.getElementById('report-' + format).href = apiUrl + '?' + queryString(format);
    });
  }

  function loadReport() {
    if (!form.reportValidity()) return;
    if (start.value > end.value) {
      message.textContent = 'La date de début doit précéder ou égaler la date de fin.';
      message.classList.add('is-error');
      return;
    }
    updateExportLinks();
    message.classList.remove('is-error');
    message.textContent = 'Chargement du rapport…';

    fetch(apiUrl + '?' + queryString(), {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' }
    }).then(function (response) {
      if (!response.ok) {
        return response.json().catch(function () { return {}; }).then(function (body) {
          throw new Error(body.erreur || 'Le rapport n’a pas pu être chargé (' + response.status + ').');
        });
      }
      return response.json();
    }).then(function (data) {
      setText('kpi-sales', currency.format(data.ventes || 0));
      setText('kpi-revenue', montant(data.chiffre_affaires));
      setText('kpi-stock', currency.format(data.stock_unites || 0));
      setText('kpi-stock-value', montant(data.valeur_stock));
      setText('report-period', data.debut + ' — ' + data.fin);
      var rows = data.donnees || [];
      var columns = rows.length
        ? Object.keys(rows[0])
        : (['jour', 'semaine', 'mois', 'annee'].indexOf(data.par) !== -1
          ? ['periode', 'ventes', 'chiffre_affaires', 'panier_moyen']
          : [data.par, 'ventes', 'quantite', 'chiffre_affaires']);
      fillTable('sales-head', 'sales-body', rows, columns);

      var promotions = data.promotions || {};
      setText('promo-sales', currency.format(promotions.ventes || 0));
      setText('promo-discount', montant(promotions.remise_accordee));
      setText('promo-revenue', montant(promotions.chiffre_affaires_net));
      setText('promo-rate', String(promotions.taux_remise_pct || '0.00'));
          fillTable('promotions-table-head', 'promotions-body', promotions.donnees || [], [
        'promotion', 'ventes', 'lignes', 'remise_accordee', 'chiffre_affaires_net'
      ]);
      message.textContent = 'Rapport mis à jour.';
    }).catch(function (error) {
      message.textContent = error.message;
      message.classList.add('is-error');
    });
  }

  var promotionHead = document.querySelector('#promotions-table thead tr');
  promotionHead.replaceChildren();
  ['Promotion', 'Ventes', 'Lignes', 'Remise accordée', "Chiffre d'affaires net"].forEach(function (label) {
    var cell = document.createElement('th');
    cell.scope = 'col';
    cell.textContent = label;
    promotionHead.appendChild(cell);
  });
  labels.promotion = 'Promotion';
  labels.lignes = 'Lignes';
  labels.remise_accordee = 'Remise accordée';
  labels.chiffre_affaires_net = "Chiffre d'affaires net";

  var today = new Date();
  start.value = isoDate(new Date(today.getFullYear(), today.getMonth(), 1));
  end.value = isoDate(today);
  form.addEventListener('submit', function (event) {
    event.preventDefault();
    loadReport();
  });
  document.getElementById('report-print').addEventListener('click', function () {
    window.print();
  });
  updateExportLinks();
  loadReport();
}());
