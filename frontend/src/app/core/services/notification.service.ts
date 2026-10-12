import { isPlatformBrowser } from '@angular/common';
import { Injectable, PLATFORM_ID, computed, inject, signal } from '@angular/core';

import { Alerte, AutorisationNotification, CategorieNotification } from '../models/notification.model';

const CLE_ALERTES = 'lb.notifications';
const CLE_PREFERENCES = 'lb.notifications.prefs';

/** Nombre d'alertes conservées dans le panneau (au-delà, on purge les plus anciennes). */
const TAILLE_MAX = 30;

/** Catégories proposées dans le panneau de réglages. */
export const CATEGORIES_NOTIFICATION: CategorieNotification[] = ['promo', 'stock', 'commande'];

/**
 * Notifications.
 *
 * Trois niveaux de реалиité, du plus simple au plus complet :
 *  1. **liste applicative** — toujours disponible : les alertes sont mémorisées
 *     et lues par `<app-notification-panneau>`. C'est ce qui fonctionne dans la
 *     démonstration, y compris hors connexion ;
 *  2. **notification système** — si l'utilisateur a accordé la permission, chaque
 *     alerte remonte aussi dans le centre de notifications du navigateur ou de
 *     l'appareil ;
 *  3. **push serveur** — le même `notifier()` alimentera le `showNotification`
 *     du service worker dès que le backend Django enverra des messages Web Push.
 *
 * Le service ne dépend ni d'un composant ni d'un `Router` : la navigation est
 * déléguée au panneau, qui reçoit la route dans `Alerte.lien`.
 */
@Injectable({ providedIn: 'root' })
export class NotificationService {
  private readonly platformId = inject(PLATFORM_ID);

  /** Alertes connues, les plus récentes d'abord. */
  readonly alertes = signal<Alerte[]>(this.lireAlertes());

  /** Catégories activées par l'utilisateur. */
  readonly preferences = signal<Record<CategorieNotification, boolean>>(this.lirePreferences());

  /** Autorisation de l'API Notification, lue au démarrage. */
  readonly autorisation = signal<AutorisationNotification>(this.lireAutorisation());

  /** Nombre d'alertes non lues — pastille sur la cloche de la navbar. */
  readonly nonLues = computed(() => this.alertes().filter((alerte) => !alerte.lue).length);

  /** L'API Notification est-elle utilisable dans ce navigateur ? */
  readonly disponible = signal(false);

  constructor() {
    this.disponible.set(
      isPlatformBrowser(this.platformId) && typeof Notification !== 'undefined',
    );
    if (!this.disponible()) this.autorisation.set('inconnu');
  }

  /**
   * Demande l'autorisation au navigateur.
   * Doit être appelée depuis un geste utilisateur (clic) : sans clic, Chrome
   * refuse silencieusement la demande.
   *
   * Le message de confirmation n'est **pas** produit ici : le service ignore
   * volontairement la langue. C'est l'appelant (le panneau) qui émet ensuite
   * `notifier()` avec des textes traduits.
   */
  async demanderAutorisation(): Promise<AutorisationNotification> {
    if (!this.disponible()) return 'inconnu';

    try {
      const resultat = await Notification.requestPermission();
      this.autorisation.set(resultat);
      return resultat;
    } catch (erreur) {
      console.warn('Demande de permission de notification refusée par le navigateur.', erreur);
      this.autorisation.set('denied');
      return 'denied';
    }
  }

  /** Active ou désactive une catégorie d'alertes. */
  basculerPreference(categorie: CategorieNotification): void {
    this.preferences.update((preferences) => {
      const suivantes = { ...preferences, [categorie]: !preferences[categorie] };
      this.ecrirePreferences(suivantes);
      return suivantes;
    });
  }

