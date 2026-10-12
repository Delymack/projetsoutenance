import { DatePipe, DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { TranslateModule } from '@ngx-translate/core';
import { firstValueFrom } from 'rxjs';

import { PanierLigne } from '../../core/models/product.model';
import { PanierService } from '../../core/services/panier.service';
import { VinService } from '../../core/services/vin.service';
import {
  ReservationDetail,
  ReservationsService,
} from '../../core/services/reservations.service';

/** Statuts proposés dans le filtre de la file de réception. */
const STATUTS = ['EN_ATTENTE', 'ACOMPTE', 'SOLDEE', 'ANNULEE', 'EXPIREE'] as const;

/**
 * Section « Commandes reçues » (équipe : admin / gestionnaire / vendeur).
 *
 * Liste les commandes passées par les clients depuis le frontend Angular
 * (`POST /api/reservations/site/`), lues via `GET /api/reservations/`
 * (permission CanManageVentes).
 */
@Component({
  selector: 'app-commandes-recues',
  standalone: true,
  imports: [
    DatePipe,
    DecimalPipe,
    ReactiveFormsModule,
    RouterLink,
    TranslateModule,
    MatButtonModule,
    MatButtonToggleModule,
    MatIconModule,
    MatProgressSpinnerModule,
  ],
  templateUrl: './commandes-recues.component.html',
  styleUrl: './commandes-recues.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CommandesRecuesComponent {
  private readonly reservationsService = inject(ReservationsService);
  private readonly router = inject(Router);
  private readonly panier = inject(PanierService);
  private readonly vinsService = inject(VinService);

  readonly statuts = STATUTS;

  readonly chargement = signal(true);
  readonly erreur = signal<string | null>(null);
  readonly liste = signal<ReservationDetail[]>([]);
  readonly statutFiltre = signal<string | null>(null);
  readonly referenceOuverte = signal<string | null>(null);
  readonly validationEnCours = signal<string | null>(null);
  readonly erreurAction = signal<string | null>(null);
  readonly motifRefus = new FormControl('', {
    nonNullable: true,
    validators: [Validators.required, Validators.minLength(5), Validators.maxLength(255)],
  });

  /** Commandes après application du filtre par statut. */
  readonly commandes = computed(() => {
    const statut = this.statutFiltre();
    return statut ? this.liste().filter((r) => r.statut === statut) : this.liste();
  });

  /** Commandes encore en cours (à servir / à encaisser). */
  readonly nbEnCours = computed(
    () =>
      this.liste().filter(
        (r) => r.statut === 'EN_ATTENTE' || r.statut === 'ACOMPTE',
      ).length,
  );

  /** Total en attente de règlement, toutes commandes filtrées confondues. */
  readonly totalAffiche = computed(() =>
    this.commandes().reduce((somme, r) => somme + Number(r.montant_total || 0), 0),
  );

  constructor() {
    void this.charger();
  }

  /** Recharge la file complète depuis le backend. */
  async charger(): Promise<void> {
    this.chargement.set(true);
    this.erreur.set(null);
    try {
      this.liste.set(await this.reservationsService.listeEquipe());
    } catch (err: unknown) {
      const code = (err as { status?: number } | null)?.status;
      this.erreur.set(
        code === 401 || code === 403
          ? 'Accès refusé : votre rôle ne permet pas de consulter les commandes.'
          : 'Impossible de charger les commandes reçues. Vérifiez la connexion au serveur.',
      );
    } finally {
      this.chargement.set(false);
    }
  }

  /** Déplie / replie le détail d'une commande. */
  basculer(reservation: ReservationDetail): void {
    const reference = reservation.reference;
    this.referenceOuverte.update((ouverte) => (ouverte === reference ? null : reference));
    this.erreurAction.set(null);
    this.motifRefus.reset('');
  }

  async validerCommande(reservation: ReservationDetail): Promise<void> {
    if (!reservation.id || this.validationEnCours()) return;
    this.validationEnCours.set(reservation.reference);
    this.erreurAction.set(null);
    try {
      await this.reservationsService.valider(reservation.id);
      await this.charger();
    } catch (err: unknown) {
      this.erreurAction.set(
        err instanceof Error ? err.message : 'La commande n’a pas pu être validée.',
      );
    } finally {
      this.validationEnCours.set(null);
    }
  }

  async refuserCommande(reservation: ReservationDetail): Promise<void> {
    if (!reservation.id || this.validationEnCours()) return;
    if (this.motifRefus.invalid) {
      this.motifRefus.markAsTouched();
      return;
    }
    this.validationEnCours.set(reservation.reference);
    this.erreurAction.set(null);
    try {
      await this.reservationsService.refuser(reservation.id, this.motifRefus.value);
      this.motifRefus.reset('');
      await this.charger();
    } catch (err: unknown) {
      this.erreurAction.set(
        err instanceof Error ? err.message : 'La commande n’a pas pu être refusée.',
      );
    } finally {
      this.validationEnCours.set(null);
    }
  }

  /** Libellé du client (prénom + nom), à défaut la référence du contact. */
  client(reservation: ReservationDetail): string {
    const c = reservation.client;
    if (!c) return '—';
    const nom = [c.prenom, c.nom].filter(Boolean).join(' ').trim();
    return nom || c.telephone || c.email || '—';
  }

  /** Icône Material du statut. */
  icone(statut: string | undefined): string {
    switch (statut) {
      case 'SOLDEE':
        return 'check_circle';
      case 'ANNULEE':
      case 'EXPIREE':
        return 'cancel';
      default:
        return 'local_shipping';
    }
  }

  /** Total d'une ligne du détail. */
  totalLigne(ligne: NonNullable<ReservationDetail['lignes']>[number]): number {
    return Math.round(Number(ligne.prix_unitaire || 0) * ligne.quantite);
  }

  /**
   * Passerelle Click-and-Collect : charge les articles de la commande en caisse,
   * pré-remplit l'identité du client et redirige vers le terminal de caisse.
   */
  async encaisserEnCaisse(reservation: ReservationDetail): Promise<void> {
    if (!reservation.lignes?.length || this.validationEnCours()) return;
    let commande = reservation;
    this.validationEnCours.set(commande.reference);
    this.erreurAction.set(null);
    try {
      if (commande.source === 'SITE' && commande.validation_statut === 'A_VALIDER') {
        await this.reservationsService.valider(commande.id!);
        await this.charger();
        commande =
          this.liste().find((r) => r.id === commande.id) || commande;
      }
      const lignesPanier: PanierLigne[] = [];
      for (const ligne of commande.lignes ?? []) {
        try {
          const vin = await firstValueFrom(
            this.vinsService.obtenirParId(String(ligne.produit_id)),
          );
          if (vin) {
            lignesPanier.push({
              vin,
              quantite: ligne.quantite,
              prixUnitaire: Number(ligne.prix_unitaire || vin.prix),
              remisePct: 0,
            });
          }
        } catch {
          // Produit ignoré si introuvable
        }
      }
      if (lignesPanier.length > 0) {
        this.panier.restaurerLignes(lignesPanier);
        localStorage.setItem('lb.caisse.client_predefini', this.client(commande));
        void this.router.navigate(['/caisse']);
      }
    } catch (err: unknown) {
      this.erreurAction.set(
        err instanceof Error ? err.message : 'L’encaissement n’a pas pu être préparé.',
      );
    } finally {
      this.validationEnCours.set(null);
    }
  }
}
