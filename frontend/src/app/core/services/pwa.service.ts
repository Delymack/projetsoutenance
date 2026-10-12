import { isPlatformBrowser } from '@angular/common';
import { Injectable, PLATFORM_ID, inject, signal } from '@angular/core';
import { SwUpdate, VersionEvent } from '@angular/service-worker';

/** Détail d'un prompt d'installation, hors API standard (non encore typée). */
interface PromptInstallation extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

/**
 * Service PWA.
 *
 * Regroupe ce qui dépend de l'installation de l'application :
 *  - détection d'une nouvelle version mise en cache par le service worker, avec
 *    rechargement explicite (jamais de rechargement subi en pleine caisse) ;
 *  - prompt d'installation de l'application (`beforeinstallprompt`), affiché une
 *    seule fois et seulement sur les écrans publics ;
 *  - suivi de l'installation effective (`appinstalled`).
 *
 * Les deux signaux (`nouvelleVersion`, `installationDisponible`) sont
 * consommés par un composant d'interface ; le service ne fait aucun accès réseau.
 */
@Injectable({ providedIn: 'root' })
export class PwaService {
  private readonly swUpdate = inject(SwUpdate);
  private readonly platformId = inject(PLATFORM_ID);

  /** Une nouvelle version est prête : l'utilisateur doit recharger. */
  readonly nouvelleVersion = signal(false);

  /** Le navigateur a proposé d'installer l'application. */
  readonly installationDisponible = signal(false);

  /** L'application a été installée sur l'appareil. */
  readonly installee = signal(false);

  private promptDiffere: PromptInstallation | null = null;

  constructor() {
    if (!isPlatformBrowser(this.platformId)) return;

    this.ecouterLesVersions();
    this.ecouterInstallation();
  }

  /** Recharge la page pour prendre la version en attente. */
  actualiser(): void {
    this.nouvelleVersion.set(false);
    location.reload();
  }

  /** Demande l'installation ; la promesse est ignorée si l'utilisateur refuse. */
  installer(): Promise<boolean> {
    const prompt = this.promptDiffere;
    if (!prompt) return Promise.resolve(false);

    this.installationDisponible.set(false);
    return prompt
      .prompt()
      .then(() => prompt.userChoice)
      .then((choix) => {
        this.promptDiffere = null;
        return choix.outcome === 'accepted';
      })
      .catch(() => false);
  }

  /** Ferme le prompt sans installer (bouton « plus tard »). */
  reporterInstallation(): void {
    this.installationDisponible.set(false);
    this.promptDiffere = null;
  }

  /** Signale une version prête. Utilisé par les tests. */
  private ecouterLesVersions(): void {
    if (!this.swUpdate.isEnabled) return;

    // `VersionReadyEvent` matérialise une version téléchargée et prête à
    // l'emploi ; l'interface propose un rechargement manuel plutôt qu'un
    // rechargement subi en pleine caisse.
    this.swUpdate.versionUpdates.subscribe((evenement: VersionEvent) => {
      console.info('Nouvelle version de l\'application prête.', evenement);
      this.nouvelleVersion.set(true);
    });
  }

  /** Capture le prompt d'installation avant que le navigateur ne le consomme. */
  private ecouterInstallation(): void {
    window.addEventListener('beforeinstallprompt', (evenement) => {
      // L'événement ne doit pas afficher la bannière native du navigateur.
      evenement.preventDefault();
      this.promptDiffere = evenement as PromptInstallation;
      this.installationDisponible.set(true);
    });

    window.addEventListener('appinstalled', () => {
      this.promptDiffere = null;
      this.installationDisponible.set(false);
      this.installee.set(true);
    });
  }
}
