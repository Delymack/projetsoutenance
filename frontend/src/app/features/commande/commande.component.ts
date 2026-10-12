import { CurrencyPipe, DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { TranslateModule } from '@ngx-translate/core';

import { AuthService } from '../../core/services/auth.service';
import { CommandesService } from '../../core/services/commandes.service';
import { LangueService } from '../../core/services/langue.service';
import { NotificationService } from '../../core/services/notification.service';
import { PanierService } from '../../core/services/panier.service';
import { ProfilService } from '../../core/services/profil.service';
import { ReservationsService } from '../../core/services/reservations.service';

/** tunnel de commande. */
@Component({
  selector: 'app-commande',
  standalone: true,
  imports: [
    CurrencyPipe,
    DecimalPipe,
    ReactiveFormsModule,
    RouterLink,
    TranslateModule,
    MatButtonModule,
    MatButtonToggleModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
  ],
  templateUrl: './commande.component.html',
  styleUrl: './commande.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CommandeComponent {
  private readonly fb = inject(FormBuilder).nonNullable;

  readonly auth = inject(AuthService);
  private readonly commandes = inject(CommandesService);
  private readonly langue = inject(LangueService);
  readonly notifications = inject(NotificationService);
  readonly panier = inject(PanierService);
  readonly profil = inject(ProfilService);
  private readonly reservations = inject(ReservationsService);

  readonly livraison = signal<'livraison' | 'retrait'>('livraison');
  readonly enCours = signal(false);
  readonly reference = signal<string | null>(null);
  readonly enAttenteValidation = signal(false);
 /** points figés avant vidage du panier. */
  readonly pointsGagnes = signal(0);

  readonly form = this.fb.group({
    notes: ['', Validators.maxLength(240)],
    telephone: [
      this.profil.telephone() ||
        this.profil.adresseParDefaut()?.telephone ||
        this.auth.utilisateur()?.telephone ||
        '',
      [Validators.required, Validators.maxLength(20)],
    ],
  });

  readonly modeRetrait = computed(() => this.livraison() === 'retrait');

  /** Frais de livraison : aucun n'est facturé, le total vient du panier. */
  readonly fraisAffiche = computed(() => 0);

  readonly totalAffiche = computed(() =>
    this.panier.sousTotal() + this.fraisAffiche(),
  );

  async valider(): Promise<void> {
    if (this.panier.estVide() || this.enCours()) return;
    const adresse = this.profil.adresseParDefaut();
    if (!this.modeRetrait() && !adresse?.ligne.trim()) {
      this.notifications.notifier(
        'commande',
        'Adresse de livraison requise',
        'Ajoutez une adresse de livraison dans votre profil avant de confirmer.',
        '/profil',
      );
      return;
    }
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    this.enCours.set(true);

    try {
      const nomComplet = this.auth.utilisateur()?.nom.trim() ?? '';
      const [prenom, ...resteNom] = nomComplet.split(/\s+/).filter(Boolean);
      if (!prenom) throw new Error('Le nom du compte est manquant.');
      const reservation = await this.reservations.creerDepuisSite({
        nom: resteNom.join(' ') || prenom,
        prenom,
        telephone: this.form.controls.telephone.value.trim(),
        email: this.auth.utilisateur()?.email ?? '',
        mode_reception: this.modeRetrait() ? 'RETRAIT' : 'LIVRAISON',
        adresse_livraison: this.modeRetrait()
          ? ''
          : [adresse?.ligne, adresse?.ville].filter(Boolean).join(', '),
        note: this.form.controls.notes.value.trim(),
      }, this.panier.lignes());
      const commande = this.commandes.enregistrerReservation(reservation);
      this.panier.vider();
      this.enAttenteValidation.set(true);
      this.pointsGagnes.set(commande.points);
      this.reference.set(reservation.reference);

      this.notifications.notifier(
        'commande',
        this.langue.t('COMMANDE.confirmeeTitre'),
        `Référence : ${reservation.reference}. Suivez la commande dans votre historique.`,
        '/historique',
      );
    } catch (err) {
      console.error('Erreur lors de l\'enregistrement de la réservation :', err);
      const message = err instanceof Error ? err.message : this.langue.t('COMMANDE.erreurDetail');
      this.notifications.notifier(
        'commande',
        this.langue.t('COMMANDE.erreurTitre'),
        message,
      );
    } finally {
      this.enCours.set(false);
    }
  }
}