import { Injectable, computed, signal } from '@angular/core';

import { genererVenteLive, genererVentesMock, VenteUnitaire } from '../data/mock-ventes';
import { MOCK_PROMOS_HISTORIQUE, MOCK_VINS } from '../data/mock-vins';
import {
  CaseVente,
  IndicateursPeriode,
  LigneEfficacite,
  PeriodeRapport,
  SerieGraphique,
  VenteCategorie,
  VenteLive,
} from '../models/analytics.model';
import { Promotion } from '../models/product.model';

/** Clés techniques des catégories, dans l'ordre d'affichage des graphiques. */
const CATEGORIES: { cle: VenteCategorie['categorie']; suffixeCle: string }[] = [
  { cle: 'rouge', suffixeCle: 'rouge' },
  { cle: 'blanc', suffixeCle: 'blanc' },
  { cle: 'rose', suffixeCle: 'rose' },
  { cle: 'mousseux', suffixeCle: 'mousseux' },
  { cle: 'petit-lait', suffixeCle: 'petitLait' },
  { cle: 'liqueur', suffixeCle: 'liqueur' },
];

/** Nombre maximum de lignes conservées dans le flux « en direct ». */
const TAILLE_FLUX = 25;

/** Bornes de la période demandée (bornes incluses, timestamps). */
interface Bornes {
  debut: number;
  fin: number;
}

/**
 * Service de ventes et d'analyse.
 *
 * C'est la source de vérité des chiffres affichés par le tableau de bord, les
 * rapports, la heatmap et la frise des promotions. En mode mock il reconstruit un
 * historique déterministe de 90 jours ; en mode API, il suffira de remplacer le
 * contenu de `ventesInterne` par le résultat de `GET /api/ventes/` : tous les
 * agrégats ci-dessous sont purs et continueront de fonctionner.
 *
 * Les méthodes d'agrégat sont volontairement des fonctions (et non des signaux) :
 * les composants les enveloppent dans `computed()` avec leurs propres paramètres
 * (période, nombre de lignes), ce qui évite un signal par combinaison possible.
 */
@Injectable({ providedIn: 'root' })
export class VentesService {
  /**
   * Historique brut. `signal` et non `const` : le tableau de bord y ajoute les
   * ventes « en direct » via `ajouterVenteLive()`, ce qui met à jour tous les
   * agrégats (KPI du jour, heatmap, top vins) sans calcul supplémentaire.
   */
  private readonly historique = signal<VenteUnitaire[]>(genererVentesMock());

  /** Ventes du jour, les plus récentes d'abord. */
  readonly ventesDuJour = computed(() =>
    this.historique()
      .filter((vente) => this.estAujourdhui(vente.date))
      .sort((a, b) => b.date.getTime() - a.date.getTime()),
  );

 /** Flux « en direct » : les ventes du jour, formatées pour l'UI. */
  readonly fluxLive = computed<VenteLive[]>(() =>
    this.ventesDuJour().slice(0, TAILLE_FLUX).map((vente) => this.versVenteLive(vente)),
  );

  /** Total du jour en Ariary. */
  readonly caJour = computed(() =>
    this.ventesDuJour().reduce((somme, vente) => somme + vente.ca, 0),
  );

  /** Nombre de tickets encaissés aujourd'hui. */
  readonly ticketsJour = computed(() => this.ventesDuJour().length);

  /** Bouteilles vendues aujourd'hui. */
  readonly bouteillesJour = computed(() =>
    this.ventesDuJour().reduce((somme, vente) => somme + vente.quantite, 0),
  );

  /** Panier moyen du jour, en Ariary. */
  readonly panierMoyenJour = computed(() => this.panierMoyen(this.ventesDuJour()));

