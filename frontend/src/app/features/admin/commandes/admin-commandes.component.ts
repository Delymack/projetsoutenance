import { CommonModule } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CdkDragDrop, DragDropModule, moveItemInArray, transferArrayItem } from '@angular/cdk/drag-drop';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatMenuModule } from '@angular/material/menu';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule } from '@ngx-translate/core';

import { CommandesService } from '../../../core/services/commandes.service';
import { ReservationsService, ReservationDetail } from '../../../core/services/reservations.service';

interface CommandeAdmin {
  reference: string;
  date: string;
  clientNom: string;
  clientEmail: string;
  total: number;
  statut: 'A_VALIDER' | 'VALIDEE' | 'ENCAISSEE' | 'EXPEDIEE' | 'LIVREE' | 'ANNULEE' | 'REFUSEE';
  lignes: { vinId: string; quantite: number; prixUnitaire: number; remisePct: number }[];
  source: 'reservation' | 'vente';
  id?: number;
}

@Component({
  selector: 'app-admin-commandes',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    DragDropModule,
    TranslateModule,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatChipsModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatMenuModule,
    MatProgressBarModule,
    MatSnackBarModule,
    MatTooltipModule,
  ],
  templateUrl: './admin-commandes.component.html',
  styleUrl: './admin-commandes.component.scss',
})
export class AdminCommandesComponent {
  private readonly commandes = inject(CommandesService);
  private readonly reservations = inject(ReservationsService);
  private readonly snackBar = inject(MatSnackBar);

  readonly filtreStatut = signal<'tous' | 'A_VALIDER' | 'VALIDEE' | 'ENCAISSEE' | 'EXPEDIEE' | 'LIVREE' | 'ANNULEE' | 'REFUSEE'>('tous');
  readonly recherche = signal('');

  readonly statuts = [
    'A_VALIDER',
    'VALIDEE',
    'ENCAISSEE',
    'EXPEDIEE',
    'LIVREE',
    'ANNULEE',
    'REFUSEE',
  ] as const;

  readonly commandesFiltrees = computed(() => {
    const filtre = this.filtreStatut();
    const recherche = this.recherche().toLowerCase();
    return this.toutesCommandes().filter((cmd) => {
      const matchStatut = filtre === 'tous' || cmd.statut === filtre;
      const matchRecherche =
        !recherche ||
        cmd.reference.toLowerCase().includes(recherche) ||
        cmd.clientNom.toLowerCase().includes(recherche) ||
        cmd.clientEmail.toLowerCase().includes(recherche);
      return matchStatut && matchRecherche;
    });
  });

  readonly commandesParStatut = computed(() => {
    const groupes: Record<string, CommandeAdmin[]> = {};
    for (const statut of this.statuts) {
      groupes[statut] = this.commandesFiltrees().filter((c) => c.statut === statut);
    }
    return groupes;
  });

  private toutesCommandes = computed((): CommandeAdmin[] => {
    const locales = this.commandes.commandes();
    const result: CommandeAdmin[] = [];

    for (const cmd of locales) {
      if (cmd.reference.startsWith('RES-')) {
        // Extraire l'ID numérique de la référence (ex: "RES-123" -> 123)
        const id = Number(cmd.reference.split('-')[1]);
        result.push({
          reference: cmd.reference,
          date: cmd.date,
          clientNom: 'Client site',
          clientEmail: 'client@lazani-betsileo.mg',
          total: this.commandes.total(cmd),
          statut: this.mapStatutReservation(cmd.statut, cmd.validationStatut),
          lignes: cmd.lignes,
          source: 'reservation',
          id: Number.isSafeInteger(id) ? id : undefined,
        });
      } else {
        result.push({
          reference: cmd.reference,
          date: cmd.date,
          clientNom: 'Client caisse',
          clientEmail: 'caisse@lazani-betsileo.mg',
          total: this.commandes.total(cmd),
          statut: this.mapStatutVente(cmd.statut),
          lignes: cmd.lignes,
          source: 'vente',
        });
      }
    }
    return result.sort((a, b) => b.date.localeCompare(a.date));
  });

