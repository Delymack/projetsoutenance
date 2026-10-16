/**
 * Environnement de développement.
 *
 * Le frontend utilise l'API Django en développement comme en production.
 */
export const environment = {
  production: false,
  // Le catalogue, les promotions et les ventes viennent de l'API Django.
  // Repasser à `true` ne sert qu'à travailler sans backend (démonstration
  // hors ligne), au prix d'un catalogue figé dans `core/data/mock-vins.ts`.
  useMock: false,
  /** URL de base de l'API Django. */
  apiUrl: 'http://127.0.0.1:8000/api',
  /** Nom affiché dans le bandeau de développement. */
  nomApp: 'Lazan\'i Betsileo',
};