  /**
 * Heatmap 7 jours × 24 heures.
   * Chaque case est la somme des ventes de la période, toutes catégories
   * confondues : la lecture attendue est « quand la cave vend-elle ? ».
   */
  readonly matrice = computed<CaseVente[]>(() => {
    const cases: CaseVente[] = [];
    for (let jour = 0; jour < 7; jour++) {
      for (let heure = 0; heure < 24; heure++) {
        cases.push({ jour, heure, ventes: 0, ca: 0 });
      }
    }

    const index = new Map(cases.map((cellule) => [`${cellule.jour}-${cellule.heure}`, cellule]));
    for (const vente of this.historique()) {
      const jour = (vente.date.getDay() + 6) % 7; // 0 = lundi
      const cellule = index.get(`${jour}-${vente.date.getHours()}`);
      if (!cellule) continue;
      cellule.ventes += vente.quantite;
      cellule.ca += vente.ca;
    }
    return cases;
  });

  /** Maximum de bouteilles sur une case : sert à l'échelle de couleur. */
  readonly picVentes = computed(() =>
    this.matrice().reduce((maximum, cellule) => Math.max(maximum, cellule.ventes), 0),
  );

  /**
   * Créneau le plus rentable : jour de la semaine et heure qui cumulent le plus
   * de bouteilles. Le libellé du jour est traduit par le composant qui affiche
   * ce résumé — le service ne connaît pas i18n.
   */
  readonly meilleurMoment = computed(() => {
    const cumul = new Map<string, { jour: number; heure: number; ventes: number }>();
    for (const cellule of this.matrice()) {
      const cle = `${cellule.jour}-${cellule.heure}`;
      const actuel = cumul.get(cle) ?? { jour: cellule.jour, heure: cellule.heure, ventes: 0 };
      actuel.ventes += cellule.ventes;
      cumul.set(cle, actuel);
    }
    return [...cumul.values()].sort((a, b) => b.ventes - a.ventes)[0] ?? { jour: 0, heure: 0, ventes: 0 };
  });

 // --- Agrégats pour les rapports ---

  /**
   * Série principale du rapport : chiffre d'affaires agrégé selon la période.
   *  - `jour`    → les 7 derniers jours ;
   *  - `semaine` → les 8 dernières semaines ;
   *  - `mois`    → les 12 derniers mois ;
   *  - `annee`   → les 12 derniers mois (l'historique simulé ne couvre pas
   *                d'année entière : on ne fabrique pas de Vide).
   */
  caParPeriode(periode: PeriodeRapport): SerieGraphique[] {
    const ventes = this.historique();
    const maintenant = new Date();

    if (periode === 'jour') {
      const series: SerieGraphique[] = [];
      for (let recule = 6; recule >= 0; recule--) {
        const jour = new Date(maintenant);
        jour.setHours(0, 0, 0, 0);
        jour.setDate(jour.getDate() - recule);
        series.push({
          name: jour.toLocaleDateString('fr-FR', { weekday: 'short' }).replace('.', ''),
          value: this.sommeCa(ventes.filter((vente) => this.estMemeJour(vente.date, jour))),
        });
      }
      return series;
    }

    if (periode === 'semaine') {
      const series: SerieGraphique[] = [];
      for (let recule = 7; recule >= 0; recule--) {
        const fin = new Date(maintenant);
        fin.setDate(fin.getDate() - recule * 7);
        const debut = new Date(fin);
        debut.setDate(debut.getDate() - 6);
        debut.setHours(0, 0, 0, 0);
        series.push({
          name: `S${this.numeroSemaine(fin)}`,
          value: this.sommeCa(ventes.filter((vente) => this.dansBornes(vente.date, debut, fin))),
        });
      }
      return series;
    }

    // `mois` et `annee` : 12 points mensuels.
    const series: SerieGraphique[] = [];
    for (let recule = 11; recule >= 0; recule--) {
      const debut = new Date(maintenant.getFullYear(), maintenant.getMonth() - recule, 1);
      const fin = new Date(maintenant.getFullYear(), maintenant.getMonth() - recule + 1, 0, 23, 59, 59);
      series.push({
        name: debut.toLocaleDateString('fr-FR', { month: 'short' }).replace('.', ''),
        value: this.sommeCa(ventes.filter((vente) => this.dansBornes(vente.date, debut, fin))),
      });
    }
    return series;
  }

