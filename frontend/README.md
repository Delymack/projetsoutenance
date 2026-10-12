# Lazan'i Betsileo — Frontend Angular

Application de **vente et promotion de vin** pour la société *Lazan'i Betsileo*
(Fianarantsoa, Madagascar). Projet de mémoire de L3 Informatique.

- **Framework** : Angular 18 (standalone components, `inject()`, signals)
- **UI** : Angular Material 18 (thème M3) + SCSS piloté par CSS variables
- **i18n** : `@ngx-translate/core` — FR / MG / EN
- **PWA** : manifest + Angular Service Worker + file de ventes hors ligne
- **Backend** : API REST Django REST Framework (non implémentée ici — mode mock par défaut)

---

## 1. Démarrage rapide

```bash
npm install
npm start           # http://localhost:4200
```

L'application fonctionne **sans backend** : `environment.useMock === true` et les
données proviennent de `src/app/core/data/mock-vins.ts` (12 vins, 3 promotions,
3 avis), avec une latence simulée de 600 ms pour rendre visibles les squelettes.

### Passer en mode API réelle

1. `src/environments/environment.ts` → `useMock: false`, `apiUrl: 'http://localhost:8000/api'`
2. Brancher le backend Django (endpoints attendus) :
   `GET /api/vins/`, `GET /api/vins/{id}/`, `GET /api/promotions/`,
   `GET /api/vins/{id}/avis/`, `POST /api/auth/login/`, `POST /api/ventes/`

### Commandes

| Commande | Rôle |
|---|---|
| `npm start` | Serveur de développement (rechargement à chaud) |
| `npm run build` | Build de production **avec** le service worker |
| `npm run watch` | Build de développement en continu |
| `npm test` | Tests unitaires (Karma + Jasmine, nécessite Chrome) |

> **Build hors ligne** : `optimization.fonts` est désactivé dans `angular.json`,
> car l'inlining des polices Google échoue sans accès à `fonts.googleapis.com`.
> Les polices Inter et Playfair Display restent chargées par le navigateur via
> les `<link>` de `src/index.html`, avec Georgia comme repli défini dans
> `styles.scss`.

---

## 2. Structure du projet

