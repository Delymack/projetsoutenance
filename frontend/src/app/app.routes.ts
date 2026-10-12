import { Routes } from '@angular/router';

import { authGuard, invitationGuard } from './core/guards/auth.guard';
import { roleGuard } from './core/guards/role.guard';

/**
 * Routage principal.
 *
 * Chaque « module métier » est chargé via `loadComponent` (composant unique) ou
 * `loadChildren` (ensemble de pages). Rien n'est chargé tant que la route n'est
 * pas visitée : le bundle initial ne contient que la coquille (navbar, shell).
 *
 * Les guards :
 *  - `authGuard`  → exige un JWT ;
 *  - `roleGuard`  → exige un rôle déclaré dans `data.roles`.
 */
export const routes: Routes = [
  {
    path: '',
    title: "Lazan'i Betsileo",
    loadComponent: () => import('./features/home/home.component').then((m) => m.HomeComponent),
  },
  {
    path: 'catalogue',
    title: 'Catalogue',
    loadComponent: () => import('./features/catalogue/catalogue.component').then((m) => m.CatalogueComponent),
  },
  {
    path: 'vin/:id',
    title: 'Fiche vin',
    loadComponent: () => import('./features/vin/vin-detail.component').then((m) => m.VinDetailComponent),
  },
  {
    path: 'panier',
    title: 'Panier',
    loadComponent: () => import('./features/cart/cart.component').then((m) => m.CartComponent),
  },
  {
    path: 'favoris',
    title: 'Favoris',
    loadComponent: () => import('./features/favoris/favoris.component').then((m) => m.FavorisComponent),
  },

 // ---------- expérience client ----------
  {
    path: 'scanner',
    title: 'Scanner',
    loadComponent: () => import('./features/scanner/scanner.component').then((m) => m.ScannerComponent),
  },
  {
    path: 'promotions',
    title: 'Promotions',
    loadChildren: () => import('./features/promo/promo.routes').then((m) => m.PROMO_ROUTES),
  },

 // ---------- caisse / POS (rôle vendeur) ----------
  {
    path: 'caisse',
    title: 'Caisse',
    canActivate: [authGuard, roleGuard],
    data: { roles: ['admin', 'gestionnaire', 'vendeur'] },
    loadComponent: () => import('./features/cashier/cashier.component').then((m) => m.CashierComponent),
  },
  {
    // Écran client : affiché sur un écran face au client. `sansChrome` masque la
    // navbar et le footer (voir AppComponent), `authGuard` évite d'exposer le
    // panier de la caisse à un visiteur non connecté.
    path: 'ecran-client',
    title: 'Écran client',
    canActivate: [authGuard],
    data: { sansChrome: true, ecranClient: true },
    loadComponent: () =>
      import('./features/cashier/customer-display.component').then((m) => m.CustomerDisplayComponent),
  },

 // ---------- visualisation ----------
  {
    path: 'dashboard',
    title: 'Tableau de bord',
    canActivate: [authGuard, roleGuard],
    data: { roles: ['admin', 'gestionnaire'] },
    loadChildren: () => import('./features/dashboard/dashboard.routes').then((m) => m.DASHBOARD_ROUTES),
  },
  {
 // équipe : réception des commandes passées par les clients.
    path: 'commandes',
    title: 'Commandes reçues',
    canActivate: [authGuard, roleGuard],
    data: { roles: ['admin', 'gestionnaire', 'vendeur'] },
    loadComponent: () =>
      import('./features/commandes/commandes-recues.component').then((m) => m.CommandesRecuesComponent),
  },
  {
    path: 'rapports',
    title: 'Rapports',
    canActivate: [authGuard, roleGuard],
    data: { roles: ['admin', 'gestionnaire'] },
    loadComponent: () => import('./features/rapports/rapports.component').then((m) => m.RapportsComponent),
  },

  // ---------- Admin section ----------
  {
    path: 'admin',
    loadChildren: () => import('./features/admin/admin.routes').then((m) => m.ADMIN_ROUTES),
  },

 // ---------- social ----------
  {
 // espace client : commandes, messages, favoris, profil.
    path: 'profil',
    title: 'Mon profil',
    canActivate: [authGuard],
    loadComponent: () => import('./features/profil/profil.component').then((m) => m.ProfilComponent),
  },
  {
 // passer commande (client connecté).
    path: 'commande',
    title: 'Commande',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/commande/commande.component').then((m) => m.CommandeComponent),
  },
  {
    path: 'historique',
    title: 'Historique',
    canActivate: [authGuard],
    loadComponent: () => import('./features/historique/historique.component').then((m) => m.HistoriqueComponent),
  },

  // ---------- Auth ----------
  {
    path: 'connexion',
    title: 'Connexion',
    canActivate: [invitationGuard],
    loadComponent: () => import('./features/auth/login.component').then((m) => m.LoginComponent),
  },
  {
 // inscription client : exigée avant tout ajout au panier.
    path: 'inscription',
    title: 'Inscription',
    canActivate: [invitationGuard],
    loadComponent: () =>
      import('./features/auth/inscription.component').then((m) => m.InscriptionComponent),
  },

  // ---------- 404 ----------
  {
    path: '**',
    title: 'Page introuvable',
    loadComponent: () => import('./features/not-found.component').then((m) => m.NotFoundComponent),
  },
];