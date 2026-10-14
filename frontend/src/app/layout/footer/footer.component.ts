import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { TranslateModule } from '@ngx-translate/core';

/**
 * Pied de page du site public.
 *
 * Le composant ne conserve que l'année utilisée dans le copyright.
 */
@Component({
  selector: 'app-footer',
  standalone: true,
  imports: [RouterLink, MatIconModule, TranslateModule],
  templateUrl: './footer.component.html',
  styleUrl: './footer.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FooterComponent {
  readonly annee = new Date().getFullYear();
}
