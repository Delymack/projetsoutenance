/* =========================================================================
   Cave & Or — Poste de caisse
   Le comptoir est bruyant et pressé : tout ce qui n'est pas immédiatement
   lisible fait perdre une vente. D'où des chiffres larges, des cibles de 44 px,
   et le bip qui confirme chaque scan sans qu'il faille regarder l'écran.
   ========================================================================= */
(function () {
  'use strict';

  const API = {
    produits: '/api/produits/',
    clients: '/api/clients/',
    categories: '/api/categories/',
    ventes: '/api/ventes/',
    simulerPromo: '/api/promotions/simuler/',
    caisseEtat: '/api/caisse/etat/',
    caisseRapport: '/api/caisse/rapport/',
    caisseOuvrir: '/api/caisse/ouvrir/',
    caisseCloturer: '/api/caisse/cloturer/',
  };
  const STORAGE = {
    sound: 'caveor-pos-sound',
    dense: 'caveor-pos-dense',
    seen: 'caveor-pos-first',
  };
  // Les moyens de paiement viennent du gabarit (Vente.ModePaiement.MODES_CAISSE) :
  // une seule source de vérité, le modèle.
  const MODES = [...document.querySelectorAll('#payment-pills button[data-mode]')].map((b) => b.dataset.mode);
  const CATEGORIES_SANS_FILTRE = new Set(['liqueurs & apéritifs', 'mousseux']);
  const ICONES_MODE = { ESPECES: 'fa-money-bill-wave', MVOLA: 'fa-mobile-screen', ORANGE_MONEY: 'fa-mobile-screen',
                        AIRTEL_MONEY: 'fa-mobile-screen', MOBILE_MONEY: 'fa-mobile-screen', CHEQUE: 'fa-file-signature',
                        CARTE: 'fa-credit-card', CREDIT: 'fa-book' };
  // Un opérateur de mobile money ou un chèque exige une référence : sans elle,
  // le rapprochement avec l'opérateur est impossible à la clôture.
  const MODES_A_REFERENCE = ['MVOLA', 'ORANGE_MONEY', 'AIRTEL_MONEY', 'MOBILE_MONEY', 'CHEQUE'];

  const $ = (id) => document.getElementById(id);
  const meta = new Map();

  let produits = [];
  let clients = [];
  let categories = [];
  let panier = {};
  let categorieActive = null;
  let modePaiement = MODES[0] || 'ESPECES';
  let contexte = {};
  let devisTmp = 'Ar';
  let sonActif = false;
  let venteCourante = null;
  let simulationPromo = null;
  let simulationEnCours = false;
  let simulationErreur = false;
  let simulationVersion = 0;
  let simulationMinuteur = null;
  let catalogueVersion = 0;
  // Pavé numérique / coupures rapides dépliés ? Au montant exact ils restent
  // repliés : la caisse s'encaisse sans encombrer l'écran.
  let extrasOuverts = false;

  /* ---------------------------------------------------------------- outils */
  const nf = new Intl.NumberFormat('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmt = (v) => nf.format(Number(v || 0));
  const dev = (v) => `${fmt(v)} ${devisTmp}`.trim();
  const num = (v) => {
    const n = parseFloat(String(v ?? '').replace(/\s/g, '').replace(',', '.'));
    return Number.isFinite(n) ? n : 0;
  };
  const esc = (v) =>
    String(v ?? '').replace(/[&<>'"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#039;', '"': '&quot;' }[c]));
  const cookie = (n) =>
    document.cookie.split(';').map((c) => c.trim()).find((c) => c.startsWith(n + '='))?.slice(n.length + 1) || '';

  async function api(url, options = {}) {
    const reponse = await fetch(url, {
      credentials: 'same-origin',
      ...options,
      headers: { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(options.headers || {}) },
    });
    let data = null;
    try { data = await reponse.json(); } catch (e) { data = null; }
    if (!reponse.ok) throw new Error(messageErreur(data, reponse.status));
    return data;
  }

  function messageErreur(data, status) {
    if (!data) return `Erreur ${status}.`;
    if (typeof data.errors === 'string') return data.errors;
    if (data.errors && typeof data.errors === 'object') {
      const premier = Object.values(data.errors)[0];
      if (Array.isArray(premier) && premier.length) return String(premier[0]);
      if (typeof premier === 'string') return premier;
    }
    return data.message || data.detail || data.erreur || `Erreur ${status}.`;
  }

  async function fetchAll(url) {
    const valeurs = [];
    let cible = url;
    while (cible) {
      const data = await api(cible);
      valeurs.push(...(data.results || data || []));
      cible = data.next || null;
    }
    return valeurs;
  }

  const CSRF = () => ({ 'X-CSRFToken': cookie('csrftoken') });

  function notice(message, type = 'error') {
    const el = $('notice');
    el.textContent = message;
    el.className = 'notice ' + type;
  }
  function effacerNotice() {
    const el = $('notice');
    el.textContent = '';
    el.className = 'notice';
  }

  function toast(message, kind = 'info') {
    const el = document.createElement('div');
    el.className = 'pos-toast ' + kind;
    el.innerHTML = message;
    $('pos-toasts').appendChild(el);
    setTimeout(() => { el.className += ' out'; setTimeout(() => el.remove(), 260); }, 2800);
  }

  function bip(ok = true) {
    if (!sonActif) return;
    try {
      const ctx = bip.ctx || (bip.ctx = new (window.AudioContext || window.webkitAudioContext)());
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.value = ok ? 880 : 320;
      gain.gain.setValueAtTime(0.001, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.12, ctx.currentTime + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.16);
      osc.connect(gain); gain.connect(ctx.destination);
      osc.start(); osc.stop(ctx.currentTime + 0.17);
    } catch (e) { /* audio indisponible : on ne bloque pas la vente */ }
  }

  /* --------------------------------------------------------------- horloge */
  function horloge() {
    $('pos-clock').textContent = new Date().toLocaleTimeString('fr-FR', { hour12: false });
  }
  setInterval(horloge, 1000);
  horloge();

  $('fullscreen-toggle').addEventListener('click', () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen().catch(() => {});
  });

  function syncSon() {
    $('sound-toggle').innerHTML = sonActif ? '<i class="fas fa-volume-up"></i>' : '<i class="fas fa-volume-mute"></i>';
    $('sound-toggle').title = sonActif ? 'Couper le bip' : 'Activer le bip';
    $('sound-toggle').classList.toggle('active', sonActif);
  }
  $('sound-toggle').addEventListener('click', () => {
    sonActif = !sonActif;
    try { localStorage.setItem(STORAGE.sound, sonActif ? '1' : '0'); } catch (e) {}
    syncSon();
    if (sonActif) bip(true);
  });
  try { sonActif = localStorage.getItem(STORAGE.sound) === '1'; } catch (e) {}
  syncSon();

  /* ------------------------------------------------------- mode DENSE/PHOTO */
  function appliquerDensite() {
    let dense = true;
    try { dense = localStorage.getItem(STORAGE.dense) !== '0'; } catch (e) {}
    $('pos-root').classList.toggle('dense', dense);
    $('layout-toggle').innerHTML = dense ? '<i class="fas fa-table-cells"></i>' : '<i class="fas fa-image"></i>';
    $('layout-toggle').title = dense ? 'Vue PHOTO (reconnaître les bouteilles)' : 'Vue DENSE (maximiser les références)';
    $('layout-toggle').classList.toggle('active', !dense);
  }
  $('layout-toggle').addEventListener('click', () => {
    const dense = $('pos-root').classList.contains('dense');
    try { localStorage.setItem(STORAGE.dense, dense ? '0' : '1'); } catch (e) {}
    appliquerDensite();
  });
  appliquerDensite();

  /* ------------------------------------------------------------ chargement */
  async function charger() {
    try {
      contexte = await api(API.caisseEtat);
      devisTmp = contexte.devise || 'Ar';
      majSession();

      [produits, clients, categories] = await Promise.all([
        fetchAll(API.produits), fetchAll(API.clients), fetchAll(API.categories),
      ]);
      produits.forEach((p) => {
        const promo = infoPromo(p);
        meta.set(p.id, {
          promo,
          prix: promo ? Number(promo.prix_final) : Number(p.prix_unitaire_vente),
        });
      });
      rendreCategories();
      rendreClients();
      rendreProduits();
      majCompteurPromos();
      $('search-input').focus();
      if (!localStorage.getItem(STORAGE.seen)) {
        localStorage.setItem(STORAGE.seen, '1');
        toast('<i class="fas fa-check-circle mr-1"></i>Caisse prête. Scannez ou cliquez un vin.', 'green');
      }
    } catch (e) {
      $('product-count').textContent = 'Le catalogue ne peut pas être chargé.';
      notice(e.message);
    }
  }

  function infoPromo(p) {
    const promo = p && p.promotion_active;
    if (!promo) return null;
    const prix = Number(p.prix_unitaire_vente);
    const final = Number(promo.prix_final);
    if (!(final > 0) || final >= prix) return null;
    return {
      nom: promo.nom,
      prix_final: final,
      remise: prix - final,
      etiquette: promo.type === 'POURCENTAGE' ? `-${Number(promo.valeur)}%` : 'Promo',
    };
  }

  function majCompteurPromos() {
    const n = produits.filter((p) => meta.get(p.id)?.promo).length;
    $('hstat-promos').innerHTML = `<i class="fas fa-bolt"></i>${n} promo`;
  }

  async function actualiserCatalogueClient() {
    const version = ++catalogueVersion;
    const clientId = $('client-select').value;
    const url = new URL(API.produits, window.location.origin);
    if (clientId) url.searchParams.set('client', clientId);
    try {
      const nouveauxProduits = await fetchAll(url.pathname + url.search);
      if (version !== catalogueVersion) return;
      produits = nouveauxProduits;
      meta.clear();
      produits.forEach((p) => {
        const promo = infoPromo(p);
        meta.set(p.id, {
          promo,
          prix: promo ? Number(promo.prix_final) : Number(p.prix_unitaire_vente),
        });
      });
      rendreProduits();
      majCompteurPromos();
    } catch (e) {
      if (version === catalogueVersion) notice(`Prix du catalogue non actualisés : ${e.message}`);
    }
  }

  /* ---------------------------------------------------------------- session */
  function majSession() {
    const s = contexte.session;
    const pill = $('pill-session');
    const chip = $('cashier-chip');
    const bloque = contexte.session_requise && !s;

    pill.className = 'pos-status-pill ' + (!bloque ? 'success' : 'bad');
    if (!contexte.session_requise) {
      pill.querySelector('span').textContent = 'Session non requise';
    } else if (s) {
      pill.querySelector('span').textContent = `Caisse ouverte · ${fmt(s.fonds_de_caisse)} ${devisTmp}`;
    } else {
      pill.querySelector('span').textContent = 'Caisse fermée';
    }

    if (s && s.utilisateur) {
      const u = s.utilisateur;
      chip.classList.remove('bad');
      chip.innerHTML = `<i class="fas fa-user-tie"></i> ${esc(u.full_name || u.username)}`;
    } else if (bloque) {
      chip.classList.add('bad');
      chip.innerHTML = '<i class="fas fa-user-tie"></i> Session à ouvrir';
    } else {
      chip.classList.remove('bad');
    }

    $('session-block').classList.toggle('on', !!bloque);
    majEtatEncaissement();
  }

  function sessionBloquee() {
    return !!(contexte.session_requise && !contexte.session);
  }

  function majEtatEncaissement() {
    const bloquant = sessionBloquee() || simulationEnCours || simulationErreur
      || (Object.keys(panier).length > 0 && !simulationPromo);
    $('checkout-btn').disabled = bloquant || !MODES.length || !Object.keys(panier).length;
  }

  $('session-open').addEventListener('click', async () => {
    const fonds = num($('session-fonds').value);
    const btn = $('session-open');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i> Ouverture…';
    try {
      const data = await api(API.caisseOuvrir, {
        method: 'POST',
        headers: CSRF(),
        body: JSON.stringify({ fonds_initial: fonds }),
      });
      contexte = data.contexte;
      majSession();
      bip(true);
      toast('<i class="fas fa-unlock mr-1"></i>Caisse ouverte.', 'green');
    } catch (e) {
      bip(false);
      notice(e.message);
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<i class="fas fa-unlock mr-1"></i> Ouvrir la caisse';
    }
  });

  /* -------------------------------------------------------------- catégories */
  function rendreCategories() {
    const visibles = categories.filter((c) => (
      c.statut && !CATEGORIES_SANS_FILTRE.has(String(c.nom || '').trim().toLocaleLowerCase('fr-FR'))
    ));
    const html = ['<button type="button" class="category active" data-cat="">Tout le catalogue</button>']
      .concat(visibles.map((c) => `<button type="button" class="category" data-cat="${c.id}">${esc(c.nom)}</button>`))
      .join('');
    $('category-list').innerHTML = html;
  }

  $('category-list').addEventListener('click', (e) => {
    const btn = e.target.closest('.category');
    if (!btn) return;
    categorieActive = btn.dataset.cat ? Number(btn.dataset.cat) : null;
    $('category-list').querySelectorAll('.category').forEach((b) => b.classList.toggle('active', b === btn));
    rendreProduits();
  });

  /* --------------------------------------------------------------- produits */
  function produitsVisibles() {
    const q = $('search-input').value.trim().toLowerCase();
    const quePromos = $('promo-only').classList.contains('active');
    return produits.filter((p) => {
      if (!p.statut) return false;
      if (quePromos && !meta.get(p.id)?.promo) return false;
      if (categorieActive && p.categorie !== categorieActive) return false;
      if (!q) return true;
      const nomCategorie = categories.find((c) => String(c.id) === String(p.categorie))?.nom;
      const cible = [p.nom, p.marque, p.millesime, p.code_barre, p.reference, p.conditionnement_libelle, nomCategorie]
        .filter(Boolean).join(' ').toLowerCase();
      return cible.includes(q);
    });
  }

  function stockDe(p) {
    if (p.stock_quantite !== undefined && p.stock_quantite !== null) return Number(p.stock_quantite);
    return 0;
  }

  function rendreProduits() {
    const liste = produitsVisibles();
    $('product-count').innerHTML = `<b>${liste.length}</b> référence${liste.length > 1 ? 's' : ''} affichée${liste.length > 1 ? 's' : ''}`;

    if (!liste.length) {
      $('product-list').innerHTML = '<div class="empty" style="grid-column:1/-1">Aucune référence ne correspond.</div>';
      return;
    }

    $('product-list').innerHTML = liste.map((p) => {
      const info = meta.get(p.id) || {};
      const stock = stockDe(p);
      const dansPanier = panier[p.id];
      const stockCls = stock <= 0 ? 'out-stock' : stock <= 6 ? 'low-stock' : 'in-stock';
      const stockTxt = stock <= 0 ? 'Rupture' : `${stock} dispo`;
      const image = p.image_url
        ? `<img src="${esc(p.image_url)}" alt="" loading="lazy" onerror="this.closest('.product-thumb').innerHTML='<i class=\\'fas fa-wine-bottle\\'></i>'">`
        : '<i class="fas fa-wine-bottle"></i>';
      return `
        <button type="button" class="product${info.promo ? ' promo' : ''}" data-id="${p.id}" ${stock <= 0 ? 'disabled' : ''}
                title="${esc(p.nom)} — ${esc(stockTxt)}">
          <span class="cart-qty${dansPanier ? ' on' : ''}" data-qty="${p.id}">${dansPanier ? dansPanier.quantite : ''}</span>
          ${info.promo ? '<span class="promo-badge">PROMO</span>' : ''}
          <span class="product-body">
            <span class="product-thumb${info.promo ? ' thumb-promo' : ''}">${image}${info.promo ? `<i>${info.promo.etiquette}</i>` : ''}</span>
            <span class="product-name">${esc(p.nom)}</span>
            <span class="product-brand">${esc(p.marque || p.conditionnement_libelle || '')}</span>
            <span class="product-bottom">
              <span class="price-wrap">
                ${info.promo
                  ? `<span class="price-promo">${fmt(info.promo.prix_final)}</span><span class="price-original">${fmt(p.prix_unitaire_vente)}</span>`
                  : `<span class="price">${fmt(p.prix_unitaire_vente)}</span>`}
              </span>
              <span class="stock ${stockCls}">${stockTxt}</span>
            </span>
          </span>
        </button>`;
    }).join('');
  }

  $('product-list').addEventListener('click', (e) => {
    const card = e.target.closest('.product');
    if (!card || card.disabled) return;
    ajouter(Number(card.dataset.id));
  });

  $('search-clear').addEventListener('click', () => {
    $('search-input').value = '';
    rendreProduits();
    $('search-input').focus();
  });
  ['promo-only'].forEach((id) => {
    $(id).addEventListener('click', () => {
      $(id).classList.toggle('active');
      rendreProduits();
    });
  });

  /* ----------------------------------------------------------------- panier */
  function produit(id) { return produits.find((p) => p.id === id); }

  function ajouter(id, quantite = 1) {
    const p = produit(id);
    if (!p) return;
    if (sessionBloquee()) { notice('Ouvrez la caisse avant d\'encaisser.'); bip(false); return; }
    const stock = stockDe(p);
    const ligne = panier[id];
    if (ligne && ligne.quantite + quantite > stock) {
      notice(`Stock insuffisant : ${stock} unité(s) disponible(s) pour ${p.nom}.`);
      bip(false);
      return;
    }
    if (!ligne) {
      panier[id] = { id, quantite, unite: p.unite_vente || 'BOUTEILLE', remise_manuelle: 0 };
    } else {
      ligne.quantite += quantite;
    }
    bip(true);
    const badge = $('product-list').querySelector(`[data-qty="${id}"]`);
    if (badge) {
      badge.textContent = panier[id].quantite;
      badge.classList.add('on', 'qty-flash');
      setTimeout(() => badge.classList.remove('qty-flash'), 500);
    }
    rendrePanier();
  }

  function setQuantite(id, valeur) {
    const ligne = panier[id];
    if (!ligne) return;
    const p = produit(id);
    const max = p ? stockDe(p) : ligne.quantite;
    const q = Math.max(1, Math.min(max, valeur || 1));
    if (q < valeur) notice(`Maximum ${max} unité(s) en stock.`);
    ligne.quantite = q;
    rendrePanier();
  }

  function simulationLigne(id) {
    return simulationPromo?.lignes?.find((l) => Number(l.produit_id) === Number(id));
  }

  function prixLigne(ligne) {
    const simulation = simulationLigne(ligne.id);
    if (simulation) return Number(simulation.prix_ligne);
    const info = meta.get(ligne.id) || {};
    const brut = (info.prix || 0) * ligne.quantite;
    return Math.max(0, brut - (ligne.remise_manuelle || 0));
  }

  function totalPanier() {
    if (simulationPromo) return Number(simulationPromo.total);
    return Object.values(panier).reduce((s, l) => s + prixLigne(l), 0);
  }

  function economies() {
    if (simulationPromo) return Number(simulationPromo.remise_totale || 0);
    let eco = 0;
    Object.values(panier).forEach((l) => {
      const info = meta.get(l.id) || {};
      if (info.promo) eco += info.promo.remise * l.quantite;
      eco += l.remise_manuelle || 0;
    });
    return eco;
  }

  function rendrePanier(simuler = true) {
    const lignes = Object.values(panier);
    const badge = $('items-count');
    badge.textContent = lignes.length;
    badge.classList.add('pop');
    setTimeout(() => badge.classList.remove('pop'), 350);

    if (!lignes.length) {
      $('cart-items').innerHTML = '<div class="empty"><i class="fas fa-shopping-basket d-block mb-2" style="font-size:1.4rem"></i>Votre panier est vide.</div>';
    } else {
      $('cart-items').innerHTML = lignes.map((l) => {
        const p = produit(l.id);
        const info = meta.get(l.id) || {};
        const simulation = simulationLigne(l.id);
        const promoNom = simulationPromo
          ? (simulation?.promotion || '')
          : (simulationEnCours ? '' : (info.promo?.nom || ''));
        const isPromo = simulationPromo
          ? Boolean(simulation?.promotion)
          : (!simulationEnCours && Boolean(info.promo));
        const brut = simulation
          ? Number(simulation.brut_ligne)
          : (info.prix || 0) * l.quantite;
        return `
          <div class="cart-item" data-id="${l.id}">
            <div class="item-top">
              <span>
                <span class="item-name">${esc(p.nom)}</span>
                ${promoNom ? `<div class="item-promo"><i class="fas fa-tag"></i> ${esc(promoNom)}</div>` : ''}
                ${l.remise_manuelle > 0 ? `<div class="item-remise">Remise ${fmt(l.remise_manuelle)}</div>` : ''}
              </span>
              <button type="button" class="remove" data-action="remove" aria-label="Retirer"><i class="fas fa-times"></i></button>
            </div>
            <div class="item-bottom">
              <span class="quantity">
                <button type="button" class="qty-btn" data-action="minus" aria-label="Moins"><i class="fas fa-minus"></i></button>
                <input class="qty-input" type="number" min="1" value="${l.quantite}" aria-label="Quantité">
                <button type="button" class="qty-btn" data-action="plus" aria-label="Plus"><i class="fas fa-plus"></i></button>
              </span>
              <span class="${isPromo ? 'subtotal-promo' : 'subtotal'}">${fmt(prixLigne(l))}</span>
            </div>
            <div class="line-tools">
              <button type="button" data-action="remise" ${contexte.peut_remettre ? '' : 'disabled'} title="Remise sur la ligne">
                <i class="fas fa-percent"></i> Remise
              </button>
              <button type="button" data-action="unite" title="Changer l'unité de vente">
                <i class="fas fa-cubes"></i> ${esc( uniteLabel(l.unite) )}
              </button>
            </div>
            ${brut !== prixLigne(l) ? `<div class="item-remise" style="margin-top:.25rem">Brut ${fmt(brut)}</div>` : ''}
          </div>`;
      }).join('');
    }

    const total = totalPanier();
    const eco = economies();
    $('cart-total').textContent = fmt(total);
    $('cart-total').classList.toggle('is-promo', eco > 0);
    $('savings-row').style.display = eco > 0 ? '' : 'none';
    $('savings-amount').textContent = `- ${fmt(eco)}`;
    $('hstat-savings').style.display = eco > 0 ? '' : 'none';
    $('hstat-savings-txt').textContent = `-${fmt(eco)}`;

    $('open-retour').disabled = false;
    $('open-remise').disabled = !lignes.length || !contexte.peut_remettre;
    if (simuler) programmerSimulationPromotions();
    majEtatEncaissement();
    rendreProduits();
  }

  function programmerSimulationPromotions() {
    const version = ++simulationVersion;
    clearTimeout(simulationMinuteur);
    simulationPromo = null;
    simulationErreur = false;
    simulationEnCours = Object.keys(panier).length > 0;
    const feedback = $('promo-code-feedback');
    if (feedback) {
      feedback.className = 'promo-code-feedback';
      feedback.textContent = simulationEnCours ? 'Calcul des offres…' : '';
    }
    if (!simulationEnCours) {
      majEtatEncaissement();
      majAffichagePanier();
      return;
    }
    majEtatEncaissement();
    simulationMinuteur = setTimeout(async () => {
      const clientId = $('client-select').value;
      const corps = {
        client: clientId ? Number(clientId) : null,
        lignes: Object.values(panier).map((l) => ({
          produit_id: l.id,
          quantite: l.quantite,
          unite: l.unite,
          remise_manuelle: Number(l.remise_manuelle || 0).toFixed(2),
        })),
      };
      try {
        const resultat = await api(API.simulerPromo, {
          method: 'POST',
          headers: CSRF(),
          body: JSON.stringify(corps),
        });
        if (version !== simulationVersion) return;
        simulationPromo = resultat;
        simulationEnCours = false;
        if (feedback) {
          feedback.className = 'promo-code-feedback success';
          feedback.textContent = 'Offres applicables recalculées sans code promotionnel.';
        }
        rendrePanier(false);
      } catch (e) {
        if (version !== simulationVersion) return;
        simulationEnCours = false;
        simulationErreur = true;
        simulationPromo = null;
        if (feedback) {
          feedback.className = 'promo-code-feedback error';
          feedback.textContent = e.message;
        }
        notice(e.message);
        majEtatEncaissement();
        majAffichagePanier();
      }
    }, 180);
  }

  function majAffichagePanier() {
    const total = totalPanier();
    const eco = economies();
    $('cart-total').textContent = fmt(total);
    $('cart-total').classList.toggle('is-promo', eco > 0);
    $('savings-row').style.display = eco > 0 ? '' : 'none';
    $('savings-amount').textContent = `- ${fmt(eco)}`;
    $('hstat-savings').style.display = eco > 0 ? '' : 'none';
    $('hstat-savings-txt').textContent = `-${fmt(eco)}`;
  }

  function uniteLabel(code) {
    const u = (contexte.conditions?.unites) || {};
    return u[code] || code || 'Unité';
  }

  $('cart-items').addEventListener('click', (e) => {
    const wrap = e.target.closest('.cart-item');
    if (!wrap) return;
    const id = Number(wrap.dataset.id);
    const action = e.target.closest('[data-action]')?.dataset.action;
    if (action === 'remove') {
      delete panier[id];
      rendrePanier();
    } else if (action === 'plus') {
      ajouter(id, 1);
    } else if (action === 'minus') {
      const l = panier[id];
      if (l.quantite <= 1) delete panier[id];
      else l.quantite -= 1;
      rendrePanier();
    } else if (action === 'remise') {
      ouvrirRemise(id);
    } else if (action === 'unite') {
      cycUnite(id);
    }
  });

  $('cart-items').addEventListener('change', (e) => {
    if (!e.target.classList.contains('qty-input')) return;
    const id = Number(e.target.closest('.cart-item').dataset.id);
    setQuantite(id, num(e.target.value));
  });

  function cycUnite(id) {
    const l = panier[id];
    const dispo = Object.keys(contexte.conditions?.unites || { BOUTEILLE: 1, PACK: 1, CARTON: 1 });
    l.unite = dispo[(dispo.indexOf(l.unite) + 1) % dispo.length];
    toast(`Unité : ${uniteLabel(l.unite)}`);
    rendrePanier();
  }

  /* ---------------------------------------------------------------- clients */
  // Nom libre du client de passage. Déclaré hors de `contexte` : cet objet est
  // rechargé depuis l'API et écraserait la saisie en cours.
  let clientLibelle = '';

  function rendreClients() {
    const sel = $('client-select');
    const courant = sel.value;
    sel.innerHTML = '<option value="">Client de passage</option>'
      + clients.map((c) => `<option value="${c.id}">${esc([c.nom, c.prenom].filter(Boolean).join(' '))}${c.niveau_label ? ' — ' + esc(c.niveau_label) : ''}</option>`)
      .join('');
    sel.value = courant;
    majClient();
  }

  function clientCourant() {
    return clients.find((c) => String(c.id) === $('client-select').value) || null;
  }

  function majClient() {
    const c = clientCourant();
    // Pas de fiche sélectionnée = client de passage : on propose de nommer la
    // vente, et ni fidélité ni encours ne s'appliquent.
    $('client-libelle-row').style.display = c ? 'none' : '';
    if (c) { $('client-libelle').value = ''; clientLibelle = ''; }
    const pts = $('pts-row');
    if (c && Number(c.points_fidelite) > 0) {
      pts.style.display = '';
      $('pts-amount').textContent = `${c.points_fidelite} pts`;
    } else {
      pts.style.display = 'none';
    }
    const hint = $('loyalty-hint');
    if (c && Number(c.max_credit) > 0) {
      hint.style.display = '';
      hint.innerHTML = `<i class="fas fa-book mr-1"></i>Compte autorisé : ${fmt(c.max_credit)} · dû actuel ${fmt(c.solde_du)}`;
    } else {
      hint.style.display = 'none';
    }
  }

  $('client-select').addEventListener('change', () => {
    majClient();
    actualiserCatalogueClient();
    programmerSimulationPromotions();
  });
  $('client-libelle').addEventListener('input', (e) => { clientLibelle = e.target.value.trim(); });

  /* -------------------------------------------------------------- recherche */
  let minuteurRecherche = null;
  $('search-input').addEventListener('input', () => {
    clearTimeout(minuteurRecherche);
    minuteurRecherche = setTimeout(rendreProduits, 120);
  });

  $('search-input').addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const q = $('search-input').value.trim();
    if (!q) return;
    // Un code barre scanné n'apparaît pas forcément dans le texte affiché :
    // on le cherche aussi dans le code produit avant de dire « inconnu ».
    const parCode = produits.find((p) => p.code_barre && String(p.code_barre).trim() === q);
    const liste = produitsVisibles();
    if (parCode) {
      ajouter(parCode.id);
      $('search-input').value = '';
      rendreProduits();
      return;
    }
    if (liste.length === 1) {
      ajouter(liste[0].id);
      $('search-input').value = '';
      rendreProduits();
      return;
    }
    if (liste.length > 1) {
      toast(`<i class="fas fa-list mr-1"></i>${liste.length} références : cliquez ou précisez.`, 'info');
    } else {
      bip(false);
      toast('<i class="fas fa-circle-xmark mr-1"></i>Aucune référence pour ce code.', 'red');
    }
  });

  /* -------------------------------------------------------- annulation panier */
  function annulerVente() {
    if (!Object.keys(panier).length) {
      notice('Aucune vente en cours à annuler.');
      return;
    }
    if (!confirm('Annuler la vente en cours ?')) return;
    panier = {};
    $('client-select').value = '';
    majClient();
    rendrePanier();
    effacerNotice();
  }

  $('cancel-sale').addEventListener('click', annulerVente);

  /* ------------------------------------------------------------ mode paiement */
  function setMode(mode) {
    modePaiement = mode;
    $('payment-pills').querySelectorAll('button').forEach((b) => b.classList.toggle('active', b.dataset.mode === mode));
  }
  $('payment-pills').addEventListener('click', (e) => {
    const btn = e.target.closest('button');
    if (btn) setMode(btn.dataset.mode);
  });

  /* --------------------------------------------------------------- encaissement */
  function ouvrirPaiement() {
    if (!MODES.length) {
      notice('Aucun moyen de paiement disponible. Contactez un administrateur.');
      return;
    }
    if (sessionBloquee()) { notice('Ouvrez la caisse avant d\'encaisser.'); bip(false); return; }
    if (!Object.keys(panier).length) { notice('Le panier est vide.'); return; }
    effacerNotice();

    const total = totalPanier();
    $('pay-total').textContent = fmt(total);
    $('pay-sub').textContent = `${Object.keys(panier).length} ligne(s) · ${Object.values(panier).reduce((n, l) => n + l.quantite, 0)} article(s)`;
    $('pay-method').querySelectorAll('button').forEach((b) => b.classList.toggle('active', b.dataset.mode === modePaiement));
    // En espèces, le total exact est pré-rempli : le caissier encaisse en deux
    // gestes (ouvrir, confirmer) sans rien taper. Les autres moyens valent le
    // montant exact par construction.
    $('cash-received').value = modePaiement === 'ESPECES' ? total.toFixed(2) : '';
    extrasOuverts = false;
    $('pay-reference').value = '';
    $('pay-reference').style.borderColor = 'var(--line)';
    $('change-box').style.display = 'none';
    $('confirm-pay').disabled = true;
    // Tout moyen autre que les espèces s'encaisse au montant exact : le
    // bouton est donc directement actionnable.
    if (modePaiement !== 'ESPECES' && modePaiement !== 'CREDIT') $('confirm-pay').disabled = false;

    majCreditBox();
    majSectionEspeces();
    construireRaccourcisCash();
    majMonnaie();
    $('pay-modal').classList.add('open');
    if (modePaiement === 'ESPECES') $('cash-received').focus();
  }

  function majSectionEspeces() {
    const mode = $('pay-method').querySelector('button.active')?.dataset.mode;
    $('cash-section').style.display = mode === 'ESPECES' ? '' : 'none';
    // Bascule vers les espèces : on repart du montant exact pré-rempli.
    if (mode === 'ESPECES' && !$('cash-received').value.trim()) {
      $('cash-received').value = totalPanier().toFixed(2);
      extrasOuverts = false;
    }
    $('confirm-pay').style.display = '';
    $('confirm-pay').innerHTML = mode === 'CREDIT'
      ? '<i class="fas fa-book mr-1"></i> Confirmer la vente à crédit'
      : '<i class="fas fa-check-circle mr-1"></i> Confirmer le paiement';
    const needsRef = MODES_A_REFERENCE.includes(mode);
    $('ref-box').style.display = needsRef ? '' : 'none';
    if (needsRef) $('pay-reference').focus();
    majExtras();
    majEtatConfirmationPaiement();
  }

  function majCreditBox() {
    const credit = $('pay-method').querySelector('button.active')?.dataset.mode === 'CREDIT';
    const box = $('credit-box');
    box.style.display = credit ? 'flex' : 'none';
    if (credit) {
      const c = clientCourant();
      const dispo = c ? Math.max(0, Number(c.max_credit) - Number(c.solde_du)) : 0;
      $('credit-available').textContent = c
        ? `${fmt(dispo)} disponible · plafond ${fmt(c.max_credit)} · dû ${fmt(c.solde_du)}`
        : 'Sélectionnez un client autorisé';
      box.classList.toggle('negar', !c || Number(c.max_credit) <= 0 || dispo < totalPanier());
    }
    majEtatConfirmationPaiement();
  }

  function majEtatConfirmationPaiement() {
    const mode = $('pay-method').querySelector('button.active')?.dataset.mode;
    const bouton = $('confirm-pay');
    if (mode === 'ESPECES') {
      bouton.disabled = num($('cash-received').value) < totalPanier();
    } else if (mode === 'CREDIT') {
      const c = clientCourant();
      const dispo = c ? Math.max(0, Number(c.max_credit) - Number(c.solde_du)) : 0;
      bouton.disabled = !c || Number(c.max_credit) <= 0 || dispo < totalPanier();
    } else {
      bouton.disabled = false;
    }
  }

  $('pay-method').addEventListener('click', (e) => {
    const btn = e.target.closest('button');
    if (!btn) return;
    $('pay-method').querySelectorAll('button').forEach((b) => b.classList.toggle('active', b === btn));
    setMode(btn.dataset.mode);
    majCreditBox();
    majSectionEspeces();
    if (btn.dataset.mode === 'ESPECES') $('cash-received').focus();
  });

  function construireRaccourcisCash() {
    const total = totalPanier();
    const valeurs = [Math.ceil(total / 500) * 500, Math.ceil(total / 1000) * 1000, Math.ceil(total / 5000) * 5000, Math.ceil(total / 10000) * 10000];
    $('quick-cash').innerHTML = [...new Set(valeurs.filter((v) => v > total))].slice(0, 3)
      .map((v) => `<button type="button" data-amount="${v}">${fmt(v)}</button>`).join('');
  }
  $('quick-cash').addEventListener('click', (e) => {
    const btn = e.target.closest('button');
    if (!btn) return;
    $('cash-received').value = Number(btn.dataset.amount).toFixed(2);
    majMonnaie();
  });

  function majMonnaie() {
    const total = totalPanier();
    const recu = num($('cash-received').value);
    const change = recu - total;
    const box = $('change-box');
    // Le rendu n'apparaît que s'il y a réellement quelque chose à rendre (ou à
    // réclamer) : au montant exact, l'écran reste épuré.
    if (recu > 0 && Math.abs(change) >= 0.005) {
      box.style.display = 'flex';
      box.classList.toggle('negar', change < 0);
      $('change-amount').textContent = `${change < 0 ? 'Manque ' : ''}${fmt(Math.abs(change))}`;
    } else {
      box.style.display = 'none';
    }
    // Dès qu'on s'écarte du montant exact, le pavé et les coupures rapides se
    // déploient pour saisir le montant reçu.
    if (estEspecesCourantes()) extrasOuverts = !estMontantExact();
    majExtras();
    majEtatConfirmationPaiement();
  }
  $('cash-received').addEventListener('input', majMonnaie);

  /* Le paiement en espèces part du montant exact ; le pavé et les coupures ne
     s'affichent qu'au besoin, pour ne pas encombrer l'écran. */
  function estEspecesCourantes() {
    return ($('pay-method').querySelector('button.active')?.dataset.mode || modePaiement) === 'ESPECES';
  }
  function estMontantExact() {
    return Math.abs(num($('cash-received').value) - totalPanier()) < 0.005;
  }
  function majExtras() {
    const especes = estEspecesCourantes();
    $('cash-extras').style.display = especes && extrasOuverts ? '' : 'none';
    $('cash-more').style.display = especes && !extrasOuverts ? '' : 'none';
  }
  $('cash-more').addEventListener('click', () => {
    extrasOuverts = true;
    majExtras();
    $('cash-received').focus();
    $('cash-received').select();
  });

  // Entrée valide l'encaissement depuis le montant reçu ou la référence :
  // « taper le montant puis Entrée » sans chercher le bouton.
  function validerParEntree(e) {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    if (!$('confirm-pay').disabled) $('confirm-pay').click();
  }
  $('cash-received').addEventListener('keydown', validerParEntree);
  $('pay-reference').addEventListener('keydown', validerParEntree);

  function touchePave(btn, champ) {
    const key = btn.dataset.key;
    if (key === 'clear') { champ.value = ''; return; }
    if (key === 'back') { champ.value = champ.value.slice(0, -1); return; }
    if (key === 'exact') { champ.value = Number(totalPanier()).toFixed(2); return; }
    champ.value = (champ.value + key).replace(/^0+(?=\d)/, '');
  }
  $('pave').addEventListener('click', (e) => {
    const btn = e.target.closest('button');
    if (btn) { touchePave(btn, $('cash-received')); majMonnaie(); }
  });
  $('pave').addEventListener('keydown', (e) => {
    if (!e.key.startsWith('Arrow') && e.key !== 'Backspace') return;
    e.preventDefault();
    const touches = { ArrowLeft: '7', ArrowUp: '4', ArrowRight: '9', ArrowDown: '1', Backspace: 'back' };
    if (touches[e.key]) touchePave({ dataset: { key: touches[e.key] } }, $('cash-received'));
    majMonnaie();
  });

  function fermerPaiement() { $('pay-modal').classList.remove('open'); }
  $('pay-close').addEventListener('click', fermerPaiement);
  $('pay-modal').addEventListener('click', (e) => { if (e.target === $('pay-modal')) fermerPaiement(); });
  $('checkout-btn').addEventListener('click', ouvrirPaiement);

  function corpsVente(paiements) {
    const lignes = Object.values(panier).map((l) => ({
      produit_id: l.id,
      quantite: l.quantite,
      unite: l.unite,
      remise_manuelle: Number(l.remise_manuelle || 0).toFixed(2),
    }));
    const corps = {
      client: $('client-select').value ? Number($('client-select').value) : null,
      lignes,
    };
    if (corps.client === null) corps.client_libelle = clientLibelle;
    if (paiements && paiements.length) corps.paiements = paiements;
    else corps.mode_paiement = modePaiement;
    const motif = Object.values(panier).some((l) => l.remise_manuelle > 0);
    if (motif && contexte.remise_motif_obligatoire) corps.motif_remise = 'Remise au comptoir';
    return corps;
  }

  async function validerVente(paiements) {
    const btn = $('confirm-pay');
    const texte = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i> Validation…';
    try {
      const data = await api(API.ventes, {
        method: 'POST',
        headers: { ...CSRF() },
        body: JSON.stringify(corpsVente(paiements)),
      });
      venteCourante = data.data;
      bip(true);
      fermerPaiement();
      afficherRecu(venteCourante, paiements);
      viderPanier();
    } catch (e) {
      bip(false);
      notice(e.message);
      toast(`<i class="fas fa-exclamation-triangle mr-1"></i>${esc(e.message)}`, 'red');
      btn.disabled = false;
      btn.innerHTML = texte;
    }
  }

  $('confirm-pay').addEventListener('click', () => {
    const mode = $('pay-method').querySelector('button.active')?.dataset.mode || modePaiement;
    if (mode === 'ESPECES') {
      const total = totalPanier();
      const recu = num($('cash-received').value);
      if (recu < total) { notice('Montant reçu insuffisant pour encaisser.'); return; }
      validerVente(null);
      return;
    }
    if (mode === 'CREDIT') {
      const client = clientCourant();
      if (!client || Number(client.max_credit) <= 0) {
        notice('Sélectionnez un client autorisé au paiement en compte.');
        return;
      }
      const disponible = Number(client.max_credit) - Number(client.solde_du);
      if (disponible < totalPanier()) {
        notice(`Crédit insuffisant : ${fmt(Math.max(0, disponible))} disponible pour ${fmt(totalPanier())}.`);
        return;
      }
      validerVente([{ mode, montant: totalPanier().toFixed(2) }]);
      return;
    }
    // Mobile money, operators, card, check and account are taken at the exact
    // amount: no "change" is asked on a terminal. A reference is captured for
    // the modes the cashier cannot reconcile on their own.
    const ref = $('pay-reference').value.trim();
    if (MODES_A_REFERENCE.includes(mode) && !ref) {
      notice('Saisissez la référence de transaction.');
      $('pay-reference').focus();
      return;
    }
    validerVente([{ mode, montant: totalPanier().toFixed(2), reference: ref }]);
  });
  $('pay-reference').addEventListener('input', (e) => {
    if (e.target.value.trim()) e.target.style.borderColor = 'var(--line)';
  });

  /* ------------------------------------------------------------ paiement mixte */
  let repartition = [];

  function ouvrirMixte() {
    if (!MODES.length) {
      notice('Aucun moyen de paiement disponible. Contactez un administrateur.');
      return;
    }
    const total = totalPanier();
    $('mixte-total').textContent = fmt(total);
    $('split-motif').value = '';
    if (!repartition.length) repartition = [{ mode: modePaiement === 'CREDIT' ? 'ESPECES' : modePaiement, montant: total, reference: '' }];
    majRepartition();
    $('mixte-modal').classList.add('open');
  }

  function majRepartition() {
    const total = totalPanier();
    $('split-lines').innerHTML = repartition.map((r, i) => `
      <div class="split-line" data-i="${i}">
        <span class="who"><i class="fas ${iconeMode(r.mode)}"></i> ${esc(uniteLabelMode(r.mode))}</span>
        <input type="text" inputmode="decimal" data-champ="montant" value="${r.montant.toFixed(2)}" aria-label="Montant ${esc(uniteLabelMode(r.mode))}">
        ${MODES_A_REFERENCE.includes(r.mode)
          ? `<input type="text" data-champ="reference" value="${esc(r.reference || '')}" placeholder="Réf. transaction" aria-label="Référence ${esc(uniteLabelMode(r.mode))}">`
          : ''}
        <button type="button" class="del" aria-label="Retirer"><i class="fas fa-times"></i></button>
      </div>`).join('');

    const somme = repartition.reduce((s, r) => s + r.montant, 0);
    const reste = total - somme;
    $('split-rest').textContent = `Reste à répartir : ${fmt(reste)}`;
    $('split-rest').classList.toggle('ok', Math.abs(reste) < 0.005);
    $('confirm-mixte').disabled = Math.abs(reste) > 0.005 || !repartition.length;
  }

  function uniteLabelMode(mode) {
    return ($('payment-pills').querySelector(`button[data-mode="${mode}"]`)?.textContent || '').trim() || mode;
  }

  function iconeMode(mode) {
    return ICONES_MODE[mode] || 'fa-money-bill';
  }

  $('split-lines').addEventListener('input', (e) => {
    if (e.target.tagName !== 'INPUT') return;
    const i = Number(e.target.closest('.split-line').dataset.i);
    if (e.target.dataset.champ === 'reference') repartition[i].reference = e.target.value;
    else repartition[i].montant = num(e.target.value);
    majRepartition();
  });
  $('split-lines').addEventListener('click', (e) => {
    if (!e.target.closest('.del')) return;
    repartition.splice(Number(e.target.closest('.split-line').dataset.i), 1);
    majRepartition();
  });
  $('add-mode').addEventListener('click', () => {
    const restants = MODES.filter((m) => !repartition.some((r) => r.mode === m));
    if (!restants.length) { toast('Tous les moyens de paiement sont déjà utilisés.', 'info'); return; }
    repartition.push({ mode: restants[0], montant: 0, reference: '' });
    majRepartition();
  });
  $('mixte-modes').innerHTML = MODES.map((m) => `<span class="stock in-stock" style="justify-content:center"><i class="fas ${iconeMode(m)}"></i> ${esc(uniteLabelMode(m))}</span>`).join('');
  $('switch-mixte').addEventListener('click', ouvrirMixte);
  $('mixte-close').addEventListener('click', () => $('mixte-modal').classList.remove('open'));
  $('mixte-modal').addEventListener('click', (e) => { if (e.target === $('mixte-modal')) $('mixte-modal').classList.remove('open'); });

  $('confirm-mixte').addEventListener('click', async () => {
    const btn = $('confirm-mixte');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i> Validation…';
    const paiements = repartition
      .filter((r) => r.montant > 0)
      .map((r) => ({ mode: r.mode, montant: r.montant.toFixed(2), reference: r.reference || '' }));
    if (Object.values(panier).some((l) => l.remise_manuelle > 0) && !$('split-motif').value.trim()) {
      notice('Motif obligatoire : une remise est appliquée sur une ligne.', 'error');
      $('split-motif').focus();
      btn.disabled = false;
      btn.innerHTML = '<i class="fas fa-check-circle mr-1"></i> Valider le paiement mixte';
      return;
    }
    // Une ligne sans référence ne peut pas être rapprochée de l'opérateur.
    const sansRef = paiements.find((p) => MODES_A_REFERENCE.includes(p.mode) && !p.reference.trim());
    if (sansRef) {
      notice(`Référence de transaction manquante pour ${uniteLabelMode(sansRef.mode)}.`, 'error');
      btn.disabled = false;
      btn.innerHTML = '<i class="fas fa-check-circle mr-1"></i> Valider le paiement mixte';
      return;
    }
    const texte = btn.innerHTML;
    await validerVente(paiements);
    btn.disabled = false;
    btn.innerHTML = texte;
    if (venteCourante) $('mixte-modal').classList.remove('open');
    repartition = [];
  });

  /* ------------------------------------------------------------------ reçu */
  function viderPanier() {
    panier = {};
    // Le nom du client de passage vaut pour une seule vente : le ticket est
    // encaissé, la vente suivante repart d'un panier vierge.
    $('client-select').value = '';
    $('client-libelle').value = '';
    clientLibelle = '';
    majClient();
    rendrePanier();
  }

  function afficherRecu(vente, paiements) {
    $('receipt-sub').textContent = `${vente.reference} · ${dev(vente.total)}`;
    $('receipt-lines').innerHTML = vente.lignes.map((l) => `
      <div class="rec-line">
        <span><span class="q">${l.quantite} ×</span> ${esc(l.produit.nom)}${l.unite && l.unite !== 'BOUTEILLE' ? ` <span class="q">(${esc(l.unite.toLowerCase())})</span>` : ''}</span>
        <span>${fmt(l.sous_total)}</span>
      </div>`).join('');
    $('receipt-total').textContent = fmt(vente.total);

    const recu = paiements && paiements.length === 1 && paiements[0].mode === 'ESPECES' ? null : num(paiements?.[0]?.montant);
    const change = $('receipt-change');
    if (recu && recu > Number(vente.total)) {
      change.style.display = 'flex';
      $('receipt-change-val').textContent = fmt(recu - Number(vente.total));
    } else {
      change.style.display = 'none';
    }

    const modes = (vente.paiements || []).map((p) => uniteLabelMode(p.mode)).join(' + ') || uniteLabelMode(vente.mode_paiement);
    $('receipt-meta').innerHTML = `${esc(vente.reference)} · ${new Date(vente.date_vente).toLocaleString('fr-FR')} · ${esc(modes)}<br>Caissier : ${esc(vente.utilisateur?.full_name || vente.utilisateur?.username || '—')}`;

    $('receipt-print').href = vente.ticket_url;
    $('receipt-facture').href = `/admin/ventes/vente/${vente.id}/facture/`;

    const wa = $('receipt-wa');
    if (vente.whatsapp_url) {
      wa.disabled = false;
      wa.onclick = () => window.open(vente.whatsapp_url, '_blank', 'noopener');
    } else {
      wa.disabled = true;
      wa.title = 'Ce client n\'a pas de numéro de téléphone';
    }

    $('receipt-overlay').classList.add('open');
  }

  function fermerRecu() {
    $('receipt-overlay').classList.remove('open');
    $('search-input').focus();
  }
  $('receipt-next').addEventListener('click', fermerRecu);
  $('receipt-overlay').addEventListener('click', (e) => { if (e.target === $('receipt-overlay')) fermerRecu(); });

  /* ----------------------------------------------------------------- remise */
  let ligneRemise = null;

  function ouvrirRemise(id) {
    const lignes = Object.values(panier);
    if (!lignes.length) { notice('Aucune ligne à remiser.'); return; }
    if (!contexte.peut_remettre) { notice('Votre rôle ne permet pas la remise.'); return; }
    ligneRemise = id || lignes[0].id;
    $('remise-ligne').innerHTML = lignes.map((l) => {
      const p = produit(l.id);
      return `<option value="${l.id}" ${l.id === ligneRemise ? 'selected' : ''}>${esc(p.nom)} — ${fmt(prixLigne(l))}</option>`;
    }).join('');
    majPlafondLigne();
    $('remise-montant').value = '';
    $('remise-pct').value = '';
    majApresRemise();
    $('remise-modal').classList.add('open');
  }

  function majPlafondLigne() {
    const ligne = panier[$('remise-ligne').value];
    if (!ligne) return;
    const brut = (meta.get(ligne.id)?.prix || 0) * ligne.quantite;
    const pctMax = contexte.remise_max_pct !== null && contexte.remise_max_pct !== undefined ? Number(contexte.remise_max_pct) : null;
    $('remise-plafond').textContent = pctMax === null
      ? `Ligne brute ${fmt(brut)} — remise libre.`
      : `Ligne brute ${fmt(brut)} — plafond ${pctMax} % soit ${fmt(brut * pctMax / 100)}.`;

    const valeurs = [5, 10, pctMax || 20].filter((v, i, a) => a.indexOf(v) === i)
      .map((pct) => `<button type="button" data-pct="${pct}">${pct} %</button>`).join('');
    $('remise-rapides').innerHTML = valeurs;
  }

  function majApresRemise() {
    const ligne = panier[$('remise-ligne').value];
    if (!ligne) return;
    const brut = (meta.get(ligne.id)?.prix || 0) * ligne.quantite;
    let remise = num($('remise-montant').value);
    const pct = num($('remise-pct').value);
    if (pct > 0) remise = brut * pct / 100;
    const autorise = remise <= brut;
    $('remise-apres').style.display = 'flex';
    $('remise-apres').classList.toggle('negar', !autorise || remise > brut);
    $('remise-apres-val').textContent = `${fmt(Math.max(0, brut - remise))}`;
    $('confirm-remise').disabled = remise <= 0 || !autorise;
  }

  $('remise-ligne').addEventListener('change', () => { majPlafondLigne(); majApresRemise(); });
  $('remise-montant').addEventListener('input', () => { $('remise-pct').value = ''; majApresRemise(); });
  $('remise-pct').addEventListener('input', () => { $('remise-montant').value = ''; majApresRemise(); });
  $('remise-rapides').addEventListener('click', (e) => {
    const btn = e.target.closest('button');
    if (!btn) return;
    $('remise-pct').value = btn.dataset.pct;
    $('remise-montant').value = '';
    majApresRemise();
  });
  $('confirm-remise').addEventListener('click', () => {
    const id = Number($('remise-ligne').value);
    const ligne = panier[id];
    if (!ligne) return;
    const brut = (meta.get(id)?.prix || 0) * ligne.quantite;
    let remise = num($('remise-montant').value);
    const pct = num($('remise-pct').value);
    if (pct > 0) remise = brut * pct / 100;
    if (remise <= 0) { notice('Saisissez un montant de remise.'); return; }
    if (remise > brut) { notice('La remise ne peut pas dépasser le brut de la ligne.'); return; }
    ligne.remise_manuelle = Math.round(remise * 100) / 100;
    rendrePanier();
    $('remise-modal').classList.remove('open');
    toast(`<i class="fas fa-percent mr-1"></i>Remise de ${fmt(remise)} appliquée.`, 'green');
  });
  $('remise-close').addEventListener('click', () => $('remise-modal').classList.remove('open'));
  $('remise-modal').addEventListener('click', (e) => { if (e.target === $('remise-modal')) $('remise-modal').classList.remove('open'); });
  $('open-remise').addEventListener('click', () => ouvrirRemise(null));

  /* ----------------------------------------------------------------- retour */
  let venteRetour = null;

  async function chercherVente(ref) {
    if (!ref) return;
    try {
      const data = await api(`${API.ventes}?search=${encodeURIComponent(ref)}`);
      const results = data.results || data;
      if (!results.length) {
        bip(false);
        $('retour-vide').textContent = `Aucune vente pour la référence « ${ref} ».`;
        $('retour-vide').style.display = '';
        $('retour-contenu').style.display = 'none';
        return;
      }
      const v = results[0];
      const detail = await api(`${API.ventes}${v.id}/retour/`);
      venteRetour = detail;
      rendreRetour(detail);
    } catch (e) {
      bip(false);
      notice(e.message);
    }
  }

  function rendreRetour(detail) {
    const v = detail.vente;
    $('retour-vide').style.display = 'none';
    $('retour-contenu').style.display = '';
    $('retour-tete').innerHTML = `Vente <b>${esc(v.reference)}</b> du ${new Date(v.date_vente).toLocaleDateString('fr-FR')} — total ${fmt(v.total)}, déjà retourné ${fmt(detail.retourne)} · ${esc([v.client?.nom, v.client?.prenom].filter(Boolean).join(' '))}`;

    $('retour-lignes').innerHTML = detail.lignes.map((l) => `
      <div class="retour-line" data-ligne="${l.ligne_id}" data-prix="${l.prix_unitaire}" data-restant="${l.retournable}">
        <span>
          <span class="nom">${esc(l.nom)}</span>
          <span class="info">vendu ${l.vendu} · retourné ${l.deja_retourne} · max ${l.retournable}</span>
        </span>
        <span class="max">×<input type="number" min="0" max="${l.retournable}" value="0" aria-label="Quantité retournée"></span>
        <button type="button" class="qty-btn" data-dir="-1" aria-label="Moins"><i class="fas fa-minus"></i></button>
        <button type="button" class="qty-btn" data-dir="1" aria-label="Plus"><i class="fas fa-plus"></i></button>
      </div>`).join('');
    $('retour-motif').value = '';
    majTotalRetour();
  }

  function majTotalRetour() {
    let total = 0;
    $('retour-lignes').querySelectorAll('.retour-line').forEach((row) => {
      const q = num(row.querySelector('input').value);
      total += q * num(row.dataset.prix);
    });
    $('retour-total').style.display = 'flex';
    $('retour-total-val').textContent = fmt(total);
    $('confirm-retour').disabled = total <= 0 || !$('retour-motif').value.trim();
  }

  $('retour-lignes').addEventListener('input', (e) => {
    if (e.target.tagName === 'INPUT') majTotalRetour();
  });
  $('retour-lignes').addEventListener('click', (e) => {
    const btn = e.target.closest('.qty-btn');
    if (!btn) return;
    const row = btn.closest('.retour-line');
    const input = row.querySelector('input');
    const max = Number(row.dataset.restant);
    const q = Math.max(0, Math.min(max, num(input.value) + Number(btn.dataset.dir)));
    input.value = q;
    majTotalRetour();
  });
  $('retour-motif').addEventListener('input', majTotalRetour);
  $('retour-ref').addEventListener('change', (e) => chercherVente(e.target.value.trim()));
  $('retour-ref').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); chercherVente(e.target.value.trim()); } });

  $('confirm-retour').addEventListener('click', async () => {
    if (!venteRetour) return;
    const retours = [];
    $('retour-lignes').querySelectorAll('.retour-line').forEach((row) => {
      const q = num(row.querySelector('input').value);
      // La clé attendue par `RetourService` est `ligne_id`, pas `ligne`.
      if (q > 0) retours.push({ ligne_id: Number(row.dataset.ligne), quantite: q });
    });
    const motif = $('retour-motif').value.trim();
    if (!motif) { notice('Le motif du retour est obligatoire.'); return; }
    const btn = $('confirm-retour');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i> Validation…';
    try {
      await api(`${API.ventes}${venteRetour.vente.id}/retour/`, {
        method: 'POST',
        headers: CSRF(),
        body: JSON.stringify({ retours, motif, mode_remboursement: $('retour-mode').value }),
      });
      bip(true);
      $('retour-modal').classList.remove('open');
      toast('<i class="fas fa-rotate-left mr-1"></i>Retour enregistré, stock réintégré.', 'green');
      await rechargerStock();
    } catch (e) {
      bip(false);
      notice(e.message);
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<i class="fas fa-check mr-1"></i> Valider le retour';
    }
  });
  $('retour-close').addEventListener('click', () => $('retour-modal').classList.remove('open'));
  $('retour-modal').addEventListener('click', (e) => { if (e.target === $('retour-modal')) $('retour-modal').classList.remove('open'); });
  $('open-retour').addEventListener('click', () => {
    venteRetour = null;
    $('retour-ref').value = '';
    $('retour-contenu').style.display = 'none';
    $('retour-vide').style.display = '';
    $('retour-modal').classList.add('open');
    $('retour-ref').focus();
  });

  async function rechargerStock() {
    try {
      produits = await fetchAll(API.produits);
      produits.forEach((p) => {
        const promo = infoPromo(p);
        meta.set(p.id, { promo, prix: promo ? Number(promo.prix_final) : Number(p.prix_vente) });
      });
      rendreProduits();
      rendrePanier();
    } catch (e) { /* le catalogue se rafraîchira au prochain rechargement */ }
  }

  /* ---------------------------------------------------------- client express */
  $('express-client').addEventListener('click', () => {
    ['exp-nom', 'exp-prenom', 'exp-tel', 'exp-email'].forEach((id) => { $(id).value = ''; });
    $('express-modal').classList.add('open');
    $('exp-nom').focus();
  });
  $('express-close').addEventListener('click', () => $('express-modal').classList.remove('open'));
  $('express-modal').addEventListener('click', (e) => { if (e.target === $('express-modal')) $('express-modal').classList.remove('open'); });

  $('exp-submit').addEventListener('click', async () => {
    const payload = {
      nom: $('exp-nom').value.trim(),
      prenom: $('exp-prenom').value.trim(),
      telephone: $('exp-tel').value.trim(),
      email: $('exp-email').value.trim(),
    };
    if (!payload.nom || !payload.prenom || !payload.telephone) {
      notice('Nom, prénom et téléphone sont obligatoires.', 'error');
      return;
    }
    const btn = $('exp-submit');
    btn.disabled = true;
    try {
      const client = await api(API.clients, { method: 'POST', headers: CSRF(), body: JSON.stringify(payload) });
      clients.push(client);
      rendreClients();
      $('client-select').value = String(client.id);
      majClient();
      $('express-modal').classList.remove('open');
      toast(`<i class="fas fa-user-check mr-1"></i>${esc(client.nom)} ajouté.`, 'green');
    } catch (e) {
      notice(e.message);
    } finally {
      btn.disabled = false;
    }
  });

  /* ---------------------------------------------------------------- clôture */
  let fondsSession = 0;

  async function ouvrirCloture() {
    try {
      const data = await api(API.caisseRapport);
      if (!data.session || !data.rapport) { notice('Aucune caisse ouverte à clôturer.'); return; }
      const r = data.rapport;
      // Le service calcule l'écart sur `especes_reel - (fonds_de_caisse + CA
      // espèces)`. Le fonds à déclarer est donc celui de l'ouverture : envoyer le
      // compté comme fonds ferait compter le tiroir deux fois.
      fondsSession = Number(data.session.fonds_de_caisse) || 0;
      $('cl-nb-tickets').textContent = r.nb_tickets;
      $('cl-ca-especes').textContent = fmt(r.ca_especes);
      $('cl-ca-mobile').textContent = fmt(r.ca_mobile_money);
      $('cl-ca-carte').textContent = fmt(r.ca_carte);
      $('cl-ca-credit').textContent = fmt(r.ca_credit);
      $('cl-rembourse').textContent = fmt(r.ca_rembourse);
      $('cl-fonds').textContent = fmt(data.session.fonds_de_caisse);
      $('cl-attendu').textContent = fmt(r.attendu_en_caisse);
      $('cl-reel').value = '';
      $('cl-note').value = '';
      majEcart();
      $('cloture-modal').classList.add('open');
    } catch (e) {
      notice(e.message);
    }
  }

  function majEcart() {
    const attendu = Number($('cl-attendu').textContent.replace(/\s/g, '').replace(',', '.')) || 0;
    const reel = num($('cl-reel').value);
    const box = $('cl-ecart');
    if (reel > 0) {
      const ecart = reel - attendu;
      box.style.display = 'flex';
      box.classList.toggle('negar', Math.abs(ecart) > 0.5);
      $('cl-ecart-val').textContent = `${ecart > 0 ? 'Excédent ' : ecart < 0 ? 'Manque ' : ''}${fmt(Math.abs(ecart))}`;
      $('confirm-cloture').disabled = false;
    } else {
      box.style.display = 'none';
      $('confirm-cloture').disabled = true;
    }
  }
  $('cl-reel').addEventListener('input', majEcart);
  $('cl-pave').addEventListener('click', (e) => {
    const btn = e.target.closest('button');
    if (!btn) return;
    const champ = $('cl-reel');
    if (btn.dataset.key === 'exact') {
      const attendu = Number($('cl-attendu').textContent.replace(/\s/g, '').replace(',', '.')) || 0;
      champ.value = attendu.toFixed(2);
    } else if (btn.dataset.key === 'clear') champ.value = '';
    else if (btn.dataset.key === 'back') champ.value = champ.value.slice(0, -1);
    else champ.value = (champ.value + btn.dataset.key).replace(/^0+(?=\d)/, '');
    majEcart();
  });

  $('confirm-cloture').addEventListener('click', async () => {
    const reel = num($('cl-reel').value);
    if (reel <= 0) { notice('Saisissez le total d\'espèces comptées.'); return; }
    const btn = $('confirm-cloture');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i> Clôture…';
    try {
      const data = await api(API.caisseCloturer, {
        method: 'POST',
        headers: CSRF(),
        body: JSON.stringify({ fonds_de_caisse: fondsSession, especes_reel: reel, note: $('cl-note').value.trim() }),
      });
      bip(true);
      $('cloture-modal').classList.remove('open');
      toast('<i class="fas fa-lock mr-1"></i>' + esc(data.message), 'green');
      contexte = await api(API.caisseEtat);
      majSession();
    } catch (e) {
      bip(false);
      notice(e.message);
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<i class="fas fa-lock mr-1"></i> Archiver la clôture';
    }
  });
  $('cloture-close').addEventListener('click', () => $('cloture-modal').classList.remove('open'));
  $('cloture-modal').addEventListener('click', (e) => { if (e.target === $('cloture-modal')) $('cloture-modal').classList.remove('open'); });

  /* --------------------------------------------------------------- clavier */
  document.addEventListener('keydown', (e) => {
    const dansChamp = /^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName);
    if (e.key === 'Escape') {
      if ($('receipt-overlay').classList.contains('open')) return fermerRecu();
      ['pay-modal', 'mixte-modal', 'remise-modal', 'retour-modal', 'express-modal', 'cloture-modal']
        .forEach((id) => $(id).classList.remove('open'));
      if (!dansChamp) { $('search-input').value = ''; rendreProduits(); }
      return;
    }
    if (dansChamp && e.key !== 'F2') {
      if (e.key === 'Enter' && e.target.id === 'search-input') return;
      return;
    }
    switch (e.key) {
      case 'F1': e.preventDefault(); $('sound-toggle').click(); break;
      case 'F2': e.preventDefault(); $('search-input').focus(); $('search-input').select(); break;
      case 'F4': e.preventDefault(); ouvrirPaiement(); break;
      case 'F5': e.preventDefault(); if (Object.keys(panier).length) ouvrirMixte(); break;
      case 'F6': e.preventDefault(); $('open-remise').click(); break;
      case 'F7': e.preventDefault(); $('open-retour').click(); break;
      case 'F9': e.preventDefault(); annulerVente(); break;
      case 'F10': e.preventDefault(); ouvrirCloture(); break;
      default: break;
    }
  });

  charger();
})();
