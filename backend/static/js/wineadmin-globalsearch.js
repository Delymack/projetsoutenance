/* ============================================================
   WineAdmin — Recherche globale (Ctrl + K)
   Champ placé au centre de la navbar : recherche dans les
   produits, clients, fournisseurs, commandes et ventes.
   ============================================================ */
(function () {
    "use strict";

    var root = document.getElementById("wine-global-search");
    if (!root) { return; }

    var input = document.getElementById("wine-gsearch-input");
    var panel = document.getElementById("wine-gsearch-panel");
    var timer = null;
    var requete = 0;
    var cibles = [];   // liste plate des éléments résultat
    var actif = -1;    // index de navigation clavier

    var urlRecherche = (document.body.getAttribute("data-gsearch-url") || "/admin/recherche/") + "";

    /* --- Ouverture / fermeture --- */
    function ouvrir() {
        var r = input.getBoundingClientRect();
        panel.style.left = (r.left + r.width / 2) + "px";
        panel.style.top = (r.bottom + 10) + "px";
        root.classList.add("is-open");
        panel.hidden = false;
        panel.scrollTop = 0;
    }
    function fermer(perteFocus) {
        root.classList.remove("is-open");
        panel.hidden = true;
        actif = -1;
        cibles = [];
        if (perteFocus !== false) { input.blur(); }
    }

    /* --- Mise en forme des résultats --- */
    function afficher(groupes) {
        cibles = [];
        actif = -1;
        panel.innerHTML = "";

        if (!groupes.length) {
            panel.innerHTML =
                '<div class="wine-gsearch-empty"><i class="fas fa-wine-bottle"></i>' +
                "<p>Aucun résultat pour « <strong></strong> »</p></div>";
            var st = panel.querySelector("strong");
            if (st) { st.textContent = input.value; }
            ouvrir();
            return;
        }

        var total = 0;
        groupes.forEach(function (grp) {
            var iconeClass = String(grp.icone || "fas fa-circle").replace(/[^a-z0-9-]/g, " ").trim();
            var h = document.createElement("div");
            h.className = "wine-gsearch-group";
            var hi = document.createElement("span");
            hi.className = "wine-gsearch-gh-ic " + iconeClass;
            var hl = document.createElement("span");
            hl.textContent = grp.groupe;                     // texte pur : rien n'est injecté en HTML
            var hc = document.createElement("i");
            hc.className = "wine-gsearch-gh-count";
            hc.textContent = grp.items.length;
            h.appendChild(hi); h.appendChild(hl); h.appendChild(hc);
            panel.appendChild(h);

            grp.items.forEach(function (it) {
                total += 1;
                var a = document.createElement("a");
                a.className = "wine-gsearch-item" + (total === 1 ? " selected" : "");
                a.href = it.url;
                a.setAttribute("data-index", total - 1);

                var ai = document.createElement("span");
                ai.className = "wine-gsearch-item-ic";
                var aii = document.createElement("i");
                aii.className = iconeClass;
                ai.appendChild(aii);

                var tx = document.createElement("span");
                tx.className = "wine-gsearch-item-tx";
                var t1 = document.createElement("span");
                t1.className = "wine-gsearch-item-title";
                t1.textContent = it.titre;                   // texte pur (anti-XSS)
                tx.appendChild(t1);
                if (it.sous) {
                    var t2 = document.createElement("span");
                    t2.className = "wine-gsearch-item-sub";
                    t2.textContent = it.sous;                // texte pur (anti-XSS)
                    tx.appendChild(t2);
                }

                var go = document.createElement("span");
                go.className = "wine-gsearch-item-go";
                var goi = document.createElement("i");
                goi.className = "fas fa-arrow-right";
                go.appendChild(goi);

                a.appendChild(ai); a.appendChild(tx); a.appendChild(go);
                a.addEventListener("mousemove", function () { surligner(parseInt(a.getAttribute("data-index"), 10)); });
                a.addEventListener("click", function (e) { e.stopPropagation(); fermer(false); });
                panel.appendChild(a);
                cibles.push(a);
            });
        });

        var foot = document.createElement("div");
        foot.className = "wine-gsearch-foot";
        foot.innerHTML = '<span><i class="fas fa-arrow-up"></i><i class="fas fa-arrow-down"></i> naviguer</span>' +
                         "<span><i class=\"wine-gsearch-foot-enter\">↵</i> ouvrir</span>" +
                         '<span class="wine-gsearch-foot-esc"><i class="fas fa-times"></i> fermer</span>';
        panel.appendChild(foot);
        ouvrir();
        panel.scrollTop = 0;
    }

    /* --- Surlignage clavier --- */
    function surligner(index) {
        if (index < 0 || index >= cibles.length) { return; }
        actif = index;
        cibles.forEach(function (el) { el.classList.remove("selected"); });
        cibles[index].classList.add("selected");
        var el = cibles[index];
        if (panel.scrollTop > el.offsetTop - 90 || panel.scrollTop + panel.clientHeight < el.offsetTop + el.clientHeight) {
            el.scrollIntoView({ block: "nearest" });
        }
    }

    /* --- Requête (débouncée) --- */
    function chercher(valeur) {
        var q = valeur.trim();
        if (q.length < 2) {
            panel.innerHTML = "";
            panel.hidden = true;
            root.classList.remove("is-open", "is-loading");
            return;
        }
        root.classList.add("is-loading");
        var numero = ++requete;
        fetch(urlRecherche + "?q=" + encodeURIComponent(q), {
            headers: { "X-Requested-With": "XMLHttpRequest", "Accept": "application/json" },
            credentials: "same-origin"
        })
        .then(function (r) { return r.json(); })
        .then(function (donnees) {
            if (numero !== requete) { return; }   // réponse obsolète
            root.classList.remove("is-loading");
            afficher(donnees.groupes || []);
        })
        .catch(function () {
            if (numero !== requete) { return; }
            root.classList.remove("is-loading");
            panel.innerHTML = '<div class="wine-gsearch-empty wine-gsearch-error"><i class="fas fa-exclamation-triangle"></i><p>Recherche indisponible</p></div>';
            ouvrir();
        });
    }

    /* --- Événements --- */
    input.addEventListener("input", function () {
        clearTimeout(timer);
        timer = setTimeout(function () { chercher(input.value); }, 260);
    });

    input.addEventListener("focus", function () {
        if (input.value.trim().length >= 2) { chercher(input.value); }
    });

    input.addEventListener("keydown", function (e) {
        if (e.key === "ArrowDown") { e.preventDefault(); surligner(actif + 1); }
        else if (e.key === "ArrowUp") { e.preventDefault(); surligner(actif - 1); }
        else if (e.key === "Enter") {
            if (actif >= 0 && cibles[actif]) {
                e.preventDefault();
                window.location.href = cibles[actif].href;
                fermer(false);
            }
        }
        else if (e.key === "Escape") { e.preventDefault(); fermer(true); }
    });

    document.addEventListener("keydown", function (e) {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
            e.preventDefault();
            input.focus();
            input.select();
        }
    });

    document.addEventListener("click", function (e) {
        if (!root.contains(e.target)) { fermer(true); }
    });

    window.addEventListener("resize", function () {
        if (!panel.hidden) { ouvrir(); }
    });

    panel.addEventListener("click", function (e) { e.stopPropagation(); });
})();