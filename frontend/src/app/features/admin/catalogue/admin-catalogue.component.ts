import { Component } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { TranslateModule } from '@ngx-translate/core';

@Component({
  selector: 'app-admin-catalogue',
  standalone: true,
  imports: [MatCardModule, MatIconModule, TranslateModule],
  template: `
    <mat-card appearance="outlined" class="admin-placeholder-card">
      <mat-card-header>
        <mat-card-title>{{ 'ADMIN.catalogue' | translate }}</mat-card-title>
        <mat-card-subtitle>{{ 'ADMIN.catalogueDescription' | translate }}</mat-card-subtitle>
      </mat-card-header>
      <mat-card-content>
        <div class="admin-placeholder">
          <div class="admin-placeholder__icone">
            <mat-icon>inventory_2</mat-icon>
          </div>
          <p class="placeholder-text">{{ 'ADMIN.catalogueComingSoon' | translate }}</p>
        </div>
      </mat-card-content>
    </mat-card>
  `,
  styles: `
    .admin-placeholder-card {
      border: 1px solid var(--lb-border);
      border-radius: var(--lb-radius-lg);
      box-shadow: var(--lb-shadow-1);
    }

    mat-card {
      background: var(--lb-surface);
    }

    mat-card-header {
      background: color-mix(in srgb, var(--lb-primary) 6%, var(--lb-surface));
      border-bottom: 1px solid var(--lb-border);
    }

    mat-card-title {
      color: var(--lb-text);
      font-family: var(--lb-font-display);
    }

    mat-card-subtitle {
      color: var(--lb-text-muted);
    }

    .admin-placeholder {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: var(--lb-gap);
      min-height: 420px;
      text-align: center;
      padding: var(--lb-gap-lg) var(--lb-gap);
    }

    .admin-placeholder__icone {
      width: 72px;
      height: 72px;
      display: grid;
      place-items: center;
      border-radius: var(--lb-radius-lg);
      background: color-mix(in srgb, var(--lb-primary) 12%, transparent);
      color: var(--lb-primary);
      font-size: 36px;
      box-shadow: var(--lb-shadow-1);
    }

    .placeholder-text {
      margin: 0;
      color: var(--lb-text-muted);
      font-size: 0.95rem;
      line-height: 1.5;
    }
`,
})
export class AdminCatalogueComponent {}