```
src/
├── index.html                     meta PWA, theme-color, Open Graph
├── main.ts                        bootstrapApplication
├── styles.scss                    variables CSS, thèmes clair/sombre, utilitaires
├── styles/
│   └── _material.scss             thème Angular Material (M3) clair + sombre
├── environments/                  useMock, apiUrl
├── assets/
│   ├── i18n/{fr,mg,en}.json       583 clés, parité vérifiée
│   ├── icons/                     icônes PWA (SVG)
│   └── images/vins/               12 illustrations de bouteilles (SVG généré)
└── app/
    ├── app.component.*            coquille : navbar + router-outlet + footer
    ├── app.config.ts              providers globaux (router, http, i18n, SW)
    ├── app.routes.ts              routage lazy de toutes les pages
    │
    ├── core/                      singletons : aucun composant ne vit ici
    │   ├── models/product.model.ts    interfaces TypeScript (Vin, PanierLigne…)
    │   ├── data/mock-vins.ts          jeu de données de démonstration
    │   ├── models/analytics.model.ts   CaseVente, SerieGraphique, IndicateursPeriode
    │   ├── data/
    │   │   ├── mock-vins.ts            jeu de données de démonstration
    │   │   └── mock-ventes.ts          historique de ventes simulé (90 jours)
    │   ├── services/
    │   │   ├── theme.service.ts       Bloc 1.1 — thème clair/sombre
    │   │   ├── langue.service.ts      Bloc 1.2 — FR / MG / EN
    │   │   ├── translate.loader.ts    chargement des JSON de traduction
    │   │   ├── connectivity.service.ts Bloc 1.5 — état en ligne / hors ligne
    │   │   ├── sync.service.ts        Bloc 1.5 — file d'attente des ventes
    │   │   ├── auth.service.ts        Bloc 6.37 — JWT en localStorage
    │   │   ├── panier.service.ts      Bloc 6.40 — BehaviorSubject + signals
    │   │   ├── vin.service.ts         catalogue (mock ou API)
    │   │   ├── ventes.service.ts      Bloc 4.22 — matrice, KPI, agrégats rapports
    │   │   ├── avis.service.ts        Bloc 5.29 — avis, moyenne, pagination
    │   │   ├── notification.service.ts Bloc 5.34 — permission + historique
    │   │   └── chatbot.service.ts     Bloc 5.35 — moteur de règles
    │   ├── guards/
    │   │   ├── auth.guard.ts          Bloc 6.37
    │   │   └── role.guard.ts          Bloc 6.37
    │   └── interceptors/
    │       └── auth.interceptor.ts    Bloc 6.38 — JWT + 401/403/500 → toasts
    │
    ├── layout/navbar/             Barre de navigation (thème, langue, notifications, panier)
    │
    ├── shared/components/         Composants réutilisables
    │   ├── skeleton/                Bloc 1.3 — <app-skeleton>
    │   ├── bandeau-hors-ligne/      Bloc 1.5 — bandeau « hors ligne »
    │   ├── countdown/               Bloc 2.12 — <app-countdown>
    │   ├── radar-profil/            Bloc 2 — radar SVG (remplace ngx-charts)
    │   ├── lecteur-code/            Bloc 2 — lecteur de code promo
    │   ├── promo-timeline/          Bloc 4.24 — <app-promo-timeline>
    │   ├── sales-heatmap/           Bloc 4.23 — <app-sales-heatmap>
    │   ├── review/                  Bloc 5.29 — <app-review>
    │   ├── share/                   Bloc 5.30 — <app-share>
    │   ├── notification-panneau/    Bloc 5.34 — <app-notification-panneau>
    │   └── chatbot/                 Bloc 5.35 — <app-chatbot>
    │
    └── features/                  Une page = un dossier, chargé en lazy
        ├── home/                Accueil (démo du Bloc 1)
        ├── auth/                 Connexion (reactive form typé)
        ├── catalogue/            Bloc 2
        ├── sommelier/            Bloc 2
        ├── quiz-gustatif/        Bloc 2 — quiz + radar de profil SVG
        ├── accords/              Bloc 2
        ├── scanner/              Bloc 2
        ├── promo/                Bloc 2 — routes + roue + carte à gratter
        ├── fidelite/             Bloc 2 — points, paliers, badges, récompenses
        ├── cashier/              Bloc 3 — caisse + écran client
        ├── dashboard/            Bloc 4 — KPI, heatmap, top vins, flux temps réel
        ├── rapports/             Bloc 4 — graphiques ngx-charts + heatmap
        ├── carte/                Bloc 4
        ├── comparateur/          Bloc 4
        ├── vin/                  Bloc 4 — fiche vin + avis + partage
        ├── cart/                 Bloc 2
        ├── favoris/              Bloc 5
        ├── historique/           Bloc 5
        └── parrainage/            Bloc 5
```

---

## 3. Bloc 1 — Expérience utilisateur (implémenté)

### 3.1 Dark mode + thème viticole

Le thème repose sur des **variables CSS** définies dans `styles.scss` :

| | Thème clair | Thème sombre |
|---|---|---|
| Fond | crème `#faf6ef` | noir profond `#0b0705` |
| Accent principal | bordeaux `#6b1f2a` | or `#c9a227` |
| Texte | `#2a1c16` | `#f0e6dc` |

`ThemeService` (signal) applique `data-theme` sur `<html>`, mémorise le choix
dans `localStorage` (`lb.theme`) et respecte `prefers-color-scheme` au premier
lancement. `suivreSysteme()` supprime la préférence.

Angular Material suit le même attribut : `styles/_material.scss` émet un seul
thème Material complet dans `:root`, puis **uniquement les variables de couleur
système** (`mat.system-level-colors`) dans `[data-theme='sombre']`. Cela évite
de dupliquer la typographie et la densité dans le CSS.

> **Règle de code** : aucun composant n'écrit une couleur en dur, uniquement
> `var(--lb-*)`. C'est ce qui rend le basculement instantané.

