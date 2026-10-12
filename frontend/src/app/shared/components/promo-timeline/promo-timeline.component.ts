import { DatePipe, DecimalPipe, NgStyle } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, input, output, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule } from '@ngx-translate/core';

import { Promotion } from '../../../core/models/product.model';

/** État d'une campagne par rapport à l'instant présent. */
export type EtatPromo = 'passee' | 'encours' | 'avenir';

/** Promotion positionnée sur la frise : coordonnées, état et géométrie. */
export interface BlocPromo {
  promo: Promotion;
  /** Position du début, en pourcentage de la largeur de la frise (0 → 100). */
  debut: number;
  /** Largeur du bloc, en pourcentage. */
  largeur: number;
  /** Voie (« rail ») attribuée pour éviter les chevauchements. */
  voie: number;
  /** État calculé par rapport à maintenant. */
  etat: EtatPromo;
  /** Nombre de jours restants (négatif si la campagne est terminée). */
  joursRestants: number;
}

/** Repère temporel affiché sous le rail. */
interface Repere {
  /** Libellé du repère (« janv. 26 »). */
  libelle: string;
  /** Position en pourcentage. */
  position: number;
}

/** Marge en pourcentage ajoutée de part et d'autre du domaine de dates. */
const MARGE_PCT = 6;

/** Largeur minimale d'un bloc, en pourcentage (lisibilité sur mobile). */
const LARGEUR_MIN = 9;

/**
 * Frise chronologique des promotions.
 *
 * Fonctionnement : la frise couvre l'intervalle `[début, fin]` englobant toutes
 * les promotions, chaque campagne étant placée proportionnellement à ses dates.
 * Deux campaigns qui se chevauchent partagent deux « voies » (rangées) au lieu de
 * se superposer — sinon les blocs se masqueraient et la lecture serait faussée.
 *
 * Le composant est purement présentiel : il reçoit les promotions (triées ou
 * non) et n'émet que `selectionChange`. Il ne dépend ni du service catalogue ni du
 * panier, ce qui le rend réutilisable dans la page promotions comme dans un
 * rapport de gestion.
 */
