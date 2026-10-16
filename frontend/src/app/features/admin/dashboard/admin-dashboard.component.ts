import { CommonModule } from '@angular/common';
import { Component, computed, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';
import { TranslateModule } from '@ngx-translate/core';

import { CommandesService } from '../../../core/services/commandes.service';

@Component({
  selector: 'app-admin-dashboard',
  standalone: true,
  imports: [CommonModule, RouterLink, TranslateModule, MatCardModule, MatButtonModule, MatIconModule, MatTooltipModule],
  templateUrl: './admin-dashboard.component.html',
  styleUrl: './admin-dashboard.component.scss',
})
export class AdminDashboardComponent {
  private readonly commandes = inject(CommandesService);

  readonly stats = computed(() => ({
    commandesEnAttente: this.commandes.commandes().filter((c) => c.validationStatut === 'A_VALIDER').length,
    commandesTotal: this.commandes.commandes().length,
    clientsTotal: 0,
    chiffreAffaires: this.commandes.commandes().reduce((sum, c) => sum + this.commandes.total(c), 0),
  }));

  readonly recentCommands = computed(() =>
    this.commandes.commandes().slice(0, 5)
  );

  total(cmd: any): number {
    return this.commandes.total(cmd);
  }
}