### 3.2 Multi-langue FR / MG / EN

`LangueService` lit `localStorage` (`lb.langue`), sinon la langue du navigateur,
sinon le français. `TranslateLoader` personnalisé met en cache les dictionnaires.
Les 3 fichiers JSON ont été validés : **445 clés strictement identiques**.

### 3.3 Skeleton loaders

`<app-skeleton>` accepte `forme="texte | titre | cercle | rectangle | carte | avatar"`,
`[lignes]`, `[largeur]`, `[hauteur]`, `[rayon]`. L'animation shimmer est en CSS
pur (`background-size: 300%` + `background-position`), donc coût CPU nul.

### 3.4 Animations et micro-interactions

- **Transitions de route** : `withViewTransitions()` (View Transitions API native,
  plus performant que `@angular/animations` pour un simple fondu).
- **Apparition en cascade** : `.lb-stagger > *` + `animation-delay: calc(var(--i) * 70ms)`,
  `--i` étant fourni par `@for (let i = $index)`.
- **Hover des cartes** : `.lb-card--hover` (élévation + bordure dorée + zoom de l'image).
- **Icônes Material** : ripple natif via `provideAnimationsAsync()`.
- `prefers-reduced-motion: reduce` désactive toutes les animations.

### 3.5 PWA + mode hors ligne

- `public/manifest.webmanifest` (nom, icônes, raccourcis Sommelier/Promos/Caisse).
- `ngsw-config.json` : 2 groupes d'assets + 4 groupes de données
  (catalogue, promotions, i18n, ventes POS) avec `freshness` et `maxAge`.
- `ConnectivityService` croise `navigator.onLine` et les événements navigateur.
- `SyncService` empile les ventes dans `localStorage` quand le réseau tombe et
  les renvoie à `POST /api/ventes/` au retour, avec un `id_client` stable
  (idempotence côté serveur).
- `<app-bandeau-hors-ligne>` affiche l'état + le nombre de ventes en attente.

> Le service worker n'est actif qu'en production : `ng serve` ne le génère pas.

---

## 4. Comment tester le Bloc 1

### 4.1 Thème

1. `npm start` → cliquer l'icône lune dans la navbar.
2. Vérifier le fond noir, les accents or, et le `<mat-icon>` qui devient `light_mode`.
3. **Recharger la page** (`F5`) : le thème sombre est conservé.
4. DevTools → `localStorage.lb.theme` vaut `"sombre"`.
5. Remettre sur clair, puis dans DevTools → *Rendering → Emulate CSS
   prefers-color-scheme: dark* : sans choix explicite, l'app suit le système.

### 4.2 Langue

1. Cliquer sur `🇫🇷 FR` → choisir *Malagasy* : toute l'interface change de langue.
2. Vérifier `localStorage.lb.langue === "mg"` et `<html lang="mg">`.
3. Contrôler la parité : `node -e "..."` ou ouvrir les 3 JSON et comparer les clés.

### 4.3 Skeleton loaders

1. `npm start` → onglet **Network** en mode *Slow 3G*.
2. Recharger `/catalogue` : les cartes fantômes apparaissent ~600 ms puis sont
   remplacées par les vrais vins.
3. Bloc 1.3 en action : le délai vient de `delay(MOCK_DELAY_MS)` dans `VinService`.

### 4.4 Animations

1. Naviguer entre `/` et `/catalogue` : fondu de page (View Transitions).
2. Sur l'accueil, les 3 cartes apparaissent en cascade (70 ms d'écart).
3. Survoler une carte : élévation + zoom.
4. *DevTools → Rendering → prefers-reduced-motion: reduce* : les animations
   s'arrêtent (accessibilité).

### 4.5 PWA / hors ligne

```bash
npm run build            # obligatoire : le SW n'existe pas en dev
npx http-server dist/lazanibetsileo/browser -p 8080 -c-1
```

1. Ouvrir `http://localhost:8080`, attendre l'enregistrement du SW
   (`DevTools → Application → Service Workers`).
