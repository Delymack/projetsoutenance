import { NgStyle } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/** Formes disponibles pour le squelette. */
export type SkeletonForme = 'texte' | 'titre' | 'cercle' | 'rectangle' | 'carte' | 'avatar';

/**
 * Composant squelette de chargement.
 *
 * Utilisation :
 *   <app-skeleton forme="carte" />
 *   <app-skeleton [lignes]="3" />
 *   @if (chargement()) { <app-skeleton forme="carte" /> } @else { ... }
 *
 * L'animation « shimmer » est purement CSS (voir .scss) : aucune dépendance JS,
 * donc aucun coût CPU côté thread principal pendant le scroll.
 */
@Component({
  selector: 'app-skeleton',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [NgStyle],
  templateUrl: './skeleton.component.html',
  styleUrl: './skeleton.component.scss',
})
export class SkeletonComponent {
  /** Forme du squelette. */
  readonly forme = input<SkeletonForme>('texte');

  /** Nombre de lignes pour la forme « texte ». */
  readonly lignes = input<number>(3);

  /** Largeur(forcée) du bloc, ex. « 60% ». */
  readonly largeur = input<string | null>(null);

  /** Hauteur forcée, ex. « 120px ». */
  readonly hauteur = input<string | null>(null);

  /** Arrondi supplémentaire (px). */
  readonly rayon = input<number | null>(null);

  /** Styles calculés appliqués sur le bloc. */
  readonly styles = computed<Record<string, string>>(() => {
    const style: Record<string, string> = {};
    if (this.largeur()) style['width'] = this.largeur()!;
    if (this.hauteur()) style['height'] = this.hauteur()!;
    if (this.rayon() !== null) style['border-radius'] = `${this.rayon()}px`;
    return style;
  });

  /** Tableau de lignes à itérer (1 → n). */
  readonly indexes = computed(() => Array.from({ length: Math.max(1, this.lignes()) }, (_, i) => i));
}