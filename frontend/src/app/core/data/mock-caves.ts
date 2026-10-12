/**
 * Données mockées — cartographie des caves.
 *
 * Périmètre unique de la société Lazan'i Betsileo : la maison mère de
 * Fianarantsoa. Les coordonnées sont réelles afin que la carte Leaflet soit
 * cohérente ; horaires, téléphone et références de vins sont fictifs.
 */
import { Cave } from '../models/cartographie.model';

export const MOCK_CAVES: Cave[] = [
  {
    id: 'cav-fianarantsoa',
    nom: 'Lazan\'i Betsileo — Maison mère',
    type: 'magasin',
    ville: 'Fianarantsoa',
    region: 'Haute Matsiatra',
    latitude: -21.2989,
    longitude: 47.0344,
    adresse: 'Lot II B 14, Avenue de l\'Indépendance, Fianarantsoa 301',
    telephone: '+261 32 45 678 90',
    horaires: 'Lun – Sam : 8h00 – 18h00 · Dim : 9h00 – 13h00',
    description:
      'Dépôt principal et cave de maturation. Dégustation guidée tous les samedis à 10h.',
    vinsIds: ['v-001', 'v-002', 'v-003', 'v-004', 'v-005', 'v-006', 'v-007', 'v-008', 'v-009', 'v-010', 'v-011', 'v-012'],
  },
];