2. **Cocher « Offline »** dans l'onglet Network.
3. Recharger : l'application fonctionne, le bandeau « Vous êtes hors ligne »
   apparaît en bas, et le catalogue (mis en cache par `dataGroups`) est servi
   depuis le cache.
4. Ajouter au panier puis recharger : le panier est persisté.
5. Repasser en ligne : la file d'attente se synchronise automatiquement.

### 4.6 Tests unitaires

`karma.conf.js` résout tout seul le Chrome du cache Puppeteer et lance
ChromeHeadless avec `--no-sandbox` (utile en conteneur). Aucune variable
d'environnement n'est nécessaire ; `CHROME_BIN` reste prioritaire si elle est
définie.

```bash
npm test -- --watch=false
```

Tests fournis : `panier.service.spec.ts` (quantités, stock, remises, livraison
offerte, codes promo), `theme.service.spec.ts` (bascule, persistance,
`data-theme`), `langue.service.spec.ts`, `parrainage.service.spec.ts`,
`vin.service.spec.ts`, `vin.service.promos-historique.spec.ts` (historique des
campagnes : exhaustivité, ordre chronologique, passée / en cours / à venir),
`ventes.service.spec.ts` (matrice 7×24, pic, séries par période, top vins,
indicateurs).

### 4.7 Audit automatique des pages (rendu réel)

Un navigateur headless visite chaque route et signale les erreurs console, les
requêtes en échec, les images cassées et les pages sans contenu. Les captures
d'écran sont déposées dans `outils/captures/`.

```bash
# 1. compiler puis servir le résultat (plus léger que `ng serve`)
npx ng build
node outils/serveur-statique.mjs 8080

# 2. auditer les 23 routes
node outils/audit-routes.mjs http://localhost:8080
```

Le script sort en code 1 si une route pose problème ou si une page est vide :
il peut donc être branché tel quel sur une intégration continue.

---

## 5. Bloc 2 — Catalogue, quiz, scanner, promotions, fidélité (implémenté)

- **Catalogue** : virtualisation via `@angular/cdk/scrolling`, filtres et tri.
- **Quiz gustatif** : 5 questions, profil calculé, radar de profil en SVG natif
  (`shared/components/radar-profil` — `@swimlane/ngx-charts` ne propose pas de
  radar), recommandation de vins, profil mémorisé (`lb.quiz.profil`).
