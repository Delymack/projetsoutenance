import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { TranslateModule } from '@ngx-translate/core';

import { PanierLigne } from '../../core/models/product.model';
import { AuthService } from '../../core/services/auth.service';
import { PanierService } from '../../core/services/panier.service';
import { DecimalPipe } from '@angular/common';

@Component({
  selector: 'app-cart',
  standalone: true,
  imports: [
    DecimalPipe,
    RouterLink,
    TranslateModule,
    MatButtonModule,
    MatIconModule,
  ],
  templateUrl: './cart.component.html',
  styleUrl: './cart.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CartComponent {
  readonly panier = inject(PanierService);
  readonly auth = inject(AuthService);
  modifierQuantite(ligne: PanierLigne, delta: number): void {
    this.panier.majQuantite(ligne.vin.id, ligne.quantite + delta);
  }

  vider(): void {
    this.panier.vider();
  }

  totalLigne(ligne: PanierLigne): number {
    return this.panier.totalLigne(ligne);
  }
}
