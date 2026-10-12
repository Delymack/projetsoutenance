import { ChangeDetectionStrategy, Component, computed, inject, input, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule } from '@ngx-translate/core';

import { LangueService } from '../../../core/services/langue.service';

/** Réseau de partage proposé, avec son libellé et son icône. */
export interface ReseauPartage {
  /** Identifiant technique du réseau. */
  id: 'facebook' | 'whatsapp' | 'telegram' | 'email';
  /** Icône Material. */
  icone: string;
  /** Clé i18n du libellé accessible. */
  cle: string;
}

/** Réseaux proposés, dans l'ordre d'affichage. */
export const RESEAUX: ReseauPartage[] = [
  { id: 'facebook', icone: 'facebook', cle: 'PARTAGE.facebook' },
  { id: 'whatsapp', icone: 'chat', cle: 'PARTAGE.whatsapp' },
  { id: 'telegram', icone: 'send', cle: 'PARTAGE.telegram' },
  { id: 'email', icone: 'mail', cle: 'PARTAGE.email' },
];

/**
 * Partage social.
 *
 * Deux priorités : ne jamais casser la page, et rester utilisable quand les
 * fenêtres tierces sont bloquées (CSP, bloqueur de pop-ups).
 *  - le lien de partage est **toujours** rendu dans le `href` de chaque bouton ;
 *    sans JavaScript (ou si `window.open` est refusé), le clic sur le bouton
 *    émet un `RouterLink`-free HTML : le navigateur suit alors le lien ;
 *  - le bouton « lien » utilise l'API `navigator.share` sur mobile, avec repli
 *    sur la copie dans le presse-papiers.
 */
@Component({
  selector: 'app-share',
  standalone: true,
  imports: [TranslateModule, MatButtonModule, MatIconModule, MatTooltipModule],
  templateUrl: './share.component.html',
  styleUrl: './share.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ShareComponent {
  /** URL à partager (par défaut : l'URL courante). */
  readonly url = input<string>('');

  /** Titre du contenu partagé. */
  readonly titre = input<string>('');

  /** Texte d'accroche (utilisé par WhatsApp, Telegram et le partage natif). */
  readonly message = input<string>('');

  /** Affichage compact : une seule icône (fiche vin, carte produit). */
  readonly compact = input<boolean>(false);

  private readonly langue = inject(LangueService);

  /** Réseaux disponibles. */
  readonly reseaux = RESEAUX;

  /** Lien réellement partagé : l'URL fournie, ou la page courante. */
  readonly lien = computed(() => this.url() || window.location.href);

  /** Accroche : le message fourni, sinon le titre, sinon le nom du site. */
  readonly accroche = computed(
    () => this.message() || this.titre() || this.langue.t('APP.nom'),
  );

  /** Lien de partage pour un réseau donné. */
  lienReseau(reseau: ReseauPartage['id']): string {
    const lien = encodeURIComponent(this.lien());
    const texte = encodeURIComponent(this.accroche());
    const titre = encodeURIComponent(this.titre() || this.langue.t('APP.nom'));

    switch (reseau) {
      case 'facebook':
        return `https://www.facebook.com/sharer/sharer.php?u=${lien}&quote=${texte}`;
      case 'whatsapp':
        return `https://wa.me/?text=${texte}%20${lien}`;
      case 'telegram':
        return `https://t.me/share/url?url=${lien}&text=${texte}`;
      case 'email':
        return `mailto:?subject=${titre}&body=${texte}%20${lien}`;
    }
  }

  /** Confirmation « lien copié » affichée brièvement. */
  readonly copie = signal(false);

  /**
   * Copie le lien (ou invoque le partage natif si l'appareil le propose).
   * Les deux comportements partagent la même confirmation visuelle.
   */
  async partager(): Promise<void> {
    const nav = navigator as Navigator & {
      share?: (donnees: { title?: string; text?: string; url?: string }) => Promise<void>;
    };

    // Partage natif (Android, iOS, PWA installée) : ouvre la feuille système.
    if (typeof nav.share === 'function') {
      try {
        await nav.share({ title: this.titre() || undefined, text: this.accroche(), url: this.lien() });
        return;
      } catch {
        // Partage annulé par l'utilisateur : on retombe sur la copie.
      }
    }

    try {
      await navigator.clipboard.writeText(this.lien());
    } catch {
      // Contexte non sécurisé (HTTP) ou permission refusée : l'utilisateur peut
      // toujours copier l'URL depuis la barre d'adresse.
      console.warn('Copie du lien refusée :', this.langue.t('PARTAGE.copieEchouee'));
      return;
    }

    this.copie.set(true);
    setTimeout(() => this.copie.set(false), 1800);
  }
}