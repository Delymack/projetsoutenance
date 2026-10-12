import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { TranslateModule } from '@ngx-translate/core';
import { catchError, of } from 'rxjs';

import { Vin } from '../../core/models/product.model';
import { FavorisService } from '../../core/services/favoris.service';
import { PanierService } from '../../core/services/panier.service';
import { VinService } from '../../core/services/vin.service';
import { SkeletonComponent } from '../../shared/components/skeleton/skeleton.component';

@Component({
  selector: 'app-favoris',
  standalone: true,
  imports: [DecimalPipe, RouterLink, TranslateModule, MatButtonModule, MatIconModule, SkeletonComponent],
  templateUrl: './favoris.component.html',
  styleUrl: './favoris.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FavorisComponent {
  private readonly vinsService = inject(VinService);
  private readonly destroyRef = inject(DestroyRef);
  readonly favoris = inject(FavorisService);
  readonly panier = inject(PanierService);

  readonly chargement = signal(true);
  readonly erreur = signal(false);
  readonly detailsOuverts = signal<string | null>(null);
  readonly catalogue = signal<Vin[]>([]);
  readonly vins = computed(() => {
    const ids = new Set(this.favoris.ids());
    return this.catalogue().filter((vin) => ids.has(vin.id));
  });

  constructor() {
    this.vinsService
      .listerTous()
      .pipe(
        catchError((erreur: unknown) => {
          console.error('Impossible de charger les favoris.', erreur);
          this.erreur.set(true);
          return of([]);
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((vins) => {
        this.catalogue.set(vins);
        this.chargement.set(false);
      });
  }

  ajouter(vin: Vin): void {
    this.panier.ajouter(vin);
  }

  basculerDetails(vinId: string): void {
    this.detailsOuverts.update((ouvert) => (ouvert === vinId ? null : vinId));
  }

  retirer(vin: Vin): void {
    this.favoris.retirer(vin.id);
  }
}
