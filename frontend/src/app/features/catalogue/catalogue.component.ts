import { ScrollingModule } from '@angular/cdk/scrolling';
import { ChangeDetectionStrategy, Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { TranslateModule } from '@ngx-translate/core';
import { catchError, debounceTime, map, Observable, of, startWith, switchMap, timer } from 'rxjs';

import { Vin, WineCategory } from '../../core/models/product.model';
import { FavorisService } from '../../core/services/favoris.service';
import { PanierService } from '../../core/services/panier.service';
import { ConfettiService } from '../../core/services/confetti.service';
import { ParrainageService } from '../../core/services/parrainage.service';
import { VinService } from '../../core/services/vin.service';
import { SkeletonComponent } from '../../shared/components/skeleton/skeleton.component';
import { DecimalPipe } from '@angular/common';

type TriCatalogue = 'nom' | 'prixAsc' | 'prixDesc' | 'note' | 'millesime';
interface ResultatCatalogue {
  vins: Vin[];
  erreur: boolean;
}

@Component({
  selector: 'app-catalogue',
  standalone: true,
  imports: [
    ScrollingModule,
    RouterLink,
    ReactiveFormsModule,
    DecimalPipe,
    TranslateModule,
    MatButtonModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatSelectModule,
    SkeletonComponent,
  ],
  templateUrl: './catalogue.component.html',
  styleUrl: './catalogue.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CatalogueComponent {
  private readonly vinsService = inject(VinService);
  private readonly destroyRef = inject(DestroyRef);
  readonly panier = inject(PanierService);
  /** Favoris persistés en local (bouton cœur des cartes). */
  readonly favoris = inject(FavorisService);
  private readonly parrainage = inject(ParrainageService);
  private readonly router = inject(Router);

  /** Confettis dorés à l'ajout au panier. */
  private readonly confetti = inject(ConfettiService);

  readonly chargement = signal(true);
  readonly erreur = signal(false);
  readonly vins = signal<Vin[]>([]);
  readonly ajoutConfirme = signal<string | null>(null);
  readonly detailsOuverts = signal<string | null>(null);

  readonly filtres = new FormGroup({
    recherche: new FormControl('', { nonNullable: true }),
    categorie: new FormControl<WineCategory | 'toutes'>('toutes', { nonNullable: true }),
    prixMax: new FormControl<number | null>(null),
    enStock: new FormControl(false, { nonNullable: true }),
    tri: new FormControl<TriCatalogue>('nom', { nonNullable: true }),
  });

  constructor() {
    this.appliquerCodeParrainage();
    this.appliquerCategorieUrl();
    this.filtres.valueChanges
      .pipe(
        startWith(this.filtres.getRawValue()),
        debounceTime(200),
        switchMap(() => this.charger()),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((resultat) => {
        this.vins.set(resultat.vins);
        this.erreur.set(resultat.erreur);
        this.chargement.set(false);
      });
  }

  suivreVin(_index: number, vin: Vin): string {
    return vin.id;
  }

  ajouterAuPanier(vin: Vin): void {
    if (vin.stock < 1) return;
    if (!this.panier.ajouter(vin)) return;
    this.ajoutConfirme.set(vin.id);
    this.confetti.ajoutPanier();
    timer(1800)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        if (this.ajoutConfirme() === vin.id) this.ajoutConfirme.set(null);
      });
  }

  /**
   * Effet « spotlight » : positionne la lueur dorée de la carte sous le
   * curseur via deux variables CSS (--mx / --my), sans re-rendu (OnPush).
   */
  suivreCurseur(event: MouseEvent): void {
    const carte = event.currentTarget as HTMLElement;
    const rect = carte.getBoundingClientRect();
    carte.style.setProperty('--mx', `${((event.clientX - rect.left) / rect.width) * 100}%`);
    carte.style.setProperty('--my', `${((event.clientY - rect.top) / rect.height) * 100}%`);
  }

  basculerDetails(vinId: string): void {
    this.detailsOuverts.update((ouvert) => (ouvert === vinId ? null : vinId));
  }

  reessayer(): void {
    this.filtres.updateValueAndValidity();
  }

  /**
   * Applique la remise de parrainage si la page a été ouverte via le lien
   * d'invitation (`/catalogue?code=XXXX`), puis nettoie l'URL.
   */
  private appliquerCodeParrainage(): void {
    const code = this.router.parseUrl(this.router.url).queryParams['code'];
    if (typeof code !== 'string' || !code.trim()) return;
    this.parrainage.utiliserCode(code);
    void this.router.navigate([], {
      queryParams: { code: null },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }

  /**
   * Pré-sélectionne la catégorie demandée par l'URL (`/catalogue?categorie=rouge`),
   * utilisée par les raccourcis de la page d'accueil. Une valeur inconnue est
   * ignorée (filtre « toutes catégories » par défaut).
   */
  private appliquerCategorieUrl(): void {
    const param = this.router.parseUrl(this.router.url).queryParams['categorie'];
    const connues: readonly string[] = ['rouge', 'blanc', 'rose', 'mousseux', 'petit-lait', 'liqueur'];
    if (typeof param === 'string' && connues.includes(param)) {
      this.filtres.controls.categorie.setValue(param as WineCategory);
    }
  }

  private charger(): Observable<ResultatCatalogue> {
    const valeurs = this.filtres.getRawValue();
    this.chargement.set(true);
    this.erreur.set(false);

    return this.vinsService
      .lister({
        recherche: valeurs.recherche,
        categorie: valeurs.categorie,
        prixMax: valeurs.prixMax && valeurs.prixMax > 0 ? valeurs.prixMax : undefined,
        enStock: valeurs.enStock,
        tri: valeurs.tri,
      })
      .pipe(
        map((vins) => ({ vins, erreur: false })),
        catchError((erreur: unknown) => {
          console.error('Impossible de charger le catalogue.', erreur);
          return of({ vins: [], erreur: true });
        }),
      );
  }
}