  /**
   * Enregistre une alerte et, si l'autorisation a été accordée, la pousse vers le
   * système. La catégorie désactivée par l'utilisateur est ignorée : c'est le
   * seul endroit où le filtrage a lieu, tous les appelants restent simples.
   */
  notifier(
    categorie: CategorieNotification,
    titre: string,
    message: string,
    lien: string | null = null,
  ): void {
    if (!this.preferences()[categorie]) return;

    const alerte: Alerte = {
      id: `n-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      categorie,
      titre,
      message,
      date: new Date().toISOString(),
      lue: false,
      lien,
    };

    this.alertes.update((alertes) => {
      const suivantes = [alerte, ...alertes].slice(0, TAILLE_MAX);
      this.ecrireAlertes(suivantes);
      return suivantes;
    });

    this.pushSysteme(alerte);
  }

  /** Marque une alerte comme lue. */
  marquerLue(id: string): void {
    this.alertes.update((alertes) => {
      const suivantes = alertes.map((alerte) =>
        alerte.id === id ? { ...alerte, lue: true } : alerte,
      );
      this.ecrireAlertes(suivantes);
      return suivantes;
    });
  }

  /** Marque toutes les alertes comme lues (au clic sur la cloche). */
  toutMarquerLu(): void {
    this.alertes.update((alertes) => {
      const suivantes = alertes.map((alerte) => ({ ...alerte, lue: true }));
      this.ecrireAlertes(suivantes);
      return suivantes;
    });
  }

  /** Vide le panneau. */
  effacer(): void {
    this.alertes.set([]);
    this.ecrireAlertes([]);
  }

  /** Icône Material associée à une catégorie. */
  icone(categorie: CategorieNotification): string {
    switch (categorie) {
      case 'promo':
        return 'card_giftcard';
      case 'stock':
        return 'inventory_2';
      case 'commande':
        return 'receipt_long';
    }
  }

  // --- Persistance ---

  private lireAlertes(): Alerte[] {
    try {
      const brut = localStorage.getItem(CLE_ALERTES);
      if (!brut) return this.alertesDemo();
      const parse: unknown = JSON.parse(brut);
      return Array.isArray(parse) ? (parse as Alerte[]) : this.alertesDemo();
    } catch {
      return this.alertesDemo();
    }
  }

  /**
   * Alertes de démonstration.
   * Injectées une seule fois : la page « historique » et le panneau n'ont jamais
   * l'air vides, et la démonstration reste stable d'une session à l'autre.
   */
  private alertesDemo(): Alerte[] {
    const maintenant = Date.now();
    const alertes: Alerte[] = [
      {
        id: 'n-demo-1',
        categorie: 'promo',
        titre: "Fête des Mères : -15 %",
        message: 'Le code MERE15 est valable jusqu’à la fin du mois sur une sélection de cuvées.',
        date: new Date(maintenant - 3_600_000).toISOString(),
        lue: false,
        lien: '/promotions',
      },
      {
        id: 'n-demo-2',
        categorie: 'stock',
        titre: 'Stock faible',
        message: 'Il reste quelques bouteilles de Liqueur de Fianarantsoa.',
        date: new Date(maintenant - 7_200_000).toISOString(),
        lue: false,
        lien: '/catalogue',
      },
      {
        id: 'n-demo-3',
        categorie: 'commande',
        titre: 'Commande CMD-4821 livrée',
        message: 'Votre commande a été remise en main propre à Fianarantsoa.',
        date: new Date(maintenant - 86_400_000).toISOString(),
        lue: true,
        lien: '/historique',
      },
    ];

    this.ecrireAlertes(alertes);
    return alertes;
  }

  private ecrireAlertes(alertes: Alerte[]): void {
    try {
      localStorage.setItem(CLE_ALERTES, JSON.stringify(alertes));
    } catch {
      console.warn('Notifications non enregistrées (stockage indisponible).');
    }
  }

  private lirePreferences(): Record<CategorieNotification, boolean> {
    const defaut: Record<CategorieNotification, boolean> = { promo: true, stock: true, commande: true };
    try {
      const brut = localStorage.getItem(CLE_PREFERENCES);
      if (!brut) return defaut;
      const parse = JSON.parse(brut) as Partial<Record<CategorieNotification, boolean>>;
      return { ...defaut, ...parse };
    } catch {
      return defaut;
    }
  }

  private ecrirePreferences(preferences: Record<CategorieNotification, boolean>): void {
    try {
      localStorage.setItem(CLE_PREFERENCES, JSON.stringify(preferences));
    } catch {
      console.warn('Préférences de notification non enregistrées.');
    }
  }

  private lireAutorisation(): AutorisationNotification {
    if (!isPlatformBrowser(this.platformId) || typeof Notification === 'undefined') return 'inconnu';
    return Notification.permission;
  }

  /** Notification système (navigateur / PWA installée). */
  private pushSysteme(alerte: Alerte): void {
    if (this.autorisation() !== 'granted' || !this.disponible()) return;

    try {
      const notification = new Notification(alerte.titre, {
        body: alerte.message,
        icon: 'assets/icons/icon-192.svg',
        badge: 'assets/icons/icon-192.svg',
        tag: alerte.id,
      });
      notification.onclick = () => {
        window.focus();
        notification.close();
      };
    } catch (erreur) {
      // Certains navigateurs (mobile strict) refusent la construction directe :
      // l'alerte reste visible dans le panneau applicatif.
      console.warn('Notification système non affichée.', erreur);
    }
  }
}