  private mapStatutReservation(statut: string, validationStatut?: string): CommandeAdmin['statut'] {
    if (validationStatut === 'A_VALIDER') return 'A_VALIDER';
    if (validationStatut === 'VALIDEE') return 'VALIDEE';
    if (validationStatut === 'REFUSEE') return 'REFUSEE';
    switch (statut) {
      case 'enPreparation':
        return 'ENCAISSEE';
      case 'livree':
        return 'LIVREE';
      case 'annulee':
        return 'ANNULEE';
      default:
        return 'A_VALIDER';
    }
  }

  private mapStatutVente(statut: string): CommandeAdmin['statut'] {
    switch (statut) {
      case 'livree':
        return 'LIVREE';
      case 'enPreparation':
        return 'ENCAISSEE';
      case 'annulee':
        return 'ANNULEE';
      default:
        return 'ENCAISSEE';
    }
  }

  compter(statut: string): number {
    return this.commandesParStatut()[statut]?.length ?? 0;
  }

  async validerCommande(cmd: CommandeAdmin): Promise<void> {
    if (cmd.source === 'reservation' && cmd.id) {
      try {
        await this.reservations.valider(cmd.id);
        this.snackBar.open((await this.translate('ADMIN.commandeValidee')), 'OK', { duration: 3000 });
      } catch (error) {
        this.snackBar.open((error as Error).message, 'OK', { duration: 5000 });
      }
    }
  }

  async refuserCommande(cmd: CommandeAdmin): Promise<void> {
    if (cmd.source === 'reservation' && cmd.id) {
      try {
        await this.reservations.refuser(cmd.id, 'Refusé par l\'administrateur');
        this.snackBar.open((await this.translate('ADMIN.commandeRefusee')), 'OK', { duration: 3000 });
      } catch (error) {
        this.snackBar.open((error as Error).message, 'OK', { duration: 5000 });
      }
    }
  }

  async encaisserCommande(cmd: CommandeAdmin): Promise<void> {
    if (cmd.source === 'reservation' && cmd.id) {
      try {
        // TODO: Implémenter l'encaissement via l'API
        this.snackBar.open('Fonctionnalité à venir', 'OK', { duration: 3000 });
      } catch (error) {
        this.snackBar.open((error as Error).message, 'OK', { duration: 5000 });
      }
    }
  }

  expeditionCommande(cmd: CommandeAdmin): void {
    // TODO: Implémenter expédition
    this.snackBar.open('Fonctionnalité à venir', 'OK', { duration: 3000 });
  }

  livrerCommande(cmd: CommandeAdmin): void {
    // TODO: Implémenter livraison
    this.snackBar.open('Fonctionnalité à venir', 'OK', { duration: 3000 });
  }

  annulerCommande(cmd: CommandeAdmin): void {
    if (cmd.source === 'reservation' && cmd.id) {
      // TODO: Implémenter annulation
      this.snackBar.open('Fonctionnalité à venir', 'OK', { duration: 3000 });
    }
  }

  getActionsDisponibles(cmd: CommandeAdmin): string[] {
    const actions: string[] = [];
    switch (cmd.statut) {
      case 'A_VALIDER':
        actions.push('valider', 'refuser');
        break;
      case 'VALIDEE':
        actions.push('encaisser');
        break;
      case 'ENCAISSEE':
        actions.push('expedier');
        break;
      case 'EXPEDIEE':
        actions.push('livrer');
        break;
      default:
        break;
    }
    return actions;
  }

  onDrop(event: CdkDragDrop<CommandeAdmin[]>, nouveauStatut: string): void {
    if (event.previousContainer === event.container) {
      moveItemInArray(event.container.data, event.previousIndex, event.currentIndex);
    } else {
      transferArrayItem(
        event.previousContainer.data,
        event.container.data,
        event.previousIndex,
        event.currentIndex,
      );
      const cmd = event.container.data[event.currentIndex];
    }
  }

  onRechercheChange(event: Event): void {
    const target = event.target as HTMLInputElement;
    this.recherche.set(target.value);
  }

  onFiltreChange(value: string): void {
    this.filtreStatut.set(value as any);
  }

  private async translate(key: string): Promise<string> {
    // Simple translation fallback
    const translations: Record<string, string> = {
      'ADMIN.commandeValidee': 'Commande validée avec succès',
      'ADMIN.commandeRefusee': 'Commande refusée',
      'ADMIN.commandeEncaisssee': 'Commande encaissée avec succès',
    };
    return translations[key] ?? key;
  }
}