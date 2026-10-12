(function () {
    'use strict';

    const overlay = document.getElementById('wine-quick-create');
    if (!overlay) return;

    const dialog = overlay.querySelector('.wine-quick-create-dialog');
    const title = document.getElementById('wine-quick-create-title');
    const content = document.getElementById('wine-quick-create-content');
    let previousFocus = null;
    let activeUrl = null;
    let sequence = 0;
    let busy = false;
    let widePage = false;
    let editMode = false;
    let rechargeDemandee = false;
    let minuteurSucces = null;
    let pageBodyClasses = [];
    let pageStyles = [];

    function clearPageAssets() {
        pageStyles.forEach((style) => style.remove());
        pageStyles = [];
        pageBodyClasses.forEach((name) => document.body.classList.remove(name));
        pageBodyClasses = [];
    }

    function afficherEtat(message, erreur = false) {
        content.replaceChildren();
        const state = document.createElement('div');
        state.className = erreur ? 'wine-quick-create-state is-error' : 'wine-quick-create-state';
        state.setAttribute('role', erreur ? 'alert' : 'status');
        const icon = document.createElement('i');
        icon.className = erreur ? 'fas fa-triangle-exclamation' : 'fas fa-spinner fa-spin';
        icon.setAttribute('aria-hidden', 'true');
        const texte = document.createElement('span');
        texte.textContent = message;
        state.append(icon, texte);
        content.appendChild(state);
    }

    function afficherSucces(message) {
        content.replaceChildren();
        const state = document.createElement('div');
        state.className = 'wine-quick-create-state is-success';
        state.setAttribute('role', 'status');
        const icon = document.createElement('i');
        icon.className = 'fas fa-circle-check';
        icon.setAttribute('aria-hidden', 'true');
        const texte = document.createElement('span');
        texte.textContent = message;
        state.append(icon, texte);
        content.appendChild(state);
    }

    function fermer(recharger = false) {
        window.clearTimeout(minuteurSucces);
        minuteurSucces = null;
        // Une fois un enregistrement accepté par le serveur, la page derrière
        // la fenêtre doit être actualisée : même une fermeture manuelle
        // pendant le temps fort déclenche le rechargement.
        const actualiserPage = recharger || widePage || rechargeDemandee;
        rechargeDemandee = false;
        sequence += 1;
        busy = false;
        activeUrl = null;
        widePage = false;
        editMode = false;
        overlay.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('wine-quick-create-open');
        content.replaceChildren();
        clearPageAssets();
        if (previousFocus && previousFocus.isConnected) previousFocus.focus();
        if (actualiserPage) window.location.reload();
    }

    function estPageConnexion(documentPage) {
        return Boolean(documentPage.querySelector('#login-form, form[action*="login"]'));
    }

    function installerStyles(documentPage) {
        documentPage.head.querySelectorAll('style, link[rel="stylesheet"]').forEach((element) => {
            if (element.tagName === 'LINK') {
                const url = new URL(element.href, window.location.href);
                if (url.origin !== window.location.origin) return;
                const dejaCharge = Array.from(document.querySelectorAll('link[rel="stylesheet"]'))
                    .some((link) => link.href === url.href);
                if (dejaCharge) return;
            }
            const copie = document.importNode(element, true);
            document.head.appendChild(copie);
            pageStyles.push(copie);
        });
    }

    function chargerScripts(documentPage) {
        return Array.from(documentPage.querySelectorAll('script')).reduce((queue, source) =>
            queue.then(() => {
                if (source.src) {
                    const url = new URL(source.src, window.location.href);
                    if (url.origin !== window.location.origin) return undefined;
                    const dejaCharge = Array.from(document.scripts).some((script) => script.src === url.href);
                    if (dejaCharge) return undefined;
                    return new Promise((resolve, reject) => {
                        const script = document.createElement('script');
                        script.src = url.href;
                        script.async = false;
                        script.onload = resolve;
                        script.onerror = () => reject(new Error(`Le script ${url.pathname} n’a pas pu être chargé.`));
                        document.body.appendChild(script);
                    });
                }
                if (source.textContent.trim()) {
                    const script = document.createElement('script');
                    script.textContent = source.textContent;
                    document.body.appendChild(script);
                    script.remove();
                }
                return undefined;
            }), Promise.resolve());
    }

    // Les formulaires de l'admin sont rendus avec `action=""` : injectés dans
    // la fenêtre, ils posteraient vers la liste courante au lieu du formulaire
    // demandé. On réécrit l'action avec l'URL réellement ouverte.
    function normaliserActions() {
        if (!activeUrl) return;
        const cible = activeUrl.pathname + activeUrl.search;
        content.querySelectorAll('form').forEach((formulaire) => {
            if (!formulaire.getAttribute('action')) formulaire.setAttribute('action', cible);
        });
    }

    // La fenêtre n'a pas d'onglets : le onglet de navigation est masqué, donc
    // chaque fieldset replié est déplié ici et reçoit son titre d'origine.
    function deplierPanneaux() {
        const onglets = content.querySelector('#jazzy-tabs');
        const panneaux = Array.from(content.querySelectorAll('.tab-pane'));
        panneaux.forEach((panneau) => panneau.classList.add('active', 'show'));
        if (!onglets || panneaux.length < 2) return;
        const liens = Array.from(onglets.querySelectorAll('a[href^="#"]'));
        panneaux.forEach((panneau) => {
            if (!panneau.id || panneau.querySelector('.wine-pane-title')) return;
            const lien = liens.find((ancre) => ancre.getAttribute('href').slice(1) === panneau.id);
            if (!lien || !lien.textContent.trim()) return;
            const titre = document.createElement('h3');
            titre.className = 'wine-pane-title';
            titre.textContent = lien.textContent.trim();
            panneau.prepend(titre);
        });
    }

    function mettreAJourActions() {
        normaliserActions();
        deplierPanneaux();

        const formulaire = content.querySelector('#content-main form');
        const ligneChamps = formulaire?.querySelector('.row');
        const panneauActions = formulaire?.querySelector('#jazzy-actions');

        if (formulaire && ligneChamps && panneauActions) {
            const colonneChamps = ligneChamps.querySelector('.col-lg-9');
            const colonneActions = panneauActions.closest('.col-12');
            const ligneActions = panneauActions.querySelector('.submit-row, .card-body > .d-flex.flex-wrap');

            colonneChamps?.classList.add('wine-quick-create-fields');
            if (ligneActions) {
                ligneActions.classList.add('submit-row');
                ligneActions.classList.add('wine-quick-create-actions');
                ligneChamps.after(ligneActions);
            }
            panneauActions.querySelectorAll('.object-tools, .object-tools *').forEach((outil) => outil.remove());
            colonneActions?.remove();
        }

        content.querySelectorAll('.submit-row').forEach((ligne) => {
            const enregistrer = ligne.querySelector('button[name="_save"], input[name="_save"]');
            if (enregistrer) {
                enregistrer.classList.add('wine-quick-create-save');
                const label = editMode ? 'Modifier' : 'Enregistrer';
                if (enregistrer instanceof HTMLInputElement) {
                    enregistrer.value = label;
                } else {
                    enregistrer.replaceChildren();
                    const icon = document.createElement('i');
                    icon.className = editMode ? 'fas fa-pen' : 'fas fa-check';
                    icon.setAttribute('aria-hidden', 'true');
                    enregistrer.append(icon, document.createTextNode(` ${label}`));
                }
            }

            ligne.querySelectorAll(
                '[name="_addanother"], [name="_continue"], [name="_saveasnew"], a'
            ).forEach((action) => action.remove());
            if (!ligne.querySelector('.wine-quick-create-cancel')) {
                const annuler = document.createElement('button');
                annuler.type = 'button';
                annuler.className = 'wine-quick-create-cancel';
                annuler.dataset.quickCreateClose = '';
                annuler.innerHTML = '<i class="fas fa-times" aria-hidden="true"></i> Annuler';
                ligne.appendChild(annuler);
            }
        });

        // Les cadres d'aide et d'erreur sont rendus à vide par l'admin :
        // sur une carte serrée, ils ne laissent que des trous.
        content.querySelectorAll('.help-block').forEach((bloc) => {
            if (!bloc.textContent.trim() && !bloc.querySelector('input, select, textarea, button, a, ul')) {
                bloc.remove();
            }
        });
    }

    function afficherFeedback(form, message, erreur = false) {
        const ligne = form.querySelector('.submit-row');
        if (!ligne) return;

        let feedback = ligne.querySelector('.wine-quick-create-feedback');
        if (!feedback) {
            feedback = document.createElement('p');
            feedback.className = 'wine-quick-create-feedback';
            feedback.setAttribute('role', 'status');
            ligne.appendChild(feedback);
        }
        feedback.classList.toggle('is-error', erreur);
        feedback.setAttribute('role', erreur ? 'alert' : 'status');
        feedback.textContent = message;
    }

    async function afficherFormulaire(documentPage, numero) {
        const page = documentPage.querySelector('#content') ||
            documentPage.querySelector('.app-content') ||
            documentPage.querySelector('main');
        if (!page) throw new Error('Le formulaire demandé est introuvable dans la réponse du serveur.');

        const titrePage = documentPage.querySelector('.content-header h1, #content h1, main h1');
        if (titrePage && titrePage.textContent.trim()) title.textContent = titrePage.textContent.trim();
        clearPageAssets();
        installerStyles(documentPage);
        documentPage.body.classList.forEach((name) => {
            if ((name === 'change-form' || /^model-[\w-]+$/.test(name)) &&
                !document.body.classList.contains(name)) {
                document.body.classList.add(name);
                pageBodyClasses.push(name);
            }
        });
        content.replaceChildren(document.importNode(page, true));
        content.scrollTop = 0;

        await chargerScripts(documentPage);
        if (numero !== sequence) return;
        mettreAJourActions();

        const premierChamp = content.querySelector(
            '.change-form input:not([type="hidden"]):not([disabled]), .change-form select:not([disabled]), .change-form textarea:not([disabled]), #pos-root input:not([disabled])'
        );
        if (premierChamp) premierChamp.focus({ preventScroll: true });
    }

    async function charger(url, numero = ++sequence) {
        busy = true;
        afficherEtat('Chargement du formulaire…');
        try {
            const reponse = await fetch(url, {
                credentials: 'same-origin',
                headers: { Accept: 'text/html' },
            });
            if (numero !== sequence) return;
            const documentPage = new DOMParser().parseFromString(await reponse.text(), 'text/html');
            if (estPageConnexion(documentPage)) {
                afficherEtat('Votre session a expiré. Connectez-vous de nouveau puis réessayez.', true);
                return;
            }
            if (!reponse.ok) throw new Error(`Le formulaire n’a pas pu être chargé (HTTP ${reponse.status}).`);
            await afficherFormulaire(documentPage, numero);
        } catch (error) {
            if (numero !== sequence) return;
            afficherEtat(error.message || 'Une erreur est survenue pendant le chargement.', true);
            console.error('Chargement du formulaire rapide impossible.', error);
        } finally {
            if (numero === sequence) busy = false;
        }
    }

    function ouvrir(lien, url) {
        previousFocus = document.activeElement;
        activeUrl = url;
        widePage = lien.dataset.quickCreate === 'wide';
        editMode = /^\/admin\/.+\/[^/]+\/change\/$/.test(url.pathname);
        rechargeDemandee = false;
        title.textContent = lien.dataset.quickCreateTitle || lien.textContent.trim() || 'Nouvelle fiche';
        dialog.classList.toggle('is-wide', widePage);
        overlay.setAttribute('aria-hidden', 'false');
        document.body.classList.add('wine-quick-create-open');
        overlay.querySelector('.wine-quick-create-close').focus();
        charger(url.toString());
    }

    document.addEventListener('click', function (event) {
        const lien = event.target.closest('a[href]');
        if (!lien || event.defaultPrevented || event.button !== 0 || event.metaKey ||
            event.ctrlKey || event.shiftKey || event.altKey || lien.target === '_blank' ||
            lien.dataset.quickCreate === 'off') return;

        const url = new URL(lien.href, window.location.href);
        if (url.origin !== window.location.origin || url.searchParams.has('_popup')) return;
        const pageAjout = /^\/admin\/.+\/add\/$/.test(url.pathname);
        const pageModification = /^\/admin\/.+\/[^/]+\/change\/$/.test(url.pathname);
        const pageLarge = lien.dataset.quickCreate === 'wide';
        const lienModifier = lien.matches('.databtn-edit') ||
            (Boolean(lien.closest('tr')) && pageModification);
        if (!pageAjout && !(pageModification && lienModifier) && !pageLarge) return;

        event.preventDefault();
        ouvrir(lien, url);
    });

    content.addEventListener('submit', async function (event) {
        const form = event.target.closest('form');
        if (!form || widePage) return;
        event.preventDefault();
        if (busy) return;
        if (!form.reportValidity()) {
            afficherFeedback(form, 'Vérifiez les champs obligatoires.', true);
            return;
        }

        const action = new URL(form.getAttribute('action') || activeUrl, window.location.href);
        if (action.origin !== window.location.origin) {
            afficherFeedback(form, 'Enregistrement refusé : adresse de formulaire invalide.', true);
            return;
        }

        const numero = ++sequence;
        busy = true;
        const donnees = new FormData(form);
        if (event.submitter && event.submitter.name) {
            donnees.append(event.submitter.name, event.submitter.value);
        } else {
            donnees.append('_save', '');
        }
        const boutons = Array.from(form.querySelectorAll('button[type="submit"], input[type="submit"]'));
        boutons.forEach((bouton) => { bouton.disabled = true; });
        afficherFeedback(form, 'Enregistrement en cours…');

        try {
            const ajouterAutre = event.submitter?.name === '_addanother' || donnees.has('_addanother');
            const reponse = await fetch(action, {
                method: (form.method || 'post').toUpperCase(),
                body: donnees,
                credentials: 'same-origin',
                headers: { Accept: 'text/html' },
            });
            if (numero !== sequence) return;

            const finalUrl = new URL(reponse.url, window.location.href);
            const documentPage = new DOMParser().parseFromString(await reponse.text(), 'text/html');
            if (estPageConnexion(documentPage)) {
                afficherFeedback(form, 'Votre session a expiré. Connectez-vous de nouveau puis réessayez.', true);
                return;
            }
            const retourCreation = /^\/admin\/.+\/add\/$/.test(finalUrl.pathname);
            if (reponse.redirected && !(ajouterAutre && retourCreation)) {
                rechargeDemandee = true;
                afficherSucces('Enregistré ! Actualisation de la liste…');
                minuteurSucces = window.setTimeout(() => fermer(), 650);
                return;
            }
            if (!reponse.ok) throw new Error(`L’enregistrement a échoué (HTTP ${reponse.status}).`);
            await afficherFormulaire(documentPage, numero);
            const formSuivant = content.querySelector('.change-form form');
            if (reponse.redirected && ajouterAutre && retourCreation && formSuivant) {
                afficherFeedback(formSuivant, 'Enregistré. Le formulaire est prêt pour un nouvel ajout.');
            } else if (formSuivant) {
                afficherFeedback(formSuivant, 'Enregistrement impossible : vérifiez les champs signalés.', true);
            }
        } catch (error) {
            if (numero !== sequence) return;
            afficherFeedback(form, error.message || 'Une erreur est survenue pendant l’enregistrement.', true);
            console.error('Enregistrement rapide impossible.', error);
        } finally {
            if (numero === sequence) {
                busy = false;
                boutons.forEach((bouton) => { bouton.disabled = false; });
            }
        }
    });

    overlay.addEventListener('click', function (event) {
        if (event.target.closest('[data-quick-create-close]')) fermer();
    });

    document.addEventListener('keydown', function (event) {
        if (overlay.getAttribute('aria-hidden') === 'true') return;
        if (event.key === 'Escape') {
            event.preventDefault();
            fermer();
        }
        if (event.key === 'Tab' && !overlay.contains(event.target)) {
            event.preventDefault();
            overlay.querySelector('.wine-quick-create-close').focus();
        }
    });
})();
