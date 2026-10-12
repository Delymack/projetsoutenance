import { Component } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { TranslateModule } from '@ngx-translate/core';

@Component({
  selector: 'app-admin-clients',
  standalone: true,
  imports: [MatCardModule, TranslateModule],
  template: `
    <mat-card appearance="outlined">
      <mat-card-header>
        <mat-card-title>{{ 'ADMIN.clients' | translate }}</mat-card-title>
        <mat-card-subtitle>{{ 'ADMIN.clientsDescription' | translate }}</mat-card-subtitle>
      </mat-card-header>
      <mat-card-content>
        <p class="placeholder-text">{{ 'ADMIN.clientsComingSoon' | translate }}</p>
      </mat-card-content>
    </mat-card>
  `,
  styles: `
    .placeholder-text {
      margin: 0;
      color: var(--text-muted);
      text-align: center;
      padding: 48px 0;
    }
  `,
})
export class AdminClientsComponent {}