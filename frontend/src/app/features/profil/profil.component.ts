import { DatePipe, DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { DestroyRef } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink, ActivatedRoute } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule } from '@ngx-translate/core';
import { catchError, of } from 'rxjs';

import { AuthService } from '../../core/services/auth.service';
import { CommandesService } from '../../core/services/commandes.service';
import { FideliteService } from '../../core/services/fidelite.service';
import { LangueService } from '../../core/services/langue.service';
import { PanierService } from '../../core/services/panier.service';
import { AvatarService } from '../../core/services/avatar.service';
import { AdresseProfil, ProfilService } from '../../core/services/profil.service';
import { AvatarComponent } from '../../shared/components/avatar/avatar.component';

/** onglets du profil client (simplifiés à 4 essentiels). */
type SectionProfil = 'commandes' | 'adresses' | 'fidelite' | 'securite';

/** espace client. */
@Component({
  selector: 'app-profil',
  standalone: true,
  imports: [
    DatePipe,
    DecimalPipe,
    ReactiveFormsModule,
    RouterLink,
    TranslateModule,
    MatButtonModule,
    MatButtonToggleModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatProgressBarModule,
    MatTooltipModule,
    AvatarComponent,
  ],
  templateUrl: './profil.component.html',
  styleUrl: './profil.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProfilComponent {
  private readonly fb = inject(FormBuilder).nonNullable;

  readonly auth = inject(AuthService);
  readonly commandes = inject(CommandesService);
  readonly fidelite = inject(FideliteService);
  readonly panier = inject(PanierService);
  readonly profil = inject(ProfilService);
  readonly avatar = inject(AvatarService);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  private readonly langue = inject(LangueService);

  readonly section = signal<SectionProfil>('commandes');
  readonly commandeOuverte = signal<string | null>(null);
  readonly adresseEnEdition = signal<string | null>(null);
  readonly succes = signal<string | null>(null);

  readonly utilisateur = this.auth.utilisateur;

  readonly onglets: { cle: SectionProfil; icone: string; libelle: string }[] = [
    { cle: 'commandes', icone: 'receipt_long', libelle: 'PROFIL.commandes' },
    { cle: 'adresses', icone: 'home', libelle: 'PROFIL.adresses' },
    { cle: 'fidelite', icone: 'workspace_premium', libelle: 'PROFIL.fidelite' },
    { cle: 'securite', icone: 'shield', libelle: 'PROFIL.securite' },
  ];

  readonly nbCommandes = computed(() => this.commandes.commandes().length);

  readonly adresseForm = this.fb.group({
    libelle: ['Domicile', Validators.required],
    destinataire: ['', Validators.required],
    telephone: ['', Validators.required],
    ligne: ['', Validators.required],
    ville: ['', Validators.required],
    notes: [''],
  });

  readonly identityForm = this.fb.group({
    telephone: [this.profil.telephone()],
    ville: [this.profil.ville()],
  });

  ouvrir(cle: SectionProfil): void {
    this.section.set(cle);
  }

  constructor() {
    // Lien direct depuis le panneau de compte (`/profil?section=adresses`) :
    // la section demandée s'ouvre, au lieu de renvoyer l'utilisateur sur
    // « Commandes » où il doit la retrouver lui-même.
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((params) => {
      const demandee = params.get('section') as SectionProfil | null;
      if (demandee && this.onglets.some((onglet) => onglet.cle === demandee)) {
        this.ouvrir(demandee);
      }
    });
  }

  ouvrirAdresse(adresse: AdresseProfil): void {
    this.adresseEnEdition.set(adresse.id);
    this.adresseForm.setValue({
      libelle: adresse.libelle,
      destinataire: adresse.destinataire,
      telephone: adresse.telephone,
      ligne: adresse.ligne,
      ville: adresse.ville,
      notes: adresse.notes ?? '',
    });
  }

  nouvelleAdresse(): void {
    this.adresseEnEdition.set('nouvelle');
    this.adresseForm.reset({ libelle: 'Domicile', destinataire: '', telephone: '', ligne: '', ville: '', notes: '' });
  }

  enregistrerAdresse(): void {
    if (this.adresseForm.invalid) {
      this.adresseForm.markAllAsTouched();
      return;
    }
    const valeurs = this.adresseForm.getRawValue();
    const enEdition = this.adresseEnEdition();
    if (enEdition && enEdition !== 'nouvelle') {
      this.profil.modifierAdresse(enEdition, valeurs);
    } else {
      this.profil.ajouterAdresse({ ...valeurs, parDefaut: this.profil.adresses().length === 0 });
    }
    this.adresseEnEdition.set(null);
    this.succes.set('PROFIL.adresseEnregistree');
  }

  supprimerAdresse(id: string): void {
    this.profil.retirerAdresse(id);
    this.adresseEnEdition.set(null);
  }

  enregistrerIdentite(): void {
    const { telephone, ville } = this.identityForm.getRawValue();
    this.profil.majTelephone(telephone);
    this.profil.majVille(ville);
    this.succes.set('PROFIL.profilMisAJour');
  }
}