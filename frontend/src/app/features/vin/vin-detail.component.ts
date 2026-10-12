import { DatePipe, DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTabsModule } from '@angular/material/tabs';
import { TranslateModule } from '@ngx-translate/core';
import { catchError, forkJoin, of, switchMap } from 'rxjs';

import { Promotion, Vin } from '../../core/models/product.model';
import { FavorisService } from '../../core/services/favoris.service';
import { PanierService } from '../../core/services/panier.service';
import { VinService } from '../../core/services/vin.service';
import { SkeletonComponent } from '../../shared/components/skeleton/skeleton.component';
import { ReviewComponent } from '../../shared/components/review/review.component';
import { ShareComponent } from '../../shared/components/share/share.component';

@Component({
  selector: 'app-vin-detail',
  standalone: true,
  imports: [
    DatePipe,
    DecimalPipe,
    RouterLink,
    TranslateModule,
    MatButtonModule,
    MatIconModule,
    MatTabsModule,
    SkeletonComponent,
    ReviewComponent,
    ShareComponent,
  ],
  templateUrl: './vin-detail.component.html',
  styleUrl: './vin-detail.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VinDetailComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly vinsService = inject(VinService);
  private readonly destroyRef = inject(DestroyRef);
  readonly panier = inject(PanierService);
  readonly favoris = inject(FavorisService);

  readonly chargement = signal(true);
  readonly erreur = signal(false);
  readonly vin = signal<Vin | undefined>(undefined);
  readonly avis = signal<{ id: string }[]>([]);
  readonly promotions = signal<Promotion[]>([]);
  readonly rotationActive = signal(false);

  /** URL de la fiche, transmise au composant de partage. */
  readonly urlCourante = signal<string>(typeof window !== 'undefined' ? window.location.href : '');

  /** Nombre d'avis ajoutés localement par les visiteurs (hors note catalogue). */
  readonly nbAvisSupplementaires = computed(() => this.avis().length);

  basculerRotation(): void {
    this.rotationActive.set(!this.rotationActive());
  }

  readonly promotionsVin = computed(() => {
    const vin = this.vin();
    if (!vin) return [];
    return this.promotions().filter((promo) => promo.vinsIds.includes(vin.id));
  });

  constructor() {
    this.route.paramMap
      .pipe(
        switchMap((params) => {
          const id = params.get('id') ?? '';
          this.chargement.set(true);
          this.erreur.set(false);
          return forkJoin({
            vin: this.vinsService.obtenirParId(id),
            avis: this.vinsService.listerAvis(id),
            promotions: this.vinsService.listerPromotions(),
          }).pipe(
            catchError((erreur: unknown) => {
              console.error('Impossible de charger la fiche vin.', erreur);
              this.erreur.set(true);
              return of({ vin: undefined, avis: [] as { id: string }[], promotions: [] as Promotion[] });
            }),
          );
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(({ vin, avis, promotions }) => {
        this.vin.set(vin);
        this.avis.set(avis);
        this.promotions.set(promotions);
        this.chargement.set(false);
      });
  }

  ajouterAuPanier(vin: Vin): void {
    this.panier.ajouter(vin);
  }

  basculerFavori(vin: Vin): void {
    this.favoris.basculer(vin.id);
  }

  remisePct(vin: Vin): number | null {
    if (!vin.prixBarre || vin.prixBarre <= vin.prix) return null;
    return Math.round(100 - (vin.prix / vin.prixBarre) * 100);
  }
}
