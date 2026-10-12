import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Router } from '@angular/router';
import { TranslateModule } from '@ngx-translate/core';

import { CategorieNotification } from '../../../core/models/notification.model';
import { LangueService } from '../../../core/services/langue.service';
import {
  CATEGORIES_NOTIFICATION,
  NotificationService,
} from '../../../core/services/notification.service';

/**
 * Panneau de notifications.
 *
 * Il est monté dans un `mat-menu` de la barre de navigation : au clic sur la
 * cloche, toutes les alertes non lues sont automatiquement marquées comme lues
 * (une notification non lue est une notification que l'on vient de regarder).
 *
 * Le panneau ne demande jamais la permission tout seul : la demande part d'un
 * bouton, car Chrome l'ignore s'il n'y a pas de geste utilisateur explicite.
 */
@Component({
  selector: 'app-notification-panneau',
  standalone: true,
  imports: [
    DatePipe,
    TranslateModule,
    MatButtonModule,
    MatDividerModule,
    MatIconModule,
    MatTooltipModule,
  ],
  templateUrl: './notification-panneau.component.html',
  styleUrl: './notification-panneau.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class NotificationPanneauComponent {
  private readonly notifications = inject(NotificationService);
  private readonly router = inject(Router);
  private readonly langue = inject(LangueService);

  readonly alertes = this.notifications.alertes;
  readonly autorisation = this.notifications.autorisation;
  readonly preferences = this.notifications.preferences;
  readonly disponible = this.notifications.disponible;

  /** Catégories proposées dans les réglages. */
  readonly categories = CATEGORIES_NOTIFICATION;

  /** Le panneau est-il en train de demander la permission ? */
  readonly demandeEnCours = signal(false);

  /** Message affiché après une action (permission accordée, prefs…). */
  readonly message = signal<string | null>(null);

  /** Icône Material d'une catégorie. */
  icone(categorie: CategorieNotification): string {
    return this.notifications.icone(categorie);
  }

  /** Demande la permission de notification au navigateur. */
  async demanderAutorisation(): Promise<void> {
    this.demandeEnCours.set(true);
    try {
      const resultat = await this.notifications.demanderAutorisation();
      if (resultat === 'granted') {
        this.notifications.notifier(
          'promo',
          this.langue.t('NOTIF.permissionAccordee'),
          this.langue.t('NOTIF.permissionDetail'),
        );
      } else if (resultat === 'denied') {
        this.flash(this.langue.t('NOTIF.permissionRefusee'));
      } else {
        this.flash(this.langue.t('NOTIF.permissionIndisponible'));
      }
    } finally {
      this.demandeEnCours.set(false);
    }
  }

  /** Active / désactive une catégorie d'alertes. */
  basculer(categorie: CategorieNotification): void {
    this.notifications.basculerPreference(categorie);
  }

  /** Ouvre la page liée à l'alerte, puis marque celle-ci comme lue. */
  ouvrir(alerteId: string, lien: string | null): void {
    this.notifications.marquerLue(alerteId);
    if (!lien) return;
    void this.router.navigateByUrl(lien);
  }

  /** Marque toutes les alertes comme lues. */
  toutMarquerLu(): void {
    this.notifications.toutMarquerLu();
  }

  /** Vide le panneau. */
  effacer(): void {
    this.notifications.effacer();
  }

  private flash(texte: string): void {
    this.message.set(texte);
    setTimeout(() => {
      if (this.message() === texte) this.message.set(null);
    }, 3200);
  }
}