  /** Top `nombre` vins par volume vendu. */
  topVins(nombre = 5): SerieGraphique[] {
    const cumul = new Map<string, number>();
    for (const vente of this.historique()) {
      cumul.set(vente.vinId, (cumul.get(vente.vinId) ?? 0) + vente.quantite);
    }
    return [...cumul.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, nombre)
      .map(([vinId, ventes]) => ({ name: this.nomVin(vinId), value: ventes }));
  }

  /** Répartition des bouteilles vendues par catégorie de vin. */
  readonly ventesParCategorie = computed<VenteCategorie[]>(() => {
    const cumul = new Map<string, number>();
    for (const vente of this.historique()) {
      cumul.set(vente.categorie, (cumul.get(vente.categorie) ?? 0) + vente.quantite);
    }
    const total = [...cumul.values()].reduce((somme, valeur) => somme + valeur, 0);
    return CATEGORIES.map(({ cle, suffixeCle }) => ({
      name: suffixeCle,
      categorie: cle,
      value: Math.round(((cumul.get(cle) ?? 0) / Math.max(total, 1)) * 100),
    }));
  });

  /**
   * Efficacité des promotions : volume écoulé pendant chaque campagne, rapporté
   * au volume total. Les campagnes sans vente (à venir) remontent avec 0 %.
   */
  readonly efficacitePromos = computed<LigneEfficacite[]>(() => {
    const ventes = this.historique();
    const volumeTotal = ventes.reduce((somme, vente) => somme + vente.quantite, 0) || 1;

    return MOCK_PROMOS_HISTORIQUE.map((promo) => {
      const concernees = ventes.filter((vente) => vente.promoId === promo.id);
      return {
        id: promo.id,
        libelle: promo.libelle,
        ventes: concernees.reduce((somme, vente) => somme + vente.quantite, 0),
        ca: concernees.reduce((somme, vente) => somme + vente.ca, 0),
        volume: Math.round(
          (concernees.reduce((somme, vente) => somme + vente.quantite, 0) / volumeTotal) * 1000,
        ) / 10,
      };
    });
  });

  /** Indicateurs de la période, avec évolution par rapport à la précédente. */
  indicateurs(periode: PeriodeRapport): IndicateursPeriode {
    const ventes = this.historique();
    const courante = this.fenetre(periode, 0);
    const precedente = this.fenetre(periode, 1);

    const dansCourante = ventes.filter((vente) => this.dansBornes(vente.date, courante.debut, courante.fin));
    const dansPrecedente = ventes.filter((vente) =>
      this.dansBornes(vente.date, precedente.debut, precedente.fin),
    );

    const ca = this.sommeCa(dansCourante);
    const volume = dansCourante.reduce((somme, vente) => somme + vente.quantite, 0);
    const tickets = dansCourante.length;

    return {
      ca,
      tickets,
      bouteilles: volume,
      panierMoyen: this.panierMoyen(dansCourante),
      evolutionCa: this.pourcentageEvolution(ca, this.sommeCa(dansPrecedente)),
      evolutionVolume: this.pourcentageEvolution(
        volume,
        dansPrecedente.reduce((somme, vente) => somme + vente.quantite, 0),
      ),
    };
  }

  // --- Écriture (temps réel) ---

  /**
   * Ajoute une vente « en direct » à l'historique.
   * Appelée par le tableau de bord à chaque tick : les KPI, la heatmap et le top
   * des vins se recalculent ensemble, ce qui rend la démonstration convaincante
   * sans simuler un WebSocket.
   */
  ajouterVenteLive(maintenant: Date = new Date()): VenteLive {
    const vente = genererVenteLive(maintenant);
    this.historique.update((ventes) => [...ventes, vente]);
    return this.versVenteLive(vente);
  }

  /** Fiche vin d'une vente, pour l'affichage dans le flux. */
  private versVenteLive(vente: VenteUnitaire): VenteLive {
    const vin = MOCK_VINS.find((entree) => entree.id === vente.vinId);
    return {
      id: `live-${vente.date.getTime()}-${vente.vinId}-${vente.quantite}`,
      vinId: vente.vinId,
      nom: vin?.nom ?? vente.vinId,
      image: vin?.image ?? '',
      quantite: vente.quantite,
      total: vente.ca,
      date: vente.date,
    };
  }

  // --- Outils de calcul ---

