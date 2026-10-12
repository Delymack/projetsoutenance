import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/** Un axe du profil gustatif : identifiant technique + intensité de 0 à 1. */
export interface AxeProfil {
  /** Identifiant de l'axe (`fruite`, `tanin`…). Sert de clé de traduction. */
  cle: string;
  /** Valeur normalisée entre 0 et 1. */
  valeur: number;
}

/** Anneaux du fond de grille (fractions du rayon maximum). */
const ANNEAUX = [0.25, 0.5, 0.75, 1];

/**
 * Radar du profil gustatif.
 *
 * Le tracé est fait en SVG natif plutôt qu'avec ngx-charts : la bibliothèque
 * ne propose pas de graphique radar (seulement `polar`, dont le rendu empilé
 * n'a pas grand sens pour un profil à une seule série), et un SVG écrit ici
 * reste pilotable par les variables CSS du thème — y compris les libellés,
 * que ngx-charts colorie en dur.
 */
@Component({
  selector: 'app-radar-profil',
  standalone: true,
  imports: [DecimalPipe],
  templateUrl: './radar-profil.component.html',
  styleUrl: './radar-profil.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RadarProfilComponent {
  /** Axes du profil, dans l'ordre d'affichage autour du cercle. */
  readonly axes = input.required<AxeProfil[]>();

  /** Libellés traduits, indexés par clé d'axe. */
  readonly libelles = input<Record<string, string>>({});

  /** Description du graphique pour les lecteurs d'écran. */
  readonly etiquette = input<string>('Profil gustatif');

  /** Côté du carré SVG (px). */
  readonly taille = input<number>(300);

  /** Centre du radar. */
  readonly centre = computed(() => this.taille() / 2);

  /** Rayon utile, laissant la place aux libellés. */
  readonly rayon = computed(() => this.centre() * 0.62);

  /** Anneaux de fond. */
  readonly anneaux = ANNEAUX;

  /** Points d'un axe : angle (en degrés, -90° = 12 h), rayon et position. */
  readonly positions = computed(() => {
    const axes = this.axes();
    const rayon = this.rayon();
    const centre = this.centre();
    const pas = 360 / Math.max(axes.length, 1);

    return axes.map((axe, index) => {
      const angle = ((-90 + index * pas) * Math.PI) / 180;
      const cos = Math.cos(angle);
      const sin = Math.sin(angle);
      return {
        cle: axe.cle,
        valeur: axe.valeur,
        x: centre + cos * rayon,
        y: centre + sin * rayon,
        // Extrémité de la ligne d'axe et de son libellé.
        xLabel: centre + cos * rayon * 1.22,
        yLabel: centre + sin * rayon * 1.22,
        ancrage: Math.abs(cos) < 0.2 ? 'middle' : cos > 0 ? 'start' : 'end',
      };
    });
  });

  /** Polygone d'un anneau de fond. */
  pointsAnneau = (facteur: number): string => {
    const rayon = this.rayon() * facteur;
    const centre = this.centre();
    const pas = 360 / Math.max(this.axes().length, 1);

    return this.axes()
      .map((_, index) => {
        const angle = ((-90 + index * pas) * Math.PI) / 180;
        return `${centre + Math.cos(angle) * rayon},${centre + Math.sin(angle) * rayon}`;
      })
      .join(' ');
  };

  /** Polygone du profil de l'utilisateur. */
  readonly pointsProfil = computed(() =>
    this.positions()
      .map((position) => `${position.x},${position.y}`)
      .join(' '),
  );

  /** Libellé d'un axe, avec repli sur la clé technique. */
  libelle(cle: string): string {
    return this.libelles()[cle] || cle;
  }
}