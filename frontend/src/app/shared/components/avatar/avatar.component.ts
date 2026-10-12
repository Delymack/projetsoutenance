import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/**
 * Pastille d'identité : la photo du compte quand il y en a une, les initiales
 * sinon.
 *
 * Un seul composant pour les trois endroits qui montrent l'utilisateur — la
 * barre de navigation, le panneau de compte et le bandeau du profil : changer
 * de photo se voit partout, et l'image est toujours cadrée de la même façon.
 */
@Component({
  selector: 'app-avatar',
  standalone: true,
  templateUrl: './avatar.component.html',
  styleUrl: './avatar.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AvatarComponent {
  /** Nom affiché : sert à calculer les initiales de repli. */
  readonly nom = input('');

  /** Photo (adresse ou image encodée). Vide → initiales. */
  readonly photo = input<string | null>(null);

  /** Diamètre, en pixels. */
  readonly taille = input(36);

  /** Initiales de repli : deux premières lettres des deux premiers mots. */
  readonly initiales = computed(
    () =>
      this.nom()
        .split(' ')
        .filter(Boolean)
        .slice(0, 2)
        .map((mot) => mot[0]?.toUpperCase() ?? '')
        .join('') || '?',
  );

  /** La taille des initiales suit le diamètre pour rester lisible. */
  readonly tailleTexte = computed(() => Math.round(this.taille() * 0.36));
}