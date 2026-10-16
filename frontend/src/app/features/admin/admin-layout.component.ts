import { CommonModule } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule } from '@ngx-translate/core';

import { AuthService } from '../../core/services/auth.service';
import { AvatarService } from '../../core/services/avatar.service';
import { AvatarComponent } from '../../shared/components/avatar/avatar.component';

interface MenuItem {
  label: string;
  icon: string;
  route?: string;
  children?: MenuItem[];
}

@Component({
  selector: 'app-admin-layout',
  standalone: true,
  imports: [
    CommonModule,
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    TranslateModule,
    MatButtonModule,
    MatIconModule,
    MatMenuModule,
    MatTooltipModule,
    AvatarComponent,
  ],
  templateUrl: './admin-layout.component.html',
  styleUrl: './admin-layout.component.scss',
})
export class AdminLayoutComponent {
  private readonly auth = inject(AuthService);
  private readonly avatar = inject(AvatarService);
  private readonly router = inject(Router);

  readonly sidebarCollapsed = signal(false);
  readonly mobileSidebarOpen = signal(false);

  readonly utilisateur = this.auth.utilisateur;

  readonly avatarService = this.avatar;
  readonly authService = this.auth;

  readonly menuItems: MenuItem[] = [
    {
      label: 'ADMIN.dashboard',
      icon: 'dashboard',
      route: '/admin/dashboard',
    },
    {
      label: 'ADMIN.commandes',
      icon: 'receipt_long',
      route: '/admin/commandes',
    },
    {
      label: 'ADMIN.clients',
      icon: 'people',
      route: '/admin/clients',
    },
    {
      label: 'ADMIN.catalogue',
      icon: 'inventory_2',
      route: '/admin/catalogue',
    },
    {
      label: 'ADMIN.rapports',
      icon: 'analytics',
      route: '/admin/rapports',
    },
    {
      label: 'ADMIN.parametres',
      icon: 'settings',
      route: '/admin/parametres',
    },
  ];

  readonly breadcrumbs = computed(() => {
    const url = this.router.url;
    const segments = url.split('/').filter(Boolean);
    const crumbs = [{ label: 'ADMIN.accueil', route: '/admin/dashboard' }];

    let currentPath = '';
    for (const segment of segments) {
      currentPath += `/${segment}`;
      const item = this.findMenuItem(this.menuItems, segment);
      if (item) {
        crumbs.push({ label: item.label, route: currentPath });
      } else {
        crumbs.push({ label: segment, route: currentPath });
      }
    }
    return crumbs;
  });

  private findMenuItem(items: MenuItem[], segment: string): MenuItem | undefined {
    for (const item of items) {
      if (item.route && item.route.endsWith(`/${segment}`)) {
        return item;
      }
      if (item.children) {
        const found = this.findMenuItem(item.children, segment);
        if (found) return found;
      }
    }
    return undefined;
  }

  toggleSidebar(): void {
    this.sidebarCollapsed.update((v) => !v);
  }

  toggleMobileSidebar(): void {
    this.mobileSidebarOpen.update((v) => !v);
  }

  closeMobileSidebar(): void {
    this.mobileSidebarOpen.set(false);
  }

  deconnexion(): void {
    this.auth.deconnexion();
  }
}