- **Scanner** : `@zxing/browser` (caméra + import d'image), résolution par code
  EAN-13 (`VinService.parCodeBarres`), mode simulation avec les codes mockés.
- **Promotions** : compte à rebours, copie du code, ajout au panier.
- **Roue de la fortune** et **carte à gratter** : tirage pondéré par
  `PromoService`, une tentative par jeu et par jour (`lb.promo.jeux`), canvas de
  grattage avec seuil de révélation.
- **Fidélité** : solde de points persistant, paliers Bronze → Platine, badges
  débloqués, récompenses échangeables (`FideliteService`).

## 6. Blocs 4 et 5 — Données de vente et social (implémenté)

### 6.1 Frise des promotions (Bloc 4.24)

`<app-promo-timeline>` (`shared/components/promo-timeline`) affiche les campagnes
marketing sur douze mois glissants. Les blocs sont positionnés en pourcentage de
la largeur et répartis sur deux voies pour éviter les chevauchements ; un clic
ouvre le détail (dates, code promo, remise, vins concernés).

`VinService.listerHistoriquePromotions()` renvoie **toutes** les campagnes,
terminées comprises : la boutique n'affiche que les actives, la frise a besoin
de l'historique complet. En mode API, l'appel est
`GET /api/promotions/?inclure_terminees=true`.

La page `/promotions` charge les deux sources en un seul `forkJoin` (promotions
actives, historique, catalogue) : une seule passe de rendu, pas de squelette
intermédiaire.

### 6.2 Heatmap et agrégats de ventes (Bloc 4.22 et 4.23)

`VentesService` dérive tout d'un même historique simulé de 90 jours
(`core/data/mock-ventes.ts`) : c'est ce qui garantit que le dashboard et les
rapports affichent des chiffres cohérents entre eux.

- `matrice()` : 7 jours × 24 heures, `picVentes`, `meilleurMoment()` avec le jour.
- `caParPeriode()`, `topVins()`, `ventesParCategorie`, `efficacitePromos()`,
  `indicateurs()` : séries des graphiques de `/rapports`.
- `ajouterVenteLive()` alimente le flux « ventes en direct » du dashboard.

`<app-sales-heatmap>` rend la matrice en grille de 168 cases colorées, avec
infobulle au survol et détail au clic. Elle est intégrée au dashboard **et** aux
rapports.

### 6.3 Avis clients (Bloc 5.29)

`AvisService` centralise l'état des avis (aucun dans le composant) : moyenne,
répartition par note, pagination côté client. Le composant `<app-review>` affiche
la synthèse, le formulaire de dépôt et la liste paginée avec « j'aime ».

L'avis publié est inséré en tête de liste et le compteur de la fiche vin
(`nombreAvis`) est incrémenté : les deux écrans restent d'accord.

### 6.4 Partage (Bloc 5.30)

`<app-share>` produit de vrais `href` (Facebook, WhatsApp, Telegram, e-mail) :
le partage fonctionne même si `window.open` est bloqué. Le bouton de copie
utilise l'API presse-papiers avec repli silencieux (le lien reste affiché).

### 6.5 Notifications (Bloc 5.34)

`NotificationService` gère la permission du navigateur, les préférences par
catégorie (promotions, stock, commandes) et un historique persistant. Le panneau
est monté dans un `mat-menu` de la navbar ; `matMenuContent` +
`stopPropagation` le laissent ouvert pendant qu'on le manipule.

### 6.6 Chatbot (Bloc 5.35)

`ChatbotService` est un moteur de règles (aucune dépendance réseau) :
questions fréquentes, recommandations de vins, demande de conseiller. Les
réponses sont stockées sous forme de clés i18n et traduites au rendu, donc un
changement de langue se répercute aussi sur les messages déjà échangés.

---

## 7. Conventions de code

| Sujet | Convention |
|---|---|
| Fichiers | `kebab-case` : `panier.service.ts`, `vin-detail.component.ts` |
| Classes | `PascalCase` : `PanierService`, `VinDetailComponent` |
| Sélecteurs | préfixe `app-` : `app-skeleton`, `app-navbar` |
| Style URL | `styleUrl` (singulier) — API Angular 17+ |
| Détection de changement | `OnPush` sur **tous** les composants |
| Injection | `inject()` uniquement (jamais de constructeur injectable) |
| État | `signal` pour l'état local, `BehaviorSubject` pour l'état partagé |
| Formulaires | `FormBuilder.nonNullable` → types stricts, jamais de `!` |
| Couleurs | `var(--lb-*)` uniquement, jamais de valeur en dur |
| Textes | pipe `translate` avec une clé de `assets/i18n/fr.json` |

---

## 8. État d'avancement

| Bloc | Contenu | État |
|---|---|---|
| **1** | UX/UI : thème, i18n, skeletons, animations, PWA | ✅ fait |
| **2** | Sommelier, quiz, accords, scanner, promo, fidélité | fait (catalogue, sommelier, quiz + radar SVG, accords, scanner ZXing, promotions, roue, carte à gratter, fidélité) |
| **3** | Caisse : scanner, vocal, drag & drop, tactile, raccourcis, ticket, confettis | écran client fait |
| **4** | Dashboard, rapports, carte, timeline, heatmap, comparateur, fiche vin | fait (dashboard KPI + heatmap + temps réel, rapports graphiques + heatmap, frise des promotions, fiche vin) |
| **5** | Avis, partage, parrainage, favoris, historique, push, chatbot | fait (avis + partage + notifications + chatbot ; parrainage, favoris, historique déjà livrés au Bloc 2/5) |
| **6** | Lazy loading, guards, intercepteur, reactive forms, état, i18n | fait (virtual scroll : Bloc 4) |

Chaque page « squelette » affiche son numéro de bloc et la route est déjà
navigable : on peut implémenter les blocs dans l'ordre sans casser le build.