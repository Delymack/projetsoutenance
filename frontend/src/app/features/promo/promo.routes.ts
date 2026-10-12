import { Routes } from '@angular/router';

/** Routes des promotions; les anciennes URL de jeux renvoient à la liste simple. */
export const PROMO_ROUTES: Routes = [
  {
    path: '',
    title: 'Promotions',
    loadComponent: () =>
      import('./promo-list.component').then((m) => m.PromoListComponent),
  },
  {
    path: 'roue',
    pathMatch: 'full',
    redirectTo: '',
  },
  {
    path: 'carte-a-gratter',
    pathMatch: 'full',
    redirectTo: '',
  },
];