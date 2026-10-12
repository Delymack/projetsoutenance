import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { TranslateModule } from '@ngx-translate/core';

import { ConnectivityService } from '../../../core/services/connectivity.service';
import { LangueService } from '../../../core/services/langue.service';
import { PwaService } from '../../../core/services/pwa.service';
import { SyncService } from '../../../core/services/sync.service';

/**
 * Bandeau d'état hors ligne.
 *
 * Trois informations, une seule barre flottante (`position: fixed`) pour ne pas
 * déplacer la mise en page, y compris pendant une saisie en caisse :
 *  - « vous êtes hors ligne », avec le nombre de ventes en file d'attente ;
 *  - « connexion rétablie » + résultat de la synchronisation différée, affiché
 *    quelques secondes après le retour du réseau ;
 *  - « nouvelle version disponible » quand le service worker a Téléchargé une
 *    version plus récente, avec un rechargement manuel ;
 *  - l'invitation à installer l'application (PWA) quand le navigateur le propose.
 */
@Component({
  selector: 'app-bandeau-hors-ligne',
  standalone: true,
  imports: [MatIconModule, MatButtonModule, TranslateModule],
  templateUrl: './bandeau-hors-ligne.component.html',
  styleUrl: './bandeau-hors-ligne.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    '[class.bandeau-visible]': 'visible()',
    '[class.bandeau-flottant]': 'horsLigne() || nouvelleVersion()',
  },
})
export class BandeauHorsLigneComponent {
  private readonly connectivite = inject(ConnectivityService);
  private readonly sync = inject(SyncService);
  private readonly pwa = inject(PwaService);
  private readonly langue = inject(LangueService);

  readonly horsLigne = this.connectivite.horsLigne;

  /** Ventes en file d'attente hors ligne. */
  readonly enAttente = computed(() => this.sync.enAttente());

  /** Nouvelle version en cache (service worker). */
  readonly nouvelleVersion = this.pwa.nouvelleVersion;

  /** Le navigateur propose d'installer l'application. */
  readonly installationDisponible = this.pwa.installationDisponible;

  /**
   * Message contextuel à droite (`null` : rien à afficher sous le titre).
   * La réapparition du réseau est signalée quelques secondes : le temps que
   * l'utilisateur lise « connexion rétablie » et le résultat de la
   * synchronisation, avant de disparaître.
   */
  readonly message = computed<string | null>(() => {
    if (this.horsLigne()) {
      return this.enAttente() > 0 ? this.traduire('HORS_LIGNE.enAttente', { count: this.enAttente() }) : null;
    }

    const dernier = this.sync.dernierSync();
    if (dernier?.succes && dernier.nombre > 0) return this.traduire('HORS_LIGNE.syncReussie', { count: dernier.nombre });

    return this.traduire('HORS_LIGNE.enLigneDetail', { count: this.enAttente() });
  });

  /** Instant où la connexion a été perdue (0 si jamais coupée). */
  private readonly coupureDepuis = signal(0);

  /** La bannière reste visible 4 s après le retour du réseau. */
  private readonly retourRecent = signal(false);

  /** La bannière doit-elle être visible ? */
  readonly visible = computed(
    () =>
      this.horsLigne() ||
      this.retourRecent() ||
      this.nouvelleVersion() ||
      (this.installationDisponible() && !this.horsLigne()),
  );

  /** Classe de couleur : une seule variante à la fois. */
  readonly variante = computed(() => {
    if (this.nouvelleVersion() || this.installationDisponible()) return 'alerte';
    if (this.horsLigne()) return 'hors-ligne';
    return 'succes';
  });

  /** Force une tentative de synchronisation manuelle. */
  synchroniser(): void {
    void this.sync.synchroniser();
  }

  /** Recharge pour prendre la version en attente. */
  actualiser(): void {
    this.pwa.actualiser();
  }

  /** Lance l'installation de l'application. */
  installer(): void {
    void this.pwa.installer();
  }

  /** L'utilisateur refuse l'invitation à installer. */
  reporter(): void {
    this.pwa.reporterInstallation();
  }

  constructor() {
    this.connectivite.onChange((enLigne) => {
      if (!enLigne) {
        this.coupureDepuis.set(Date.now());
        this.retourRecent.set(false);
        return;
      }

      // On ne masque pas immédiatement : l'utilisateur doit voir « connexion
      // rétablie » et le nombre de ventes resynchronisées.
      if (!this.coupureDepuis()) return;
      this.retourRecent.set(true);
      window.setTimeout(() => this.retourRecent.set(false), 4000);
    });
  }

  /** Traduit une clé du bandeau dans la langue active. */
  private traduire(cle: string, params?: Record<string, unknown>): string {
    return this.langue.t(cle, params);
  }
}
