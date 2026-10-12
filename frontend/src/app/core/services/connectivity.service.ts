import { Injectable, NgZone, computed, inject, signal } from '@angular/core';

/**
 * Service de connectivité.
 *
 * Expose l'état en ligne / hors ligne de l'application.
 * On ne se contente pas de `navigator.onLine` (peu fiable) : on croise
 * l'événement online/offline du navigateur avec un test réseau réel.
 */
@Injectable({ providedIn: 'root' })
export class ConnectivityService {
  private readonly zone = inject(NgZone);

  /** Vrai si l'application pense être en ligne. */
  readonly enLigne = signal<boolean>(navigator.onLine);

  /** Vrai si le bandeau « hors ligne » doit être affiché. */
  readonly horsLigne = computed(() => !this.enLigne());

  /** Abonnements à notifier lors d'un changement de connectivité. */
  private listeners: ((enLigne: boolean) => void)[] = [];

  constructor() {
    // Les événements 'online'/'offline' ne passent pas par NgZone : on y revient
    // manuellement pour que les signaux soient bien détectés par la CD.
    const majEtat = () => {
      this.zone.run(() => {
        const precedent = this.enLigne();
        this.enLigne.set(navigator.onLine);
        if (precedent !== this.enLigne()) {
          this.listeners.forEach((fn) => fn(this.enLigne()));
        }
      });
    };

    window.addEventListener('online', majEtat);
    window.addEventListener('offline', majEtat);
  }

  /** Notifie une fois le retour de la connexion (utilisé par la sync). */
  onChange(fn: (enLigne: boolean) => void): () => void {
    this.listeners.push(fn);
    return () => (this.listeners = this.listeners.filter((l) => l !== fn));
  }

  /**
   * Test réseau réel (ping HEAD sur l'API). Utile car `navigator.onLine`
   * peut être `true` alors que le routeur/serveur est injoignable.
   */
  async verifier(pingUrl = '/favicon.ico'): Promise<boolean> {
    if (!navigator.onLine) return false;
    try {
      const controleur = new AbortController();
      const minuteur = setTimeout(() => controleur.abort(), 3000);
      const reponse = await fetch(pingUrl, {
        method: 'HEAD',
        cache: 'no-store',
        signal: controleur.signal,
      });
      clearTimeout(minuteur);
      return reponse.ok || reponse.status === 304;
    } catch {
      return false;
    }
  }
}