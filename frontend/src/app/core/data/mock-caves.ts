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
    latitude: -21.45331,
    longitude: 47.08785,
    adresse: "Rue Alphonse Rakotozafy, Isaha, Fianarantsoa 301 — BP 1496",
    telephone: '+261 20 75 901 27',
    horaires: 'Lun – Sam : 8h00 – 18h00 · Dim : 9h00 – 13h00',
    description:
      'Dépôt principal et cave de maturation. Dégustation guidée tous les samedis à 10h.',
    vinsIds: ['v-001', 'v-002', 'v-003', 'v-004', 'v-005', 'v-006', 'v-007', 'v-008', 'v-009', 'v-010', 'v-011', 'v-012'],
  },
];
