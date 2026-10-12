import { isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  OnDestroy,
  PLATFORM_ID,
  effect,
  inject,
  input,
  untracked,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import { BrowserMultiFormatReader, IScannerControls } from '@zxing/browser';

/**
 * Lecteur de code-barres / QR par caméra.
 *
 * Isolé dans un composant partagé pour que la même implémentation serve la page
 * `/scanner` (client) et la caisse (vendeur) : la logique ZXing, le choix de la
 * caméra et la torche ne sont écrits qu'une fois.
 *
 * Le composant est piloté par l'hôte : il démarre la caméra si `actif` est vrai
 * et émet `codeLu` dès qu'un code est décodé. La lecture s'arrête seule après
 * le premier code réussi, comme dans un vrai point de vente (un même code est
 * lu une seule fois par scan).
 */
@Component({
  selector: 'app-lecteur-code',
  standalone: true,
  imports: [MatProgressSpinnerModule],
  templateUrl: './lecteur-code.component.html',
  styleUrl: './lecteur-code.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LecteurCodeComponent implements OnDestroy {
  private readonly platformId = inject(PLATFORM_ID);

  private readonly video = viewChild<ElementRef<HTMLVideoElement>>('video');

  private lecteur: BrowserMultiFormatReader | null = null;
  private controles: IScannerControls | null = null;

  /** La caméra est-elle active ? Passer à true démarre le flux. */
  readonly actif = input(false);

  /** Émet le texte décodé (EAN-13, QR, code 128…). */
  readonly codeLu = output<string>();

  /** Signale une erreur d'accès à la caméra (permission refusée, aucun device). */
  readonly erreur = output<string>();

  readonly demarrage = signal(false);
  readonly pret = signal(false);

  constructor() {
    // `actif` peut être basculé par l'hôte après le premier rendu : l'effet
    // démarre la caméra quand il passe à true, la coupe quand il repasse à faux.
    effect(() => {
      // `untracked` : ZXing écrit des signals internes pendant le démarrage du
      // flux ; sans cela, l'écriture depuis l'effet lèverait NG0600.
      untracked(() => {
        if (this.actif()) this.demarrer();
        else this.arreter();
      });
    });
  }

  ngOnDestroy(): void {
    this.arreter();
  }

  /** Coupe le flux et rend la caméra au navigateur. */
  arreter(): void {
    this.controles?.stop();
    this.controles = null;
    this.lecteur = null;

    const video = this.video()?.nativeElement;
    if (video) video.srcObject = null;

    this.pret.set(false);
    this.demarrage.set(false);
  }

  /** Relance la caméra après une erreur de permission. */
  redemarrer(): void {
    this.arreter();
    this.demarrer();
  }

  /** Démarre le décodage continu sur la caméra par défaut (arrière si possible). */
  demarrer(): void {
    const video = this.video()?.nativeElement;
    if (!video || !isPlatformBrowser(this.platformId) || this.controles) return;

    this.demarrage.set(true);

    this.lecteur = new BrowserMultiFormatReader(undefined, {
      delayBetweenScanAttempts: 220,
      delayBetweenScanSuccess: 900,
    });

    this.lecteur
      .decodeFromVideoDevice(undefined, video, (resultat) => {
        if (!resultat) return;
        const texte = resultat.getText();
        // Un code lu clôt le scan : on libère la caméra tout de suite.
        this.arreter();
        this.codeLu.emit(texte);
      })
      .then((controles) => {
        this.controles = controles;
        this.demarrage.set(false);
        this.pret.set(true);
      })
      .catch((exception: unknown) => {
        console.error("Impossible d'accéder à la caméra.", exception);
        this.demarrage.set(false);
        this.pret.set(false);
        this.erreur.emit(this.messageErreur(exception));
      });
  }

  /** Message d'erreur lisible selon la cause du refus. */
  private messageErreur(exception: unknown): string {
    const nom = (exception as { name?: string })?.name ?? '';
    if (nom === 'NotAllowedError') return 'permission';
    if (nom === 'NotFoundError') return 'device';
    return 'inconnu';
  }
}
