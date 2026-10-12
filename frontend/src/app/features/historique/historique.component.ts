import { DatePipe, DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { TranslateModule } from '@ngx-translate/core';

import { Commande, StatutCommande } from '../../core/models/commande.model';
import { Vin } from '../../core/models/product.model';
import { AuthService } from '../../core/services/auth.service';
import { CommandesService, STATUTS_COMMANDE } from '../../core/services/commandes.service';
import { VinService } from '../../core/services/vin.service';
import { environment } from '../../../environments/environment';

/** Une ligne de commande enrichie du vin correspondant. */
interface LigneAffichee {
  vin: Vin | undefined;
  vinId: string;
  quantite: number;
  total: number;
}

/**
 * Historique des commandes.
 *
 * La page liste les commandes du client, de la plus récente à la plus ancienne,
 * avec un filtre par statut et un filtre par année. Chaque commande est
 * dépliable : le détail montre les bouteilles commandées, la remise et la
 * livraison.
 */
@Component({
  selector: 'app-historique',
  standalone: true,
  imports: [
    DatePipe,
    DecimalPipe,
    RouterLink,
    TranslateModule,
    MatButtonModule,
    MatButtonToggleModule,
    MatIconModule,
    MatMenuModule,
  ],
  templateUrl: './historique.component.html',
  styleUrl: './historique.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class HistoriqueComponent {
  private readonly vinService = inject(VinService);
  private readonly auth = inject(AuthService);

  readonly commandesService = inject(CommandesService);
  readonly statuts = STATUTS_COMMANDE;

  /** Statut sélectionné dans le filtre (`null` = tous). */
  readonly statutFiltre = signal<StatutCommande | null>(null);
  /** Année sélectionnée dans le filtre (`null` = toutes). */
  readonly anneeFiltre = signal<number | null>(null);
  /** Référence de la commande dont le détail est déplié. */
  readonly commandeOuverte = signal<string | null>(null);

  private readonly catalogue = signal<Vin[]>([]);

  /** Années présentes dans l'historique, de la plus récente à la plus ancienne. */
  readonly annees = computed(() => {
    const annees = this.commandesService
      .commandes()
      .map((commande) => new Date(commande.date).getFullYear());
    return [...new Set(annees)].sort((a, b) => b - a);
  });

  /** Commandes après application des filtres. */
  readonly commandes = computed(() =>
    this.commandesService.commandes().filter((commande) => {
      if (this.statutFiltre() && commande.statut !== this.statutFiltre()) return false;
      if (this.anneeFiltre() && new Date(commande.date).getFullYear() !== this.anneeFiltre()) return false;
      return true;
    }),
  );

  constructor() {
    if (!environment.useMock) {
      // 1) file d'attente (caisse) + suivi des réservations du navigateur ;
      // 2) pour un client connecté, ses propres commandes côté serveur —
      //    fusionnées après `rafraichir`, qui réécrit la liste complète.
      void this.commandesService
        .rafraichir()
        .then(() => (this.auth.connecte() ? this.commandesService.rafraichirMesCommandes() : undefined))
        .catch((erreur: unknown) =>
          console.error('Historique : chargement des ventes impossible.', erreur),
        );
    }
    this.vinService.listerTous().subscribe({
      next: (vins) => this.catalogue.set(vins),
      error: (erreur: unknown) => console.error('Historique : catalogue indisponible.', erreur),
    });
  }

  /** Bouteilles d'une commande, avec le vin résolu pour l'affichage. */
  lignes(commande: Commande): LigneAffichee[] {
    return commande.lignes.map((ligne) => {
      const vin = this.catalogue().find((v) => v.id === ligne.vinId);
      return {
        vin,
        vinId: ligne.vinId,
        quantite: ligne.quantite,
        total: Math.round(ligne.prixUnitaire * ligne.quantite * (1 - ligne.remisePct / 100)),
      };
    });
  }

  /** Bascule l'affichage du détail d'une commande. */
  basculer(commande: Commande): void {
    this.commandeOuverte.update((ouverte) => (ouverte === commande.reference ? null : commande.reference));
  }

  /** Icône Material correspondant au statut. */
  icone(statut: StatutCommande): string {
    switch (statut) {
      case 'livree':
        return 'check_circle';
      case 'annulee':
        return 'cancel';
      default:
        return 'local_shipping';
    }
  }

  /** Partage la commande : `navigator.share` si disponible, copie sinon. */
  async partager(commande: Commande): Promise<void> {
    const texte = `${commande.reference} — ${this.commandesService.quantite(commande)} bouteille(s) — ${this.commandesService.total(commande)} Ar`;
    if (!navigator.share) {
      await navigator.clipboard?.writeText(texte);
      return;
    }
    await navigator.share({ title: commande.reference, text: texte, url: location.href });
  }
}
