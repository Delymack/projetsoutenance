import { DatePipe, DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatIconModule } from '@angular/material/icon';
import { TranslateModule } from '@ngx-translate/core';
import { interval, startWith } from 'rxjs';

import { VenteLive } from '../../core/models/analytics.model';
import { LangueService } from '../../core/services/langue.service';
import { NotificationService } from '../../core/services/notification.service';
import { VentesService } from '../../core/services/ventes.service';
import { SalesHeatmapComponent } from '../../shared/components/sales-heatmap/sales-heatmap.component';

/**
 * Tableau de bord direction — vue temps réel.
 *
 * Les chiffres ne sont plus tirés au hasard dans le composant : ils viennent de
 * `VentesService`, qui simule un historique cohérent (matrice horaire, promotions,
 * week-ends). Seul le flux live est recalculé à intervalle fixe, comme le ferait
 * un `WebSocket` dans une version connectée.
 */
@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [DatePipe, DecimalPipe, MatIconModule, TranslateModule, SalesHeatmapComponent],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DashboardComponent {
  private readonly analytics = inject(VentesService);
  private readonly notifications = inject(NotificationService);
  private readonly langue = inject(LangueService);
  private readonly destroyRef = inject(DestroyRef);

  readonly maintenant = signal(new Date());

  /** Flux temps réel des 20 derniers tickets. */
  readonly ventes = computed(() => this.analytics.fluxLive());
  readonly derniereNotification = signal<VenteLive | null>(null);

  /* ---------------- Indicateurs du jour ---------------- */
  readonly caJour = this.analytics.caJour;
  readonly ventesJour = this.analytics.ticketsJour;
  readonly vinsVendus = this.analytics.bouteillesJour;
  readonly panierMoyen = this.analytics.panierMoyenJour;

 /** Matrice horaire 7 jours × 24 heures pour la heatmap. */
  readonly matrice = this.analytics.matrice;
  readonly picVentes = this.analytics.picVentes;
  readonly meilleurMoment = this.analytics.meilleurMoment;

  /** Top 5 des vins vendus sur la période, avec leur part relative (barres). */
  readonly topVins = computed(() => {
    const series = this.analytics.topVins(5);
    const max = Math.max(1, ...series.map((serie) => serie.value));
    return series.map((serie) => ({
      nom: serie.name,
      valeur: serie.value,
      part: Math.round((serie.value / max) * 100),
    }));
  });

  /**
   * Résumé du pic de ventes, traduit. Le calcul dépend du signal de langue :
   * le libellé est donc recalculé à chaque changement de langue.
   */
  readonly resumePic = computed(() => {
    const moment = this.meilleurMoment();
    return this.langue.t('HEATMAP.meilleurMoment', {
      jour: this.langue.t(`HEATMAP.jours.j${moment.jour}`),
      heure: `${String(moment.heure).padStart(2, '0')}h`,
    });
  });

  constructor() {
    interval(30_000)
      .pipe(startWith(0), takeUntilDestroyed(this.destroyRef))
      .subscribe((tick) => {
        this.maintenant.set(new Date());
        if (tick === 0) return;

        // Nouvelle vente : on l'ajoute au flux et on previent le client, comme le
        // ferait le push serveur si la boutique était en ligne.
        const nouvelle = this.analytics.ajouterVenteLive();
        this.derniereNotification.set(nouvelle);
        this.notifications.notifier(
          'commande',
          this.langue.t('DASHBOARD.nouvelleVente'),
          `${nouvelle.nom} · ${nouvelle.quantite} × ${Math.round(nouvelle.total).toLocaleString('fr-FR')} Ar`,
        );

        window.setTimeout(() => {
          if (this.derniereNotification()?.id === nouvelle.id) this.derniereNotification.set(null);
        }, 4200);
      });
  }
}
