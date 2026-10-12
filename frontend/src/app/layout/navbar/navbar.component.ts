import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatDividerModule } from '@angular/material/divider';
import { MatBadgeModule } from '@angular/material/badge';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule } from '@ngx-translate/core';

import { ThemeService } from '../../core/services/theme.service';
import { LangueService } from '../../core/services/langue.service';
import { PanierService } from '../../core/services/panier.service';
import { ConnectivityService } from '../../core/services/connectivity.service';
import { AuthService } from '../../core/services/auth.service';
import { AvatarService } from '../../core/services/avatar.service';
import { NotificationService } from '../../core/services/notification.service';
import { MessageService } from '../../core/services/message.service';
import { AvatarComponent } from '../../shared/components/avatar/avatar.component';
import { NotificationPanneauComponent } from '../../shared/components/notification-panneau/notification-panneau.component';
import { ProfilPanneauComponent } from '../../shared/components/profil-panneau/profil-panneau.component';

/** Liens de navigation principaux (desktop). */
interface LienNav {
  chemin: string;
  cle: string;
  icone: string;
}

/**
 * Barre de navigation principale.
 *
 * - responsive : barre complète sur desktop, tiroir (mat-menu) sur mobile ;
 * - le thème, la langue et le panier sont lus via des `signal` : le template
 *   se met à jour sans détection de changement manuelle.
 */
@Component({
  selector: 'app-navbar',
  standalone: true,
  imports: [
    RouterLink,
    RouterLinkActive,
    TranslateModule,
    MatButtonModule,
    MatIconModule,
    MatMenuModule,
    MatDividerModule,
    MatBadgeModule,
    MatTooltipModule,
    AvatarComponent,
    NotificationPanneauComponent,
    ProfilPanneauComponent,
  ],
  templateUrl: './navbar.component.html',
  styleUrl: './navbar.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class NavbarComponent {
  private readonly themeService = inject(ThemeService);
  private readonly langueService = inject(LangueService);
  private readonly panier = inject(PanierService);
  private readonly connectivite = inject(ConnectivityService);
  private readonly avatar = inject(AvatarService);
  readonly auth = inject(AuthService);

  /** Photo de profil affichée dans la barre (ou initiales, cf. `AvatarComponent`). */
  readonly photo = this.avatar.photo;

  /**
 * Notifications. Le service est instancié au démarrage de la
   * navbar : les alertes déjà enregistrées (promotion en cours, stock faible) sont
   * donc disponibles avant même que l'utilisateur n'ouvre le panneau.
   */
  private readonly notifications = inject(NotificationService);

 /** messages conseiller en attente de lecture. */
  private readonly messages = inject(MessageService);
  readonly nonLusMessages = this.messages.nonLus;

  // --- Exposition des signaux aux templates ---
  readonly estSombre = this.themeService.estSombre;
  readonly langueCourante = this.langueService.langue;
  readonly nbArticles = this.panier.nbArticles;
  readonly horsLigne = this.connectivite.horsLigne;
  readonly nonLues = this.notifications.nonLues;
  readonly langues = this.langueService.langues;

  /** Liens affichés en desktop (et dans le menu mobile). */
  readonly liens: LienNav[] = [
    { chemin: '/', cle: 'NAV.accueil', icone: 'home' },
    { chemin: '/catalogue', cle: 'NAV.catalogue', icone: 'wine_bar' },
    { chemin: '/promotions', cle: 'NAV.promos', icone: 'card_giftcard' },
    { chemin: '/favoris', cle: 'NAV.favoris', icone: 'favorite' },
  ];

  /** Liens réservés aux rôles encadrant (dashboard, rapports, commandes). */
  readonly liensEncadrant: LienNav[] = [
    { chemin: '/commandes', cle: 'NAV.commandes', icone: 'inbox' },
    { chemin: '/dashboard', cle: 'NAV.dashboard', icone: 'dashboard' },
    { chemin: '/rapports', cle: 'NAV.rapports', icone: 'insert_chart' },
  ];

  /** L'utilisateur est-il administrateur / gestionnaire / vendeur ? */
  readonly estEncadrant = computed(() =>
    this.auth.hasRole(['admin', 'gestionnaire', 'vendeur']),
  );

  /** Bascule clair / sombre. */
  basculerTheme(): void {
    this.themeService.basculer();
  }

  /** Change la langue. */
  changerLangue(code: 'fr' | 'mg' | 'en'): void {
    this.langueService.changer(code);
  }
}