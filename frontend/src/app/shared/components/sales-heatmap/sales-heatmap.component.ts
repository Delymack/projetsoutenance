import { DecimalPipe, NgStyle } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, input, signal } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule } from '@ngx-translate/core';

import { CaseVente } from '../../../core/models/analytics.model';
import { LangueService } from '../../../core/services/langue.service';

/** Une ligne du graphique (jour de la semaine), prête à afficher. */
interface LigneHeatmap {
  /** Index du jour : 0 = lundi … 6 = dimanche. */
  jour: number;
  /** Clé i18n du libellé court. */
  libelle: string;
  /** Les 24 cases du jour, indexées par heure. */
  cases: CaseVente[];
  /** Total de la journée. */
  total: number;
}

/** Étape de l'échelle de couleur (0 → 4), en pourcentage d'intensité. */
const PALIERS = [12, 30, 50, 70, 90];

/**
 * Heatmap des ventes — grille 7 jours × 24 heures.
 *
 * Pourquoi ne pas utiliser ngx-charts ? La bibliothèque ne propose pas de carte
 * de chaleur, et une grille manuelle donne exactement ce dont on a besoin : un
 * contrôle au pixel de la taille des cases, une échelle continue based on CSS
 * (`color-mix`), et un rendu identique en thème clair et sombre.
 *
 * L'intensité n'est jamais écrite en dur dans le template : on ne fournit que le
 * pourcentage, et la couleur est calculée en CSS à partir des variables du thème.
 */
@Component({
  selector: 'app-sales-heatmap',
  standalone: true,
  imports: [DecimalPipe, NgStyle, TranslateModule, MatIconModule, MatTooltipModule],
  templateUrl: './sales-heatmap.component.html',
  styleUrl: './sales-heatmap.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SalesHeatmapComponent {
  private readonly langue = inject(LangueService);

  /** Cases de la matrice 7 × 24. */
  readonly donnees = input.required<CaseVente[]>();

  /** Maximum de la matrice (mise à l'échelle des couleurs). */
  readonly pic = input<number>(0);

  /** Titre du graphique. */
  readonly titre = input<string>('HEATMAP.titre');

  /** Case sélectionnée au clic (détail affiché sous la grille). */
  readonly caseSelectionnee = signal<CaseVente | null>(null);

  /** Étapes de l'échelle de couleur, pour la légende. */
  readonly paliers = PALIERS;

  /** Colonnes : une en-tête toutes les 3 heures, pour ne pas surcharger l'axe. */
  readonly entetesHeures = Array.from({ length: 8 }, (_, index) => index * 3);

  /** Les 7 lignes de la grille, vides en cas de données absentes. */
  readonly lignes = computed<LigneHeatmap[]>(() => {
    const donnees = this.donnees();
    return Array.from({ length: 7 }, (_, jour) => {
      const cases = Array.from({ length: 24 }, (__, heure) => {
        const trouvee = donnees.find((case_) => case_.jour === jour && case_.heure === heure);
        return trouvee ?? { jour, heure, ventes: 0, ca: 0 };
      });
      return {
        jour,
        libelle: `HEATMAP.jours.j${jour}`,
        cases,
        total: cases.reduce((somme, case_) => somme + case_.ventes, 0),
      };
    });
  });

  /** Jour le plus productif. */
  readonly meilleurJour = computed(() =>
    [...this.lignes()].sort((a, b) => b.total - a.total)[0] ?? null,
  );

  /** Valeur plancher de l'échelle (jamais nulle : sinon la première case vaut 0 %). */
  readonly plancher = computed(() => Math.max(1, Math.floor(this.pic() * 0.05)));

  /** Effectue le changement d'échelle vers le maximum. */
  readonly plafond = computed(() => Math.max(this.pic(), this.plancher() + 1));

  /** Total des bouteilles représentées sur la période. */
  readonly total = computed(() =>
    this.donnees().reduce((somme, case_) => somme + case_.ventes, 0),
  );

  /** Intensité d'une case, en pourcentage (0 → 100), consommée par `color-mix`. */
  intensite(case_: CaseVente): number {
    const plancher = this.plancher();
    const ratio = (case_.ventes - plancher) / (this.plafond() - plancher);
    return Math.round(Math.min(Math.max(ratio, 0), 1) * 100);
  }

  /** Style inline d'une case : intensité + état sélectionné. */
  styleCase(case_: CaseVente): Record<string, string> {
    return { '--lb-intensite': `${this.intensite(case_)}%` };
  }

  /**
   * Infobulle d'une case : « Lundi 14 h · 3 bouteilles · 138 000 Ar ».
   * La traduction est faite ici et non dans le template parce que la chaîne est
   * composée (le pipe `translate` ne traduit qu'une clé, sans concaténation).
   */
  libelleCase(case_: CaseVente): string {
    return this.langue.t('HEATMAP.case', {
      jour: this.langue.t(`HEATMAP.jours.j${case_.jour}`),
      heure: `${String(case_.heure).padStart(2, '0')}h`,
      bouteilles: case_.ventes,
      ca: case_.ca.toLocaleString('fr-FR'),
    });
  }

  /** Libellé complet d'une ligne (pour `aria-label`). */
  libelleLigne(ligne: LigneHeatmap): string {
    return this.langue.t('HEATMAP.ligne', {
      jour: this.langue.t(ligne.libelle),
      bouteilles: ligne.total,
    });
  }

  /** Sélectionne une case (affiche son détail). */
  selectionner(case_: CaseVente): void {
    this.caseSelectionnee.set(case_);
  }
}