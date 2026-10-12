import { DatePipe, DecimalPipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule } from '@ngx-translate/core';

import { Commande } from '../../../core/models/commande.model';
import { AuthService } from '../../../core/services/auth.service';
import { AvatarService } from '../../../core/services/avatar.service';
import { CommandesService } from '../../../core/services/commandes.service';
import { FavorisService } from '../../../core/services/favoris.service';
import { FideliteService } from '../../../core/services/fidelite.service';
import { Langue, LangueService } from '../../../core/services/langue.service';
import { MessageService } from '../../../core/services/message.service';
import { NotificationService } from '../../../core/services/notification.service';
import { PanierService } from '../../../core/services/panier.service';
import { ProfilService } from '../../../core/services/profil.service';
import { SonService } from '../../../core/services/son.service';
import { Theme, ThemeService } from '../../../core/services/theme.service';
import { AvatarComponent } from '../avatar/avatar.component';

/** Rayon de l'anneau de fidélité, dans le repère 64 × 64 du SVG. */
const RAYON_ANNEAU = 28;

/** Un raccourci du panneau : route, libellé, icône, compteur éventuel. */
interface Raccourci {
  chemin: string;
  /** Paramètres d'adresse : ouvrent directement la bonne section du profil. */
  params?: Record<string, string>;
  cle: string;
  icone: string;
  compteur?: () => number;
}

/** Un chiffre du bandeau : ce que le client a en cours, en un coup d'œil. */
interface Chiffre {
  cle: string;
  icone: string;
  valeur: string;
  libelle: string;
  chemin: string;
  params?: Record<string, string>;
  alerte: boolean;
}

/**
 * Panneau de compte de la barre de navigation (coin haut droit).
 *
 * Il remplace le menu « nom + e-mail + quatre liens » par ce qu'un client
 * vient réellement chercher : sa carte de fidélité et l'avancement vers le
 * palier suivant, l'état de son activité (commandes, favoris, panier, alertes),
 * sa dernière commande, les raccourcis vers les sections du profil — y compris
 * par lien direct (`/profil?section=adresses`) — et ses réglages (thème,
 * langue, sons) sans quitter la page.
 *
 * Tout est lu dans les services existants : le panneau ne recalcule rien, il
 * affiche ce que la caisse et la boutique ont déjà enregistré.
 */
