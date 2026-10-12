import { Routes } from '@angular/router';

/**
 * Routes du module Tableau de bord.
 * Chargé paresseusement : réservé aux rôles admin et gestionnaire.
 */
export const DASHBOARD_ROUTES: Routes = [
  {
    path: '',
    title: 'Tableau de bord',
    loadComponent: () => import('./dashboard.component').then((m) => m.DashboardComponent),
  },
];
