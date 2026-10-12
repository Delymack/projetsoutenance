import { Routes } from '@angular/router';

import { authGuard } from '../../core/guards/auth.guard';
import { roleGuard } from '../../core/guards/role.guard';
import { AdminLayoutComponent } from './admin-layout.component';

/**
 * Routes de la section d'administration.
 * Toutes les routes sont protégées par authGuard + roleGuard (admin, gestionnaire).
 */
export const ADMIN_ROUTES: Routes = [
  {
    path: '',
    component: AdminLayoutComponent,
    canActivate: [authGuard, roleGuard],
    data: { roles: ['admin', 'gestionnaire'] },
    children: [
      {
        path: '',
        redirectTo: 'dashboard',
        pathMatch: 'full',
      },
      {
        path: 'dashboard',
        title: 'Tableau de bord',
        loadComponent: () =>
          import('./dashboard/admin-dashboard.component').then((m) => m.AdminDashboardComponent),
      },
      {
        path: 'commandes',
        title: 'Commandes',
        loadComponent: () =>
          import('./commandes/admin-commandes.component').then((m) => m.AdminCommandesComponent),
      },
      {
        path: 'clients',
        title: 'Clients',
        loadComponent: () =>
          import('./clients/admin-clients.component').then((m) => m.AdminClientsComponent),
      },
      {
        path: 'catalogue',
        title: 'Catalogue',
        loadComponent: () =>
          import('./catalogue/admin-catalogue.component').then((m) => m.AdminCatalogueComponent),
      },
      {
        path: 'fidelite',
        title: 'Fidélité',
        loadComponent: () =>
          import('./fidelite/admin-fidelite.component').then((m) => m.AdminFideliteComponent),
      },
      {
        path: 'rapports',
        title: 'Rapports',
        loadComponent: () =>
          import('./rapports/admin-rapports.component').then((m) => m.AdminRapportsComponent),
      },
      {
        path: 'parametres',
        title: 'Paramètres',
        loadComponent: () =>
          import('./parametres/admin-parametres.component').then((m) => m.AdminParametresComponent),
      },
    ],
  },
];