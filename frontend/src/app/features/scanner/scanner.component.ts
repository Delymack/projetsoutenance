import { DecimalPipe, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  PLATFORM_ID,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';
import { TranslateModule } from '@ngx-translate/core';
import { BrowserMultiFormatReader, IScannerControls } from '@zxing/browser';
import { timer } from 'rxjs';

import { Vin } from '../../core/models/product.model';
import { PanierService } from '../../core/services/panier.service';
import { VinService } from '../../core/services/vin.service';
import { SkeletonComponent } from '../../shared/components/skeleton/skeleton.component';

/** États possibles du scanner. */
type EtatScan = 'repos' | 'demarrage' | 'actif' | 'analyse';

/**
 * Scanner d'étiquettes.
 *
 * Trois entrées pour le même résultat :
 *  - la caméra (ZXing, décodage continu sur le flux vidéo) ;
 *  - l'import d'une photo (ZXing, décodage ponctuel sur l'image) ;
 *  - un mode simulation qui choisit un vin du catalogue — indispensable sur un
 *    poste sans webcam, et pour les démonstrations.
 *
 * Le décodage vidéo est piloté par @zxing/browser : le composant n'instancie
 * qu'un `BrowserMultiFormatReader` et s'appuie sur ses contrôles pour arrêter
 * proprement le flux dans `ngOnDestroy`.
 */
@Component({
  selector: 'app-scanner',
  standalone: true,
  imports: [
    DecimalPipe,
    RouterLink,
    TranslateModule,
    MatButtonModule,
    MatFormFieldModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    SkeletonComponent,
  ],
  templateUrl: './scanner.component.html',
  styleUrl: './scanner.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ScannerComponent {
  private readonly vinsService = inject(VinService);
  private readonly panier = inject(PanierService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly platformId = inject(PLATFORM_ID);

  /** Flux vidéo affiché pendant le scan. */
  private readonly video = viewChild<ElementRef<HTMLVideoElement>>('video');

  /** Champ fichier caché, déclenché par le bouton « importer ». */
  private readonly fichier = viewChild<ElementRef<HTMLInputElement>>('fichier');

  private lecteur: BrowserMultiFormatReader | null = null;
  private controles: IScannerControls | null = null;
  /** Évite de traiter plusieurs codes pendant une même analyse. */
  private analyseEnCours = false;

  readonly etat = signal<EtatScan>('repos');
  readonly erreur = signal(false);
  readonly introuvable = signal(false);
  readonly codeLu = signal<string | null>(null);
  readonly vinDetecte = signal<Vin | null>(null);
  readonly vinAjoute = signal(false);
  readonly catalogue = signal<Vin[]>([]);
  /** Vin choisi dans la liste de simulation (permet de réinitialiser le sélecteur). */
  readonly simulationChoix = signal<Vin | null>(null);

  constructor() {
    this.chargerCatalogue();
  }

  /** Démarre le décodage continu sur la caméra arrière. */
  demarrer(): void {
    const video = this.video()?.nativeElement;
    if (!video || !isPlatformBrowser(this.platformId)) return;

    this.etat.set('demarrage');
    this.erreur.set(false);
    this.introuvable.set(false);
    this.codeLu.set(null);

    this.lecteur = new BrowserMultiFormatReader(undefined, {
      delayBetweenScanAttempts: 220,
      delayBetweenScanSuccess: 900,
    });

    this.lecteur
      .decodeFromVideoDevice(
        undefined,
        video,
        (resultat) => {
          if (resultat) this.resoudre(resultat.getText());
        },
      )
      .then((controles) => {
        this.controles = controles;
        this.etat.set('actif');
      })
      .catch((erreur: unknown) => {
        console.error("Impossible d'accéder à la caméra.", erreur);
        this.etat.set('repos');
        this.erreur.set(true);
      });
  }

  /** Coupe le flux caméra et libère la contrainte. */
  arreter(): void {
    this.controles?.stop();
    this.controles = null;
    this.lecteur = null;
    const video = this.video()?.nativeElement;
    if (video) video.srcObject = null;
    if (this.etat() === 'actif' || this.etat() === 'demarrage') this.etat.set('repos');
  }

  /** Ouvre le sélecteur de fichiers pour importer une photo d'étiquette. */
  importer(): void {
    this.fichier()?.nativeElement.click();
  }

  /** Décode l'image choisie par l'utilisateur. */
  async surFichier(evenement: Event): Promise<void> {
    const champ = evenement.target as HTMLInputElement;
    const image = champ.files?.[0];
    // Réinitialise le champ pour pouvoir re-sélectionner la même image ensuite.
    champ.value = '';
    if (!image) return;

    this.etat.set('analyse');
    this.erreur.set(false);
    this.introuvable.set(false);
    this.codeLu.set(null);

    const url = URL.createObjectURL(image);
    try {
      const lecteur = this.nouveauLecteur();
      const resultat = await lecteur.decodeFromImageElement(url);
      this.resoudre(resultat.getText());
    } catch (exception) {
      console.error('Lecture du code impossible.', exception);
      this.introuvable.set(true);
      this.etat.set('repos');
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  /** Simule la lecture du code-barres d'un vin du catalogue. */
  simuler(vin: Vin): void {
    this.simulationChoix.set(vin);
    this.etat.set('analyse');
    this.erreur.set(false);
    this.introuvable.set(false);
    this.codeLu.set(null);
    // Petit délai : la lecture du code doit « prendre » comme une vraie.
    timer(650)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.resoudre(vin.codeBarres));
  }

  /** Repart d'un scan vierge. */
  reinitialiser(): void {
    this.arreter();
    this.vinDetecte.set(null);
    this.simulationChoix.set(null);
    this.introuvable.set(false);
    this.codeLu.set(null);
    this.erreur.set(false);
    this.etat.set('repos');
  }

  ajouterAuPanier(vin: Vin): void {
    this.panier.ajouter(vin);
    this.vinAjoute.set(true);
    timer(1600)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.vinAjoute.set(false));
  }

  ngOnDestroy(): void {
    this.controles?.stop();
    this.controles = null;
  }

  /** Cherche le vin correspondant au code lu. */
  private resoudre(code: string): void {
    // Le flux vidéo appelle laCallback en boucle : un seul traitement à la fois.
    if (this.analyseEnCours) return;

    this.analyseEnCours = true;
    this.codeLu.set(code);
    this.introuvable.set(false);
    this.erreur.set(false);
    this.etat.set('analyse');

    this.vinsService
      .parCodeBarres(code)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (vin) => {
          this.analyseEnCours = false;
          this.etat.set('repos');
          // Un code lu clôt le scan : on rend la caméra au navigateur.
          this.arreter();

          if (vin) {
            this.vinDetecte.set(vin);
            this.codeLu.set(null);
          } else {
            this.introuvable.set(true);
          }
        },
        error: (erreur: unknown) => {
          console.error('Code-barres introuvable.', erreur);
          this.analyseEnCours = false;
          this.etat.set('repos');
          this.arreter();
          this.erreur.set(true);
        },
      });
  }

  private nouveauLecteur(): BrowserMultiFormatReader {
    return new BrowserMultiFormatReader(undefined, { delayBetweenScanSuccess: 900 });
  }

  private chargerCatalogue(): void {
    this.vinsService
      .listerTous()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (vins) => this.catalogue.set(vins),
        error: (erreur: unknown) => {
          console.error('Impossible de charger le catalogue pour la simulation.', erreur);
          this.erreur.set(true);
        },
      });
  }
}