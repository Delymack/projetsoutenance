import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatSelectModule } from '@angular/material/select';
import { MatFormFieldModule } from '@angular/material/form-field';
import { TranslateModule } from '@ngx-translate/core';
import { NgxChartsModule } from '@swimlane/ngx-charts';

import { PeriodeRapport } from '../../core/models/analytics.model';
import { VentesService } from '../../core/services/ventes.service';
import { SalesHeatmapComponent } from '../../shared/components/sales-heatmap/sales-heatmap.component';

/**
 * Rapports et analyses.
 *
 * Tous les graphiques et la heatmap sont alimentés par `VentesService`, qui
 * derive ses agrégats du même historique simulé que le dashboard : les chiffres
 * des deux écrans sont donc cohérents entre eux.
 */
@Component({
  selector: 'app-rapports',
  standalone: true,
  imports: [
    DecimalPipe,
    TranslateModule,
    NgxChartsModule,
    MatButtonModule,
    MatIconModule,
    MatSelectModule,
    MatFormFieldModule,
    SalesHeatmapComponent,
  ],
  templateUrl: './rapports.component.html',
  styleUrl: './rapports.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RapportsComponent {
  private readonly ventes = inject(VentesService);

  readonly periode = signal<PeriodeRapport>('semaine');

  /** Chiffre d'affaires agrégé sur la période choisie. */
  readonly caParJour = computed(() => this.ventes.caParPeriode(this.periode()));

  /** Volumes vendus, par vin. */
  readonly topVins = computed(() => this.ventes.topVins());

  /** Répartition par catégorie de vin. */
  readonly categories = computed(() => this.ventes.ventesParCategorie());

  /** Efficacité des promotions (ventes pour mille bouteilles concernées). */
  readonly promotions = computed(() =>
    this.ventes.efficacitePromos().map((ligne) => ({
      name: ligne.libelle,
      value: Math.round(ligne.volume * 100) / 100,
    })),
  );

  /** Matrice jour × heure pour la heatmap. */
  readonly matrice = this.ventes.matrice;

  /** Pic de ventes sur la matrice. */
  readonly picVentes = this.ventes.picVentes;

  /** Indicateurs de la période (CA, tickets, volume, panier moyen, évolutions). */
  readonly indicateurs = computed(() => this.ventes.indicateurs(this.periode()));

  get totalCa(): number {
    return this.indicateurs().ca;
  }

  changerPeriode(periode: PeriodeRapport): void {
    this.periode.set(periode);
  }

  async exporterPdf(): Promise<void> {
    const { default: jsPDF } = await import('jspdf');
    await import('jspdf-autotable');
    const doc = new jsPDF();
    doc.text("Rapport Lazan'i Betsileo", 14, 16);
    doc.text(`Periode : ${this.periode()} - CA total : ${this.totalCa.toLocaleString('fr-FR')} Ar`, 14, 26);
    doc.save('rapport-lazani-betsileo.pdf');
  }

  async exporterExcel(): Promise<void> {
    const xlsx = await import('xlsx');
    const feuille = xlsx.utils.json_to_sheet(
      this.caParJour().map((jour) => ({ jour: jour.name, chiffreAffaires: Math.round(jour.value) })),
    );
    const classeur = xlsx.utils.book_new();
    xlsx.utils.book_append_sheet(classeur, feuille, 'CA');
    xlsx.writeFile(classeur, 'rapport-lazani-betsileo.xlsx');
  }
}