  /** Bornes `[début, fin]` de la période : `decalage` = 0 période courante, 1 précédente. */
  private fenetre(periode: PeriodeRapport, decalage: number): Bornes {
    const maintenant = new Date();
    let debut: Date;
    let fin = new Date();

    switch (periode) {
      case 'jour': {
        debut = new Date(maintenant);
        debut.setDate(debut.getDate() - decalage);
        if (decalage > 0) {
          debut.setDate(debut.getDate() - 6);
        }
        debut.setHours(0, 0, 0, 0);
        fin = new Date(maintenant);
        fin.setDate(fin.getDate() - decalage * 7);
        fin.setHours(23, 59, 59, 999);
        break;
      }
      case 'semaine':
        debut = new Date(maintenant);
        debut.setDate(debut.getDate() - decalage * 7 - 6);
        debut.setHours(0, 0, 0, 0);
        fin = new Date(maintenant);
        fin.setDate(fin.getDate() - decalage * 7);
        fin.setHours(23, 59, 59, 999);
        break;
      case 'annee':
        debut = new Date(maintenant.getFullYear() - decalage, maintenant.getMonth() - 1, 1);
        fin = new Date(maintenant.getFullYear() - decalage, maintenant.getMonth(), 0, 23, 59, 59);
        break;
case 'mois':
      default:
        // Jour 0 du mois suivant = dernier jour du mois visé.
        debut = new Date(maintenant.getFullYear(), maintenant.getMonth() - decalage, 1);
        fin = new Date(maintenant.getFullYear(), maintenant.getMonth() - decalage + 1, 0, 23, 59, 59);
        break;
    }

    return { debut: debut.getTime(), fin: fin.getTime() };
  }

  /** Écart en pourcentage entre deux valeurs (0 si la référence est nulle). */
  private pourcentageEvolution(courante: number, precedente: number): number {
    if (precedente === 0) return courante > 0 ? 100 : 0;
    return Math.round(((courante - precedente) / precedente) * 1000) / 10;
  }

  private sommeCa(ventes: VenteUnitaire[]): number {
    return ventes.reduce((somme, vente) => somme + vente.ca, 0);
  }

  private panierMoyen(ventes: VenteUnitaire[]): number {
    if (ventes.length === 0) return 0;
    return Math.round(this.sommeCa(ventes) / ventes.length);
  }

  private dansBornes(date: Date, debut: Date | number, fin: Date | number): boolean {
    const instant = date.getTime();
    return instant >= this.time(debut) && instant <= this.time(fin);
  }

  private time(valeur: Date | number): number {
    return valeur instanceof Date ? valeur.getTime() : valeur;
  }

  private estAujourdhui(date: Date): boolean {
    const aujourdhui = new Date();
    return (
      date.getFullYear() === aujourdhui.getFullYear() &&
      date.getMonth() === aujourdhui.getMonth() &&
      date.getDate() === aujourdhui.getDate()
    );
  }

  private estMemeJour(date: Date, reference: Date): boolean {
    return (
      date.getFullYear() === reference.getFullYear() &&
      date.getMonth() === reference.getMonth() &&
      date.getDate() === reference.getDate()
    );
  }

  /** Numéro de semaine ISO, pour le libellé « S42 ». */
  private numeroSemaine(date: Date): number {
    const copie = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
    const jour = copie.getUTCDay() || 7;
    copie.setUTCDate(copie.getUTCDate() + 4 - jour);
    const debutAnnee = new Date(Date.UTC(copie.getUTCFullYear(), 0, 1));
    return Math.ceil(((copie.getTime() - debutAnnee.getTime()) / 86_400_000 + 1) / 7);
  }

  private nomVin(vinId: string): string {
    return MOCK_VINS.find((vin) => vin.id === vinId)?.nom ?? vinId;
  }
}

/** Promotions de la frise, toutes campagnes confondues (passées et à venir). */
export function promotionsDeLaFrise(actives: Promotion[], historiques: Promotion[]): Promotion[] {
  return [...actives, ...historiques].sort(
    (a, b) => new Date(a.dateDebut).getTime() - new Date(b.dateDebut).getTime(),
  );
}