import { Injectable } from '@angular/core';
import { Observable, delay, map, of } from 'rxjs';
import { MOCK_CAVES } from '../data/mock-caves';
import { BlocPromo, CaseHeatmap, Cave } from '../models/cartographie.model';
import { Promotion } from '../models/product.model';

/** Palette d'indices pour la frise des promotions (0 → 5). */
export const PALETTE_PROMO = 6;

/** Jours de la semaine, du dimanche au samedi. */
export const JOURS_SEMAINE = 7;

/** Durée d'une heure d'ouverture simulée (ms). */
const DELAI_MOCK_MS = 220;

/**
 * Service de cartographie et d'analyse des ventes.
 *
 * Aucun accès réseau : les données proviennent des fixtures `mock-caves` et
 * d'une simulation déterministe des ventes sur 7 jours × 24 heures, suffisante
 * pour valider les graphiques avant le branchement sur l'API Django.
 *
 * La simulation est volontairement **déterministe** (graine fixe) afin que la
 * heatmap et les rapports affichent les mêmes chiffres d'un rechargement à
 * l'autre — une heatmap qui change à chaque `ng serve` rend les tests visuels
 * inutilisables.
 */
@Injectable({ providedIn: 'root' })
export class CartographieService {
  /**
   * Liste les caves de Madagascar.
   *
   * @param type filtre optionnel par type de point de vente ;
   * @param recherche nom ou ville recherché (insensible à la casse).
   */
  listerCaves(filtre: { type?: Cave['type'] | 'tous'; recherche?: string } = {}): Observable<Cave[]> {
    const type = filtre.type ?? 'tous';
    const terme = (filtre.recherche ?? '').trim().toLocaleLowerCase('fr');

    return of(MOCK_CAVES).pipe(
      delay(DELAI_MOCK_MS),
      map((caves) =>
        caves.filter((cave) => {
          if (type !== 'tous' && cave.type !== type) return false;
          if (!terme) return true;
          return (
            cave.nom.toLocaleLowerCase('fr').includes(terme) ||
            cave.ville.toLocaleLowerCase('fr').includes(terme)
          );
        }),
      ),
    );
  }

  /** Caves d'une ville donnée (utile pour la liste latérale). */
  cavesDeLaVille(ville: string): Cave[] {
    return MOCK_CAVES.filter((cave) => cave.ville === ville);
  }

  /** Caves proches d'un point, triées par distance approximative. */
  cavesProches(latitude: number, longitude: number): Cave[] {
    return [...MOCK_CAVES]
      .map((cave) => ({ cave, distance: this.distanceKm(latitude, longitude, cave.latitude, cave.longitude) }))
      .sort((a, b) => a.distance - b.distance)
      .map((entree) => entree.cave);
  }

  /**
   * Heatmap des ventes : grille 7 jours × 24 heures.
   *
   * Chaque case reçoit une quantité et un CA cohérents avec les créneaux
   * commerciaux : creux le dimanche matin, pic le vendredi soir, gros volume le
   * samedi (marché de Fianarantsoa).
   */
  heatmapVentes(): Observable<CaseHeatmap[]> {
    const cases: CaseHeatmap[] = [];
    for (let jour = 0; jour < JOURS_SEMAINE; jour += 1) {
      for (let heure = 0; heure < 24; heure += 1) {
        const intensite = this.intensiteCase(jour, heure);
        if (intensite <= 0) {
          cases.push({ jour, heure, quantite: 0, chiffreAffaires: 0, tickets: 0 });
          continue;
        }
        // Prix moyen de 72 000 Ar par bouteille (tirage déterministe).
        const prixMoyen = 58_000 + this.bruit(jour * 31 + heure * 7) * 34_000;
        const quantite = Math.max(1, Math.round(intensite * 14));
        cases.push({
          jour,
          heure,
          quantite,
          chiffreAffaires: Math.round(quantite * prixMoyen),
          tickets: Math.max(1, Math.round(quantite / 2.4)),
        });
      }
    }
    return of(cases).pipe(delay(DELAI_MOCK_MS));
  }

  /** Frise chronologique des promotions, de la plus ancienne à la plus proche. */
  timelinePromotions(promotions: Promotion[]): BlocPromo[] {
    const maintenant = Date.now();
    return promotions
      .filter((promo) => promo.actif)
      .map((promo, index) => {
        const debut = new Date(promo.dateDebut).getTime();
        const fin = new Date(promo.dateFin).getTime();
        const duree = Math.max(1, fin - debut);
        const progression = Math.min(1, Math.max(0, (maintenant - debut) / duree));
        return {
          promotionId: promo.id,
          libelle: promo.libelle,
          remisePct: promo.remisePct,
          dateDebut: promo.dateDebut,
          dateFin: promo.dateFin,
          nbVins: promo.vinsIds.length,
          couleur: index % PALETTE_PROMO,
          progression,
          active: maintenant >= debut && maintenant <= fin,
        };
      })
      .sort((a, b) => a.dateDebut.localeCompare(b.dateDebut));
  }

  /** Distance approximative entre deux points (formule de haversine). */
  private distanceKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
    const rayonTerre = 6371;
    const rad = Math.PI / 180;
    const dLat = (lat2 - lat1) * rad;
    const dLon = (lon2 - lon1) * rad;
    const a =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2;
    return 2 * rayonTerre * Math.asin(Math.sqrt(a));
  }

  /**
   * Intensité commerciale d'un créneau, entre 0 (fermé) et ~1 (pic).
   *
   * Déterministe : pas de `Math.random`, sinon la heatmap changerait à chaque
   * rechargement et le rendu serait impossible à contrôler.
   */
  private intensiteCase(jour: number, heure: number): number {
    // Fermeture : dimanche de 13h à 17h, et de 22h à 8h tous les jours.
    if (heure < 8 || heure >= 22) return 0;
    if (jour === 0 && heure >= 13 && heure < 17) return 0;

    // Courbe horaire : creux le matin, montée à midi, pic 18h–20h.
    const heureCible = [0.12, 0.08, 0.05, 0.06, 0.1, 0.18, 0.42, 0.85, 0.68, 0.45, 0.3, 0.18];
    let base = heureCible[heure - 8] ?? 0;

    // Pondération par jour : samedi très fort, dimanche faible.
    const poidsJour = [0.28, 0.75, 0.82, 0.78, 0.9, 1, 0.95][jour] ?? 0.7;
    base *= poidsJour;

    // Micro-variation pour éviter une grille trop régulière.
    return Math.min(1, base * (0.82 + this.bruit(jour * 13 + heure) * 0.36));
  }

  /** Pseudo-aléatoire déterministe dans [0, 1] à partir d'un entier. */
  private bruit(graine: number): number {
    const x = Math.sin(graine * 12.9898) * 43758.5453;
    return x - Math.floor(x);
  }
}