@Component({
  selector: 'app-profil-panneau',
  standalone: true,
  imports: [
    DatePipe,
    DecimalPipe,
    RouterLink,
    TranslateModule,
    MatButtonModule,
    MatDividerModule,
    MatIconModule,
    MatMenuModule,
    MatTooltipModule,
    AvatarComponent,
  ],
  templateUrl: './profil-panneau.component.html',
  styleUrl: './profil-panneau.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProfilPanneauComponent {
  private readonly auth = inject(AuthService);
  private readonly avatar = inject(AvatarService);
  private readonly fidelite = inject(FideliteService);
  readonly commandes = inject(CommandesService);
  private readonly favoris = inject(FavorisService);
  private readonly panier = inject(PanierService);
  private readonly messages = inject(MessageService);
  private readonly notifications = inject(NotificationService);
  private readonly profil = inject(ProfilService);
  private readonly theme = inject(ThemeService);
  private readonly langue = inject(LangueService);
  private readonly son = inject(SonService);

  /** Sélecteur de fichier masqué : déclenché par la pastille photo. */
  private readonly selecteur = viewChild<ElementRef<HTMLInputElement>>('selecteur');

  // --- Identité ---
  readonly utilisateur = this.auth.utilisateur;
  readonly photo = this.avatar.photo;
  readonly nom = computed(() => this.utilisateur()?.nom ?? '');
  /** E-mail, ou téléphone pour un compte créé par SMS sans adresse e-mail. */
  readonly contact = computed(
    () => this.utilisateur()?.email || this.utilisateur()?.telephone || '',
  );
  readonly role = computed(() => this.auth.role() ?? 'client');

  // --- Fidélité ---
  readonly points = this.fidelite.points;
  readonly palier = this.fidelite.niveau;
  readonly palierSuivant = this.fidelite.niveauSuivant;
  readonly pointsRestants = this.fidelite.pointsRestants;
  readonly progression = computed(() =>
    Math.max(0, Math.min(100, this.fidelite.progression())),
  );
  /** Rayon et circonférence de l'anneau : servent au tracé du cercle. */
  readonly rayon = RAYON_ANNEAU;
  readonly circonference = 2 * Math.PI * RAYON_ANNEAU;
  readonly tiret = computed(() => this.circonference * (1 - this.progression() / 100));

  // --- Activité ---
  readonly derniereCommande = computed<Commande | null>(
    () =>
      [...this.commandes.commandes()].sort((a, b) => b.date.localeCompare(a.date))[0] ?? null,
  );
  readonly nbCommandes = computed(() => this.commandes.commandes().length);
  readonly nonLusMessages = this.messages.nonLus;
  readonly nonLues = this.notifications.nonLues;
  readonly completude = this.profil.completude;

  readonly chiffres = computed<Chiffre[]>(() => [
    {
      cle: 'commandes',
      icone: 'receipt_long',
      valeur: String(this.nbCommandes()),
      libelle: 'PROFIL.commandes',
      chemin: '/historique',
      alerte: false,
    },
    {
      cle: 'favoris',
      icone: 'favorite',
      valeur: String(this.favoris.total()),
      libelle: 'PROFIL.favoris',
      chemin: '/favoris',
      alerte: false,
    },
    {
      cle: 'panier',
      icone: 'shopping_cart',
      valeur: String(this.panier.nbArticles()),
      libelle: 'NAV.panier',
      chemin: '/panier',
      alerte: false,
    },
    {
      cle: 'alertes',
      icone: 'notifications',
      valeur: String(this.nonLues()),
      libelle: 'COMPTE.alertes',
      chemin: '/profil',
      params: { section: 'notifications' },
      alerte: this.nonLues() > 0,
    },
  ]);

  /**
   * Raccourcis vers les sections du profil. Les sections s'ouvrent par lien
   * direct (`?section=`), sinon « Mes adresses » renverrait sur l'onglet
   * « Commandes » et l'utilisateur devrait chercher lui-même.
   */
  readonly raccourcis: Raccourci[] = [
    { chemin: '/profil', cle: 'NAV.profil', icone: 'person' },
    { chemin: '/historique', cle: 'PROFIL.commandes', icone: 'receipt_long' },
    {
      chemin: '/profil',
      params: { section: 'messages' },
      cle: 'PROFIL.messages',
      icone: 'forum',
      compteur: () => this.messages.nonLus(),
    },
    {
      chemin: '/profil',
      params: { section: 'adresses' },
      cle: 'PROFIL.adresses',
      icone: 'local_shipping',
    },
    {
      chemin: '/profil',
      params: { section: 'fidelite' },
      cle: 'PROFIL.fidelite',
      icone: 'workspace_premium',
    },
  ];

  // --- Réglages ---
  readonly estSombre = this.theme.estSombre;
  readonly langues = this.langue.langues;
  readonly langueCourante = this.langue.langue;
  readonly sonActif = this.son.actif;

  // --- États locaux ---
  /** Clé de traduction du dernier retour photo (succès ou refus). */
  readonly retourPhoto = signal<string | null>(null);
  readonly photoEnCours = signal(false);
  /** La déconnexion demande confirmation : un clic de trop ne doit rien casser. */
  readonly confirmation = signal(false);

  // --- Actions ---

  constructor() {
    // Le panneau n'existe qu'une fois le menu ouvert (contenu paresseux de
    // Material) : c'est donc le bon moment pour aller chercher les commandes du
    // client connecté. Sans cela, le panneau afficherait « aucune commande »
    // tant que la page Historique n'a pas été visitée. Le service absorbe les
    // refus et les coupures réseau : rien à rattraper ici.
    void this.commandes.rafraichirMesCommandes();
  }

  /** Ouvre le sélecteur de fichier du navigateur. */
  choisirPhoto(): void {
    this.retourPhoto.set(null);
    this.selecteur()?.nativeElement.click();
  }

  /** Recadre et mémorise la photo choisie. */
  async changerPhoto(evenement: Event): Promise<void> {
    const champ = evenement.target as HTMLInputElement;
    const fichier = champ.files?.[0];
    // Le champ est vidé : choisir deux fois la même photo doit fonctionner.
    champ.value = '';
    if (!fichier) return;

    this.photoEnCours.set(true);
    try {
      await this.avatar.definirDepuisFichier(fichier);
      this.retourPhoto.set('COMPTE.photoEnregistree');
    } catch (erreur) {
      this.retourPhoto.set(erreur instanceof Error ? erreur.message : 'COMPTE.photoIllisible');
    } finally {
      this.photoEnCours.set(false);
    }
  }

  /** Revient à la photo du compte, ou aux initiales. */
  retirerPhoto(): void {
    this.avatar.retirer();
    this.retourPhoto.set('COMPTE.photoRetiree');
  }

  /** Choix explicite du thème : plus court qu'une bascule quand on hésite. */
  definirTheme(theme: Theme): void {
    this.theme.definir(theme);
  }

  changerLangue(code: Langue): void {
    this.langue.changer(code);
  }

  basculerSon(): void {
    this.son.basculer();
  }

  seDeconnecter(): void {
    this.auth.deconnexion();
  }
}