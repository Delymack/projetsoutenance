// frontend/src/app/features/auth/inscription.component.ts
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  OnDestroy,
  QueryList,
  ViewChildren,
  inject,
  signal,
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import { AuthService } from '../../core/services/auth.service';
import { messageErreurHttp } from '../../core/utils/erreurs-http';

/** Inscription avec vérification par code à 6 chiffres - Lazan'i Betsileo */
@Component({
  selector: 'app-inscription',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MatIconModule,
    MatProgressSpinnerModule,
  ],
  templateUrl: './inscription.component.html',
  styleUrl: './inscription.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InscriptionComponent implements OnDestroy {
  private readonly fb = inject(FormBuilder).nonNullable;
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  /** Cases de saisie du code, dans l'ordre (auto-focus / collage). */
  @ViewChildren('caseCode') private readonly casesCode!: QueryList<ElementRef<HTMLInputElement>>;

  // Références des minuteurs : on les arrête explicitement pour éviter que
  // d'anciens intervalles ne continuent après un retour à l'étape 1.
  private intervalExpiration?: ReturnType<typeof setInterval>;
  private intervalRenvoi?: ReturnType<typeof setInterval>;

  // Étape du formulaire (1: données, 2: code, 3: succès)
  readonly etape = signal(1);
  readonly enCours = signal(false);
  readonly erreur = signal<string | null>(null);
  readonly succes = signal<string | null>(null);

  // Données de l'étape 1
  readonly form = this.fb.group({
    nom: ['', [Validators.required, Validators.minLength(3)]],
    email: ['', [Validators.email]],
    telephone: ['', [Validators.pattern(/^[0-9 +]{8,15}$/)]],
    password: ['', [Validators.required, Validators.minLength(8)]],
    contact_type: ['email' as 'email' | 'sms', Validators.required],
  });

  // Code de vérification (6 chiffres)
  readonly codeForm = this.fb.group({
    code1: ['', [Validators.required, Validators.maxLength(1)]],
    code2: ['', [Validators.required, Validators.maxLength(1)]],
    code3: ['', [Validators.required, Validators.maxLength(1)]],
    code4: ['', [Validators.required, Validators.maxLength(1)]],
    code5: ['', [Validators.required, Validators.maxLength(1)]],
    code6: ['', [Validators.required, Validators.maxLength(1)]],
  });

  /** Noms des champs du code, dans l'ordre de saisie (parcourus par le template). */
  readonly champsCode = ['code1', 'code2', 'code3', 'code4', 'code5', 'code6'] as const;

  // Timer d'expiration (10 minutes)
  readonly tempsRestant = signal(600);
  readonly timerEnCours = signal(false);

  // Timer de renvoi (60 secondes)
  readonly tempsRenvoi = signal(0);
  readonly peutRenvoyer = signal(true);

  // Contact utilisé pour la vérification
  readonly contact = signal<string>('');
  readonly contactType = signal<'email' | 'sms'>('email');

  motDePasseVisible = signal(false);

  get nom() { return this.form.controls.nom; }
  get email() { return this.form.controls.email; }
  get telephone() { return this.form.controls.telephone; }
  get password() { return this.form.controls.password; }
  get contact_type() { return this.form.controls.contact_type; }

  // Accès aux champs du code
  get code1() { return this.codeForm.controls.code1; }
  get code2() { return this.codeForm.controls.code2; }
  get code3() { return this.codeForm.controls.code3; }
  get code4() { return this.codeForm.controls.code4; }
  get code5() { return this.codeForm.controls.code5; }
  get code6() { return this.codeForm.controls.code6; }

  /** Étape 1 : Envoi du code de vérification */
  async envoyerCode(): Promise<void> {
    this.erreur.set(null);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.erreur.set('Veuillez remplir tous les champs obligatoires.');
      return;
    }

    const data = this.form.getRawValue();
    
    // Validation selon le type de contact
    if (data.contact_type === 'email' && !data.email) {
      this.erreur.set('L\'email est obligatoire pour ce mode d\'envoi.');
      return;
    }
    if (data.contact_type === 'sms' && !data.telephone) {
      this.erreur.set('Le numéro de téléphone est obligatoire pour ce mode d\'envoi.');
      return;
    }

    this.enCours.set(true);
    try {
      const reponse = await this.auth.signupSendCode(data);
      this.contact.set(data.contact_type === 'email' ? data.email! : data.telephone!);
      this.contactType.set(data.contact_type);
      this.etape.set(2);
      // Le backend peut réutiliser un code déjà émis : on cale le minuteur sur
      // la durée de vie restante réelle plutôt que sur 10 min fixes.
      this.demarrerTimerExpiration(reponse.expires_in);
      this.demarrerTimerRenvoi();
      this.succes.set(reponse.message);
    } catch (e: unknown) {
      this.erreur.set(messageErreurHttp(e, 'Erreur lors de l\'envoi du code.'));
    } finally {
      this.enCours.set(false);
    }
  }

  /** Étape 2 : Vérification du code */
  async verifierCode(): Promise<void> {
    this.erreur.set(null);
    const code = Object.values(this.codeForm.getRawValue()).join('');
    
    if (code.length !== 6) {
      this.erreur.set('Veuillez entrer les 6 chiffres du code.');
      return;
    }

    this.enCours.set(true);
    try {
      await this.auth.signupVerify(this.contact(), code);
      this.arreterTimerExpiration();
      this.arreterTimerRenvoi();
      this.etape.set(3);
      this.succes.set('Inscription réussie ! Redirection vers le tableau de bord...');
      setTimeout(() => void this.router.navigate(['/']), 2000);
    } catch (e: unknown) {
      this.erreur.set(messageErreurHttp(e, 'Code incorrect ou expiré.'));
    } finally {
      this.enCours.set(false);
    }
  }

  /** Renvoyer le code */
  async renvoyerCode(): Promise<void> {
    if (!this.peutRenvoyer()) return;

    this.erreur.set(null);
    this.enCours.set(true);
    try {
      const reponse = await this.auth.resendCode(this.contact());
      this.demarrerTimerExpiration(reponse.expires_in);
      this.demarrerTimerRenvoi();
      this.succes.set('Code renvoyé avec succès.');
    } catch (e: unknown) {
      this.erreur.set(messageErreurHttp(e, 'Erreur lors du renvoi du code.'));
    } finally {
      this.enCours.set(false);
    }
  }

  /** Gestion de l'auto-focus entre les champs du code */
  onCodeInput(event: Event, index: number): void {
    const input = event.target as HTMLInputElement;

    // Ne garder que le dernier chiffre saisi (ignore lettres, espaces, etc.).
    const chiffres = input.value.replace(/\D/g, '');
    if (input.value !== chiffres) {
      input.value = chiffres;
      this.controleCode(index).setValue(chiffres.slice(-1));
    }

    // Passer au champ suivant si un chiffre est entré.
    if (chiffres && index < this.champsCode.length - 1) {
      this.focusCase(index + 1);
    }
  }

  /** Gestion des touches Retour / flèches */
  onCodeKeyDown(event: KeyboardEvent, index: number): void {
    const target = event.currentTarget as HTMLInputElement;
    const dernier = this.champsCode.length - 1;

    if (event.key === 'Backspace' && !target.value && index > 0) {
      this.focusCase(index - 1);
    } else if (event.key === 'ArrowLeft' && index > 0) {
      this.focusCase(index - 1);
    } else if (event.key === 'ArrowRight' && index < dernier) {
      this.focusCase(index + 1);
    }
  }

  /** Colle un code entier (ex. reçu par e-mail) dans les 6 cases. */
  onCodePaste(event: ClipboardEvent): void {
    const chiffres = (event.clipboardData?.getData('text') ?? '')
      .replace(/\D/g, '')
      .slice(0, this.champsCode.length);
    if (!chiffres) return;

    event.preventDefault();
    this.champsCode.forEach((champ, i) => {
      this.codeForm.controls[champ].setValue(chiffres[i] ?? '');
    });
    this.focusCase(Math.min(chiffres.length, this.champsCode.length - 1));
  }

  private controleCode(index: number) {
    return this.codeForm.controls[`code${index + 1}` as keyof typeof this.codeForm.controls];
  }

  /** Donne le focus (et sélectionne) la case demandée. */
  private focusCase(index: number): void {
    const caseCode = this.casesCode?.get(index)?.nativeElement;
    caseCode?.focus();
    caseCode?.select();
  }

  /** Démarrer le timer d'expiration (durée de vie du code, 10 min par défaut) */
  private demarrerTimerExpiration(secondes = 600): void {
    this.arreterTimerExpiration();
    this.tempsRestant.set(Math.max(0, secondes));
    this.timerEnCours.set(true);

    this.intervalExpiration = setInterval(() => {
      const actuel = this.tempsRestant();
      if (actuel <= 0) {
        this.arreterTimerExpiration();
        this.timerEnCours.set(false);
        this.erreur.set('Code expiré. Veuillez en demander un nouveau.');
      } else {
        this.tempsRestant.set(actuel - 1);
      }
    }, 1000);
  }

  /** Démarrer le timer de renvoi (60 secondes) */
  private demarrerTimerRenvoi(): void {
    this.arreterTimerRenvoi();
    this.tempsRenvoi.set(60);
    this.peutRenvoyer.set(false);

    this.intervalRenvoi = setInterval(() => {
      const actuel = this.tempsRenvoi();
      if (actuel <= 0) {
        this.arreterTimerRenvoi();
        this.peutRenvoyer.set(true);
      } else {
        this.tempsRenvoi.set(actuel - 1);
      }
    }, 1000);
  }

  private arreterTimerExpiration(): void {
    if (this.intervalExpiration) {
      clearInterval(this.intervalExpiration);
      this.intervalExpiration = undefined;
    }
  }

  private arreterTimerRenvoi(): void {
    if (this.intervalRenvoi) {
      clearInterval(this.intervalRenvoi);
      this.intervalRenvoi = undefined;
    }
  }

  /** Formater le temps en MM:SS */
  formaterTemps(secondes: number): string {
    const mins = Math.floor(secondes / 60);
    const secs = secondes % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  }

  /** Retour à l'étape 1 */
  retour(): void {
    this.arreterTimerExpiration();
    this.arreterTimerRenvoi();
    this.etape.set(1);
    this.tempsRestant.set(600);
    this.tempsRenvoi.set(0);
    this.peutRenvoyer.set(true);
    this.codeForm.reset();
  }

  ngOnDestroy(): void {
    this.arreterTimerExpiration();
    this.arreterTimerRenvoi();
  }
}