@Component({
  selector: 'app-promo-timeline',
  standalone: true,
  imports: [
    DatePipe,
    DecimalPipe,
    NgStyle,
    TranslateModule,
    MatButtonModule,
    MatIconModule,
    MatTooltipModule,
  ],
  templateUrl: './promo-timeline.component.html',
  styleUrl: './promo-timeline.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PromoTimelineComponent {
  /** Promotions à représenter sur la frise. */
  readonly promotions = input.required<Promotion[]>();

  /** Libellé de l'axe temporel (accessibilité du rail). */
  readonly etiquette = input<string>('Frise des promotions');

  /** Campagne sélectionnée : émise vers le parent à chaque clic. */
  readonly selectionChange = output<Promotion>();

  /** Détail de la campagne sélectionnée, affiché sous la frise. */
  readonly selectionnee = signal<Promotion | null>(null);

  /** Bloc actuellement survolé (pour la surbrillance croisée du rail). */
  readonly survolee = signal<string | null>(null);

  /** Repères de l'axe : un par mois couvert par le domaine de dates. */
  readonly reperes = computed<Repere[]>(() => {
    const domaine = this.domaine();
    if (!domaine) return [];

    const reperes: Repere[] = [];
    const curseur = new Date(domaine.debut);
    curseur.setDate(1);

    while (curseur.getTime() < domaine.fin) {
      const position = this.pourcentage(curseur.getTime());
      // On saute les repères trop serrés : deux libellés se chevaucheraient.
      if (position > 4 && position < 97) {
        reperes.push({
          libelle: curseur.toLocaleDateString('fr-FR', { month: 'short', year: '2-digit' }),
          position,
        });
      }
      curseur.setMonth(curseur.getMonth() + 1);
    }
    return reperes;
  });

  /**
   * Blocs positionnés et répartis sur deux voies.
   * L'affectation de voie est gloutonne : on place chaque campagne dans la voie
   * dont la dernière fin est la plus proche (soit la même voie si possible).
   */
  readonly blocs = computed<BlocPromo[]>(() => {
    const domaine = this.domaine();
    const promotions = this.promotions();
    if (!domaine || promotions.length === 0) return [];

    const brut = promotions
      .map((promo) => this.construireBloc(promo, domaine))
      .sort((a, b) => a.debut - b.debut);

    // Fin de la dernière campagne placée, par voie.
    const finsParVoie: number[] = [];
    return brut.map((bloc) => {
      let voie = finsParVoie.findIndex((fin) => fin <= bloc.debut);
      if (voie === -1) {
        voie = finsParVoie.length;
        finsParVoie.push(0);
      }
      finsParVoie[voie] = bloc.debut + bloc.largeur;
      return { ...bloc, voie };
    });
  });

  /** Nombre de voies utilisées : commande la hauteur du composant. */
  readonly nbVoies = computed(() => {
    const blocs = this.blocs();
    return blocs.length === 0 ? 1 : Math.max(...blocs.map((bloc) => bloc.voie)) + 1;
  });

  /**.Instance « maintenant », figée à la création du composant. */
  private readonly maintenant = new Date();

  /** Domaine temporel couvert, avec marge. */
  private readonly domaine = computed<{ debut: number; fin: number } | null>(() => {
    const promotions = this.promotions();
    if (promotions.length === 0) return null;

    const dates = promotions.flatMap((promo) => [
      new Date(promo.dateDebut).getTime(),
      new Date(promo.dateFin).getTime(),
    ]);
    const min = Math.min(...dates);
    const max = Math.max(...dates);
    const portee = Math.max(max - min, 86_400_000); // au minimum un jour
    return { debut: min - (portee * MARGE_PCT) / 100, fin: max + (portee * MARGE_PCT) / 100 };
  });

  /** Sélectionne une campagne (et prévient le parent). */
  selectionner(promo: Promotion): void {
    this.selectionnee.set(promo);
    this.selectionChange.emit(promo);
  }

  /** Referme le détail de la campagne sélectionnée. */
  fermerDetail(): void {
    this.selectionnee.set(null);
  }

  /** Libellé de l'état, traduit au moment du rendu. */
  libelleEtat(etat: EtatPromo): string {
    return `PROMO.timeline.etat.${etat}`;
  }

  /** Style inline de position d'un bloc (voies + gauche + largeur). */
  styleBloc(bloc: BlocPromo): Record<string, string> {
    return {
      left: `${bloc.debut}%`,
      width: `${bloc.largeur}%`,
      '--lb-voie': String(bloc.voie),
    };
  }

  // --- Interne ---

  private construireBloc(promo: Promotion, domaine: { debut: number; fin: number }): BlocPromo {
    const debut = new Date(promo.dateDebut).getTime();
    const fin = new Date(promo.dateFin).getTime();
    const portee = domaine.fin - domaine.debut;

    const debutPct = ((debut - domaine.debut) / portee) * 100;
    const largeurPct = Math.max(((fin - debut) / portee) * 100, LARGEUR_MIN);

    const maintenant = this.maintenant.getTime();
    const etat: EtatPromo = fin < maintenant ? 'passee' : debut > maintenant ? 'avenir' : 'encours';
    const joursRestants = Math.ceil((fin - maintenant) / 86_400_000);

    return {
      promo,
      debut: Math.min(Math.max(debutPct, 0), 100 - LARGEUR_MIN),
      largeur: largeurPct,
      voie: 0,
      etat,
      joursRestants,
    };
  }

  /** Convertit un instant en position horizontale (en pourcentage du domaine). */
  private pourcentage(instant: number): number {
    const domaine = this.domaine();
    if (!domaine) return 0;
    return ((instant - domaine.debut) / (domaine.fin - domaine.debut)) * 100;
  }
}