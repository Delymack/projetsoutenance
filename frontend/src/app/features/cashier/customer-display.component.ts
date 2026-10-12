import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, effect, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router } from '@angular/router';
import { TranslateModule } from '@ngx-translate/core';
import { filter, map, startWith } from 'rxjs';

import { PanierService } from '../../core/services/panier.service';

/**
 * Écran client temps réel.
 *
 * Utilisé soit en panneau dans la caisse, soit en page entière sur la route
 * `/ecran-client` (ouverte via `window.open` depuis la caisse).
 *
 * Les deux contextes ne partageant pas le même BehaviorSubject, la
 * synchronisation entre la caisse et la fenêtre cliente passe par le
 * BroadcastChannel de `PanierService` : toute modification faite en caisse est
 * donc reflétée ici, sans état dupliqué à maintenir.
 *
 * L'entrée `pleinEcran` passe l'écran en mode « face au client » : grande
 * typographie, message de remerciement après encaissement, sans distraction.
 */
@Component({
  selector: 'app-customer-display',
  standalone: true,
  imports: [DecimalPipe, TranslateModule],
  templateUrl: './customer-display.component.html',
  styleUrl: './customer-display.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CustomerDisplayComponent {
  private readonly panier = inject(PanierService);
  private readonly router = inject(Router);

  /** URL courante : permet de déduire le mode d'affichage sans input à câbler. */
  private readonly url = toSignal(
    this.router.events.pipe(
      filter((evenement): evenement is NavigationEnd => evenement instanceof NavigationEnd),
      map(() => this.router.url),
      startWith(this.router.url),
    ),
    { initialValue: this.router.url },
  );

  /**
   * Mode page entière : vrai sur la route /ecran-client, faux quand le composant
   * est intégré en panneau dans la caisse.
   */
  readonly pleinEcran = computed(() => this.url().startsWith('/ecran-client'));

  readonly lignes = this.panier.lignes;
  readonly sousTotal = this.panier.sousTotal;
  readonly total = this.panier.total;
  readonly estVide = this.panier.estVide;
  readonly nbArticles = this.panier.nbArticles;

  /** Message de remerciement affiché après un encaissement. */
  readonly remerciement = signal(false);

  constructor() {
    // Tant que le panier contient des articles, pas de message de remerciement.
    // Dès qu'il se vide après avoir été rempli, on congratule le client.
    let panierPlein = !this.panier.estVide();

    effect(
      () => {
        const vide = this.panier.estVide();

        if (this.pleinEcran() && panierPlein && vide) {
          this.remerciement.set(true);
          window.setTimeout(() => this.remerciement.set(false), 5000);
        }

        if (!vide) panierPlein = true;
      },
      // `remerciement` est un signal : l'écriture depuis un effet l'exige.
      { allowSignalWrites: true },
    );
  }

  /** Total d'une ligne (quantité × prix × remise). */
  totalLigne(vinId: string): number {
    const ligne = this.lignes().find((l) => l.vin.id === vinId);
    return ligne ? this.panier.totalLigne(ligne) : 0;
  }
}
