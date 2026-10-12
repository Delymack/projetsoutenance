import { DatePipe, DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { TranslateModule } from '@ngx-translate/core';
import { forkJoin, timer } from 'rxjs';


import { Promotion, Vin } from '../../core/models/product.model';
import { PanierService } from '../../core/services/panier.service';
import { VinService } from '../../core/services/vin.service';
import { SkeletonComponent } from '../../shared/components/skeleton/skeleton.component';

/** Promotion complétée des vins qu'elle concerne. */
interface PromotionDetaillee extends Promotion {
  vins: Vin[];
}



const DELAI_MESSAGE_MS = 1800;

/**
 * Liste des promotions actives.
 *
 * Chaque carte présente la remise, sa date de fin et les vins concernés.
 */
@Component({
  selector: 'app-promo-list',
  standalone: true,
  imports: [
    DatePipe,
    DecimalPipe,
    RouterLink,
    TranslateModule,
    MatButtonModule,
    MatIconModule,
    SkeletonComponent,
  ],
  templateUrl: './promo-list.component.html',
  styleUrl: './promo-list.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PromoListComponent {
  private readonly vinsService = inject(VinService);
  private readonly panier = inject(PanierService);
  private readonly destroyRef = inject(DestroyRef);

  readonly chargement = signal(true);
  readonly erreur = signal(false);
  readonly promotions = signal<PromotionDetaillee[]>([]);
  readonly vinAjoute = signal<string | null>(null);

  constructor() {
    this.charger();
  }

  ajouterAuPanier(vin: Vin, promo: Promotion): void {
    if (vin.stock < 1) return;
    const prix = this.prixPromo(vin, promo);
    const vinAvecPrixPromo = { ...vin, prix, prixBarre: vin.prixBarre ?? vin.prix };
    if (!this.panier.ajouter(vinAvecPrixPromo, 1, prix)) return;
    this.vinAjoute.set(vin.id);
    timer(DELAI_MESSAGE_MS)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        if (this.vinAjoute() === vin.id) this.vinAjoute.set(null);
      });
  }

  /** Prix du vin après la remise de la promotion. */
  prixPromo(vin: Vin, promo: Promotion): number {
    const pct = promo.remisePct;
    if (pct === null) return vin.prix;
    return Math.round((vin.prixBarre ?? vin.prix) * (1 - pct / 100));
  }

  /** Date de fin formatée, pour l'accroche. */
  fin(promo: Promotion): Date {
    return new Date(promo.dateFin);
  }

  reessayer(): void {
    this.charger();
  }

  private charger(): void {
    this.chargement.set(true);
    this.erreur.set(false);

    forkJoin({
      promotions: this.vinsService.listerPromotions(),
      vins: this.vinsService.listerTous(),
    })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: ({ promotions, vins }) => {
          this.promotions.set(
            promotions.map((promo) => ({
              ...promo,
              vins: vins.filter((vin) => promo.vinsIds.includes(vin.id)),
            })),
          );
          this.chargement.set(false);
        },
        error: (erreur: unknown) => {
          console.error('Impossible de charger les promotions.', erreur);
          this.erreur.set(true);
          this.chargement.set(false);
        },
      });
  }
}