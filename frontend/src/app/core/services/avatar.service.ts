import { Injectable, computed, inject, signal } from '@angular/core';

import { AuthService } from './auth.service';

/** Photo mémorisée pour un compte : `lb.avatar.<id>` = image encodée. */
const CLE_PREFIXE = 'lb.avatar.';

/** Une photo de profil, pas une photo d'exposition : au-delà, c'est une erreur. */
const TAILLE_MAX = 5 * 1024 * 1024;

/** Côté de la vignette enregistrée. */
const COTE = 256;

/** Qualité JPEG de la vignette : invisible à cette taille, deux fois plus légère. */
const QUALITE = 0.86;

/**
 * Photo de profil.
 *
 * Deux sources, dans cet ordre : l'image choisie par l'utilisateur dans le
 * navigateur, puis celle du compte (`avatar_url` renvoyé par Django, rempli par
 * la connexion Google). Sans les deux, l'interface retombe sur les initiales.
 *
 * Le fichier choisi est recadré au carré et réduit à 256 px avant d'être
 * mémorisé : une photo d'appareil de 4 Mo ferait sauter le stockage local, et
 * une vignette de 30 ko suffit à un avatar. Le recadrage est centré, ce qui
 * garde le visage au milieu pour une photo prise au téléphone.
 */
@Injectable({ providedIn: 'root' })
export class AvatarService {
  private readonly auth = inject(AuthService);

  /** Photos locales, par identifiant de compte (le stockage n'est pas réactif). */
  private readonly locales = signal<Record<string, string>>(this.lireToutes());

  /** Photo à afficher pour le compte connecté, ou `null` pour les initiales. */
  readonly photo = computed<string | null>(() => {
    const utilisateur = this.auth.utilisateur();
    if (!utilisateur) return null;
    return this.locales()[utilisateur.id] ?? utilisateur.avatarUrl ?? null;
  });

  /** L'utilisateur a-t-il choisi lui-même cette photo ? */
  readonly personnalisee = computed(() => {
    const utilisateur = this.auth.utilisateur();
    return utilisateur ? Boolean(this.locales()[utilisateur.id]) : false;
  });

  /**
   * Enregistre la photo choisie dans le sélecteur de fichiers.
   *
   * Lève une erreur dont le message est une clé de traduction : l'écran
   * l'affiche sous la pastille, dans la langue de l'utilisateur.
   */
  async definirDepuisFichier(fichier: File): Promise<void> {
    const utilisateur = this.auth.utilisateur();
    if (!utilisateur) return;

    if (!fichier.type.startsWith('image/')) throw new Error('COMPTE.photoFormat');
    if (fichier.size > TAILLE_MAX) throw new Error('COMPTE.photoTropLourde');

    const vignette = await this.vignette(fichier);
    this.enregistrer(utilisateur.id, vignette);
  }

  /** Revient à la photo du compte (ou aux initiales). */
  retirer(): void {
    const utilisateur = this.auth.utilisateur();
    if (!utilisateur) return;

    const reste = { ...this.locales() };
    delete reste[utilisateur.id];
    this.locales.set(reste);
    try {
      localStorage.removeItem(CLE_PREFIXE + utilisateur.id);
    } catch {
      console.warn('Photo de profil non retirée (stockage indisponible).');
    }
  }

  // --- Interne ---

  private enregistrer(id: string, vignette: string): void {
    this.locales.set({ ...this.locales(), [id]: vignette });
    try {
      localStorage.setItem(CLE_PREFIXE + id, vignette);
    } catch {
      // Quota atteint : la photo reste valable pour la session en cours.
      console.warn('Photo de profil non mémorisée (stockage plein).');
    }
  }

  /** Recadre au carré, réduit, puis encode en JPEG. */
  private async vignette(fichier: File): Promise<string> {
    const image = await this.charger(fichier);
    const toile = document.createElement('canvas');
    toile.width = COTE;
    toile.height = COTE;

    const pinceau = toile.getContext('2d');
    if (!pinceau) throw new Error('COMPTE.photoIllisible');

    // Cadrage centré : on garde le plus grand carré possible au milieu.
    const cote = Math.min(image.naturalWidth, image.naturalHeight);
    const sourceX = (image.naturalWidth - cote) / 2;
    const sourceY = (image.naturalHeight - cote) / 2;
    pinceau.drawImage(image, sourceX, sourceY, cote, cote, 0, 0, COTE, COTE);

    return toile.toDataURL('image/jpeg', QUALITE);
  }

  /** Décode le fichier choisi ; l'adresse temporaire est libérée aussitôt. */
  private charger(fichier: File): Promise<HTMLImageElement> {
    return new Promise((resoudre, rejeter) => {
      const adresse = URL.createObjectURL(fichier);
      const image = new Image();
      image.onload = () => {
        URL.revokeObjectURL(adresse);
        resoudre(image);
      };
      image.onerror = () => {
        URL.revokeObjectURL(adresse);
        rejeter(new Error('COMPTE.photoIllisible'));
      };
      image.src = adresse;
    });
  }

  private lireToutes(): Record<string, string> {
    const photos: Record<string, string> = {};
    try {
      for (let index = 0; index < localStorage.length; index += 1) {
        const cle = localStorage.key(index);
        if (!cle?.startsWith(CLE_PREFIXE)) continue;
        const valeur = localStorage.getItem(cle);
        if (valeur) photos[cle.slice(CLE_PREFIXE.length)] = valeur;
      }
    } catch {
      return {};
    }
    return photos;
  }
}