import { ChangeDetectionStrategy, Component, computed, effect, inject, untracked } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterOutlet } from '@angular/router';
import { filter, map, startWith } from 'rxjs';

import { MatIconModule } from '@angular/material/icon';
import { TranslateModule } from '@ngx-translate/core';

import { NavbarComponent } from './layout/navbar/navbar.component';
import { FooterComponent } from './layout/footer/footer.component';
import { BandeauHorsLigneComponent } from './shared/components/bandeau-hors-ligne/bandeau-hors-ligne.component';
import { ChatbotComponent } from './shared/components/chatbot/chatbot.component';
import { ConnectivityService } from './core/services/connectivity.service';
import { SyncService } from './core/services/sync.service';
import { AuthService } from './core/services/auth.service';
import { PanierService } from './core/services/panier.service';

/**
 * Coquille applicative (App Shell).
 *
 * Contient la structure permanente : navbar, zone de routage, footer, bandeau
 * hors ligne. Injecter `ConnectivityService` et `SyncService` ici a un effet
 * de bord volontaire : les deux services sont instanciés dès le démarrage, donc
 * la file d'attente des ventes hors ligne est prête et se synchronise
 * automatiquement dès le retour du réseau.
 */
@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    RouterOutlet,
    RouterLink,
    MatIconModule,
    NavbarComponent,
    FooterComponent,
    BandeauHorsLigneComponent,
    ChatbotComponent,
    TranslateModule,
  ],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AppComponent {
  private readonly connectivite = inject(ConnectivityService);
  private readonly sync = inject(SyncService);
  private readonly router = inject(Router);
  private readonly auth = inject(AuthService);
  private readonly panier = inject(PanierService);

  /**
   * Some routes are displayed without navigation chrome, typically the customer
   * display opened on a second screen during a sale. The flag comes from the
   * route `data`, which is more robust than matching the URL.
   */
  private readonly sansChrome = toSignal(
    this.router.events.pipe(
      filter((evenement): evenement is NavigationEnd => evenement instanceof NavigationEnd),
      map(() => this.estRouteSansChrome()),
      startWith(this.estRouteSansChrome()),
    ),
    { initialValue: false },
  );

  readonly horsLigne = this.connectivite.horsLigne;
  readonly enAttente = this.sync.enAttente;

  /** The customer display and any route flagged `sansChrome` hide the navbar and footer. */
  readonly chromeVisible = computed(() => !this.sansChrome());

  constructor() {
 // ajout au panier refusé sans compte : on part vers l'inscription
    // en gardant la page d'origine, le vin étant rejoué juste après.
    effect(() => {
      const vin = this.panier.ajoutBloque();
      if (!vin) return;
      untracked(() => {
        this.panier.ajoutBloque.set(null);
        void this.router.navigate(['/inscription'], {
          queryParams: { retour: this.router.url },
        });
      });
    });

 // le vin mis en attente rejoint le panier dès la connexion.
    effect(() => {
      if (!this.auth.connecte()) return;
      untracked(() => this.panier.rejouerAjoutEnAttente());
    });
  }

  private estRouteSansChrome(): boolean {
    let route = this.router.routerState.snapshot.root;
    while (route.firstChild) route = route.firstChild;
    return route.data['sansChrome'] === true;
  }
}