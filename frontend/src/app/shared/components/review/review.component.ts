import { DatePipe, DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, effect, inject, input, signal, untracked } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule } from '@ngx-translate/core';

import { AVIS_PAR_PAGE, AvisService } from '../../../core/services/avis.service';

/** Longueur minimale d'un commentaire : au-delà, c'est une conversation. */
const MIN_COMMENTAIRE = 10;

/**
 * Avis clients.
 *
 * Le composant regroupe tout ce qui concerne l'avis d'un vin :
 *  - synthèse : moyenne, nombre d'avis, répartition par note ;
 *  - formulaire de dépôt (reactive form typé) ;
 *  - liste paginée avec « j'aime ».
 *
 * Il ne possède aucun état : la source de vérité est `AvisService`, ce qui permet
 * à d'autres pages (fiche vin, catalogue, comparateur) d'afficher les mêmes avis
 * sans dupliquer la logique de moyenne ni de pagination.
 */
@Component({
  selector: 'app-review',
  standalone: true,
  imports: [
    DatePipe,
    DecimalPipe,
    ReactiveFormsModule,
    TranslateModule,
    MatButtonModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatTooltipModule,
  ],
  templateUrl: './review.component.html',
  styleUrl: './review.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ReviewComponent {
  /** Vin dont les avis sont affichés. */
  readonly vinId = input.required<string>();

  /** Active (ou masque) le formulaire de dépôt d'avis. */
  readonly formulaireActif = input<boolean>(true);

  private readonly avisService = inject(AvisService);

  /** Raccourcis vers les signaux du service, pour le template. */
  readonly avis = this.avisService.avis;
  readonly avisPage = this.avisService.avisPage;
  readonly moyenne = this.avisService.moyenne;
  readonly repartition = this.avisService.repartition;
  readonly pagination = this.avisService.pagination;
  readonly pagePrecedente = this.avisService.pagePrecedente;
  readonly pageSuivante = this.avisService.pageSuivante;
  readonly chargement = this.avisService.chargement;
  readonly avisParPage = AVIS_PAR_PAGE;

  /** Formulaire de dépôt, typé et non nullable. */
  readonly formulaire = new FormGroup({
    auteur: new FormControl('', {
      nonNullable: true,
      validators: [Validators.required, Validators.minLength(2), Validators.maxLength(48)],
    }),
    note: new FormControl(5, {
      nonNullable: true,
      validators: [Validators.required, Validators.min(1), Validators.max(5)],
    }),
    commentaire: new FormControl('', {
      nonNullable: true,
      validators: [Validators.required, Validators.minLength(MIN_COMMENTAIRE), Validators.maxLength(400)],
    }),
  });

  /** Étiquettes des étoiles du formulaire (1 à 5). */
  readonly etoiles = [1, 2, 3, 4, 5];

  constructor() {
    // Le service ne connaît pas encore le vin consulté : on le déclenche dès
    // que l'identifiant arrive (et à chaque changement de fiche). `charger()`
    // écrit dans des signaux, ce qu'`effect` interdit par défaut ; l'écriture a
    // lieu dans un `untracked` pour rester hors de la dépendance du suivi.
    effect(() => {
      const vinId = this.vinId();
      untracked(() => this.avisService.charger(vinId));
    });
  }

  /** Confirmation d'envoi, masquée dès que l'utilisateur retape. */
  readonly envoye = signal(false);

  /** Message d'erreur du champ, traduit et prioritaire. */
  messageErreur(champ: 'auteur' | 'commentaire'): string {
    const controle = this.formulaire.controls[champ];
    if (!controle.errors || (!controle.touched && !controle.dirty)) return '';

    if (controle.hasError('required')) return 'AVIS.erreurs.requis';
    if (controle.hasError('minlength')) {
      return champ === 'auteur' ? 'AVIS.erreurs.auteurCourt' : 'AVIS.erreurs.commentaireCourt';
    }
    return 'AVIS.erreurs.tropLong';
  }

  /** Change la note sélectionnée. */
  noter(note: number): void {
    this.formulaire.controls.note.setValue(note);
    this.formulaire.controls.note.markAsDirty();
    this.envoye.set(false);
  }

  /** Publie l'avis. */
  publier(): void {
    if (this.formulaire.invalid) {
      this.formulaire.markAllAsTouched();
      return;
    }

    const valeur = this.formulaire.getRawValue();
    this.avisService.ajouter({
      vinId: this.vinId(),
      auteur: valeur.auteur.trim(),
      note: valeur.note,
      commentaire: valeur.commentaire.trim(),
    });

    this.formulaire.reset({ auteur: '', note: 5, commentaire: '' });
    this.formulaire.markAsPristine();
    this.formulaire.markAsUntouched();
    this.envoye.set(true);
  }

  /** Navigue dans la pagination. */
  suivant(): void {
    this.avisService.suivant();
  }

  precedent(): void {
    this.avisService.precedent();
  }

  /** Ajoute un « j'aime ». */
  aimer(avisId: string): void {
    this.avisService.aimer(avisId);
  }
}