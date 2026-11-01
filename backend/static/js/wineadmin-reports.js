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

  function svgNode(name, attributes, text) {
    var node = document.createElementNS('http://www.w3.org/2000/svg', name);
    Object.keys(attributes || {}).forEach(function (key) {
      node.setAttribute(key, attributes[key]);
    });
    if (text) node.textContent = text;
    return node;
  }

  function chartLabel(row, groupingValue) {
    var value = row.periode || row[groupingValue] || '';
    if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value.slice(5).replace('-', '/');
    if (/^\d{4}-\d{2}$/.test(value)) return value.slice(5) + '/' + value.slice(0, 4);
    if (/^\d{4}-\d{2}-\d{2}T/.test(value)) return value.slice(5, 10).replace('-', '/');
    return String(value);
  }

  function renderChart(rows, groupingValue) {
    var svg = document.getElementById('report-chart');
    svg.replaceChildren();
    if (!rows.length) {
      svg.appendChild(svgNode('text', {
        'class': 'report-chart-empty',
        x: 360,
        y: 135,
        'text-anchor': 'middle'
      }, 'Aucune donnée pour cette période.'));
      return;
    }

    var values = rows.map(function (row) {
      var value = Number(row.chiffre_affaires);
      return Number.isFinite(value) ? Math.max(value, 0) : 0;
    });
    var maxValue = Math.max.apply(null, values) || 1;
    var ceiling = maxValue * 1.12;
    var left = 66;
    var right = 704;
    var top = 20;
    var bottom = 220;
    var width = right - left;
    var height = bottom - top;
    var points = values.map(function (value, index) {
      return {
        x: left + (values.length > 1 ? index * width / (values.length - 1) : width / 2),
        y: bottom - (value / ceiling) * height,
        value: value,
        row: rows[index]
      };
    });

    var defs = svgNode('defs');
    var gradient = svgNode('linearGradient', { id: 'report-chart-gradient', x1: 0, x2: 0, y1: 0, y2: 1 });
    gradient.appendChild(svgNode('stop', { offset: '0%', 'stop-color': '#efbd4f', 'stop-opacity': '.28' }));
    gradient.appendChild(svgNode('stop', { offset: '100%', 'stop-color': '#efbd4f', 'stop-opacity': '.015' }));
    defs.appendChild(gradient);
    svg.appendChild(defs);

    [0, .5, 1].forEach(function (fraction) {
      var y = bottom - fraction * height;
      svg.appendChild(svgNode('line', {
        'class': 'report-chart-grid',
        x1: left,
        x2: right,
        y1: y,
        y2: y
      }));
      svg.appendChild(svgNode('text', {
        'class': 'report-chart-axis',
        x: left - 10,
        y: y + 4,
        'text-anchor': 'end'
      }, currency.format(Math.round(ceiling * fraction))));
    });

    var linePath = points.map(function (point, index) {
      return (index ? 'L' : 'M') + point.x.toFixed(1) + ' ' + point.y.toFixed(1);
    }).join(' ');
    var areaPath = linePath + ' L' + points[points.length - 1].x.toFixed(1) + ' ' + bottom +
      ' L' + points[0].x.toFixed(1) + ' ' + bottom + ' Z';
    svg.appendChild(svgNode('path', { 'class': 'report-chart-area', d: areaPath }));
    svg.appendChild(svgNode('path', { 'class': 'report-chart-line', d: linePath }));

    var labelIndices = [];
    var labelCount = Math.min(points.length, 6);
    for (var labelIndex = 0; labelIndex < labelCount; labelIndex += 1) {
      labelIndices.push(labelCount === 1
        ? 0
        : Math.round(labelIndex * (points.length - 1) / (labelCount - 1)));
    }
    labelIndices.forEach(function (index) {
      var point = points[index];
      svg.appendChild(svgNode('text', {
        'class': 'report-chart-axis',
        x: point.x,
        y: 246,
        'text-anchor': 'middle'
      }, chartLabel(point.row, groupingValue)));
    });

    var pointStride = Math.max(1, Math.ceil(points.length / 28));
    points.forEach(function (point, index) {
      if (index % pointStride !== 0 && index !== points.length - 1) return;
      var circle = svgNode('circle', {
        'class': 'report-chart-point',
        cx: point.x,
        cy: point.y,
        r: 4
      });
      circle.appendChild(svgNode('title', {}, chartLabel(point.row, groupingValue) + ' : ' + montant(point.value)));
      svg.appendChild(circle);
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
      renderChart(rows, data.par);

      var promotions = data.promotions || {};
      setText('promo-sales', currency.format(promotions.ventes || 0));
      setText('promo-discount', montant(promotions.remise_accordee));
      var meilleurePeriode = rows.reduce(function (best, row) {
        return !best || Number(row.chiffre_affaires) > Number(best.chiffre_affaires) ? row : best;
      }, null);
      setText('promo-revenue', meilleurePeriode
        ? chartLabel(meilleurePeriode, data.par) + ' · ' + montant(meilleurePeriode.chiffre_affaires)
        : '—');
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
