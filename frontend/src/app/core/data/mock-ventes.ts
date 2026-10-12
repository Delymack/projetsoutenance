/**
 * Jeu de données analytiques — Lazan'i Betsileo.
 *
 * Objectif : alimenter le tableau de bord, les rapports, la heatmap des ventes et
 * la frise des promotions **sans backend**, tout en restant reproductible.
 *
 * Choix important : les ventes sont produites par un générateur pseudo-aléatoire
 * *déterministe* (mulberry32, graine fixe). Deux conséquences utiles :
 *  - les captures d'écran et les chiffres du mémoire sont identiques d'une
 *    démonstration à l'autre ;
 *  - les tests unitaires peuvent vérifier des agrégats stables (total, maximum).
 *
 * Le profil horaire et le poids des jours reproduisent l'ouverture réelle de la
 * cave de Fianarantsoa : activité faible la nuit, deux pics (matin et fin
 * d'après-midi), week-end plus charged, dimanche Scholars' Day le matin.
 */

import { WineCategory } from '../models/product.model';
import { MOCK_PROMOS_HISTORIQUE, MOCK_VINS } from './mock-vins';

/** Une vente reconstituée (une ligne de ticket, plusieurs bouteilles possibles). */
export interface VenteUnitaire {
  /** Instant de la vente (heure de la journée comprise, pour la heatmap). */
  date: Date;
  /** Vin vendu. */
  vinId: string;
  /** Catégorie du vin, dédupliquée ici pour éviter un `find` à chaque agrégat. */
  categorie: WineCategory;
  /** Nombre de bouteilles. */
  quantite: number;
  /** Chiffre d'affaires de la ligne, en Ariary, remise comprise. */
  ca: number;
  /** Promotion appliquée (`null` hors promotion). */
  promoId: string | null;
  /** Part du CA laissée par la remise de la promotion (en Ariary). */
  remise: number;
}

/** Nombre de jours d'historique simulé (3 mois glissants). */
export const JOURS_HISTORIQUE = 90;

/** Graine du générateur : fixe, pour que la démonstration soit reproductible. */
const GRAINE = 20261005;

/**
 * Générateur pseudo-aléatoire déterministe (mulberry32).
 * 32 bits d'état, période longue, distribution correcte pour notre usage :
 * un `Math.random()` rendrait les captures du mémoire différentes à chaque fois.
 */
function mulberry32(graine: number): () => number {
  let etat = graine >>> 0;
  return () => {
    etat = (etat + 0x6d2b79f5) >>> 0;
    let t = etat;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Poids relatif de chaque heure de la journée (0 → minuit).
 * Le total n'a pas besoin de valoir 1 : il sert de proportion d'affectation.
 */
const PROFIL_HORAIRE = [
  0, 0, 0, 0, 0.05, 0.3, 1.1, 2.3, 3.5, 5.0, 6.2, 6.8, 6.0, 5.2, 4.9, 5.1, 6.1, 7.4, 7.0, 5.3, 3.5, 2.0, 0.9,
  0.35,
];

/** Poids relatif de chaque jour de la semaine (0 = lundi). */
const POIDS_JOUR = [0.86, 0.82, 0.9, 1.02, 1.26, 1.45, 0.72];

/** Nombre moyen de bouteilles par jour ouvré, avant pondérations. */
const BOUTEILLES_PAR_JOUR = 24;

/** Probabilité de vente par tranche horaire et par jour (faible, pour le bruit). */
const PROBABILITE_PAR_JOUR = 0.72;

/** Génère l'historique de ventes déterministe des `JOURS_HISTORIQUE` derniers jours. */
export function genererVentesMock(maintenant: Date = new Date()): VenteUnitaire[] {
  const alea = mulberry32(GRAINE);
  const ventes: VenteUnitaire[] = [];

  // Prix et catégories, résolus une seule fois.
  const prixParId = new Map<string, { prix: number; categorie: WineCategory }>(
    MOCK_VINS.map((vin) => [vin.id, { prix: vin.prix, categorie: vin.categorie }]),
  );
  const ids = [...prixParId.keys()];
  const promotions = MOCK_PROMOS_HISTORIQUE;

  for (let recule = JOURS_HISTORIQUE - 1; recule >= 0; recule--) {
    const jour = new Date(maintenant);
    jour.setHours(0, 0, 0, 0);
    jour.setDate(jour.getDate() - recule);
    const indexJour = (jour.getDay() + 6) % 7; // 0 = lundi

    // Promotion en cours ce jour-là (la plus récente si plusieurs se chevauchent).
    const promoDuJour = promotions.find(
      (promo) =>
        new Date(promo.dateDebut).getTime() <= jour.getTime() &&
        new Date(promo.dateFin).getTime() >= jour.getTime(),
    );

    // Tendance douce : la cave se/developpe sur la periode (+25 %).
    const tendance = 0.85 + (1 - recule / JOURS_HISTORIQUE) * 0.3;
    // Les affiches de promotion attirent du monde.
    const bonusPromo = promoDuJour ? 1.45 : 1;

    const attendu =
      BOUTEILLES_PAR_JOUR * POIDS_JOUR[indexJour] * tendance * bonusPromo * (0.75 + alea() * 0.5);
    const nbTransactions = Math.max(0, Math.round(attendu * PROBABILITE_PAR_JOUR));

    for (let t = 0; t < nbTransactions; t++) {
      // Distribution dans la journée selon le profil horaire (cumulé pondéré).
      const tirage = alea() * PROFIL_HORAIRE.reduce((somme, poids) => somme + poids, 0);
      let cumule = 0;
      let heure = PROFIL_HORAIRE.length - 1;
      for (let h = 0; h < PROFIL_HORAIRE.length; h++) {
        cumule += PROFIL_HORAIRE[h];
        if (tirage <= cumule) {
          heure = h;
          break;
        }
      }

      const vinId = ids[Math.floor(alea() * ids.length)];
      const vin = prixParId.get(vinId);
      if (!vin) continue;

      const quantite = alea() < 0.72 ? 1 : alea() < 0.94 ? 2 : 3;

      // La promotion ne s'applique qu'aux vins de son assortiment.
      const promoApplicable =
        promoDuJour && promoDuJour.vinsIds.includes(vinId) && promoDuJour.remisePct
          ? promoDuJour
          : null;
      const taux = promoApplicable ? (promoApplicable.remisePct ?? 0) / 100 : 0;

      const prixPleins = vin.prix * quantite;
      const ca = Math.round(prixPleins * (1 - taux));

      const date = new Date(jour);
      date.setHours(heure, Math.floor(alea() * 60), Math.floor(alea() * 60), 0);

      ventes.push({
        date,
        vinId,
        categorie: vin.categorie,
        quantite,
        ca,
        promoId: promoApplicable?.id ?? null,
        remise: prixPleins - ca,
      });
    }
  }

  return ventes;
}

/**
 * Génère une vente « en direct » (dashboard temps réel).
 * Utilise `Math.random()` : contrairement à l'historique, ces lignes doivent
 * Parece différentes à chaque rafraîchissement, sinon la démonstration fige.
 */
export function genererVenteLive(maintenant: Date = new Date()): VenteUnitaire {
  const vin = MOCK_VINS[Math.floor(Math.random() * MOCK_VINS.length)];
  const quantite = 1 + Math.floor(Math.random() * 3);
  return {
    date: maintenant,
    vinId: vin.id,
    categorie: vin.categorie,
    quantite,
    ca: vin.prix * quantite,
    promoId: null,
    remise: 0,
  };
}