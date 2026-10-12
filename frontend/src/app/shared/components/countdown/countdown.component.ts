import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { TranslateModule } from '@ngx-translate/core';
import { interval } from 'rxjs';

interface Rebours {
  jours: number;
  heures: number;
  minutes: number;
  secondes: number;
  termine: boolean;
}

/**
 * Compte à rebours réutilisable.
 *
 * Affiche jours / heures / minutes / secondes restants.
 * Ajoute la classe `.lb-pulse` quand il reste moins de 1 heure.
 */
@Component({
  selector: 'app-countdown',
  standalone: true,
  imports: [DecimalPipe, TranslateModule],
  templateUrl: './countdown.component.html',
  styleUrl: './countdown.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CountdownComponent {
  private readonly destroyRef = inject(DestroyRef);

  /** Date de fin (ISO string ou Date). */
  readonly fin = input.required<string | Date>();

  /** Horloge de rafraichissement, incrémentee chaque seconde. */
  private readonly maintenant = signal(Date.now());

  readonly rebours = computed<Rebours>(() => this.calculer(this.fin(), this.maintenant()));

  readonly moinsDuneHeure = computed(() => !this.rebours().termine && this.rebours().jours === 0 && this.rebours().heures < 1);

  constructor() {
    interval(1000)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        this.maintenant.set(Date.now());
      });
  }

  private calculer(fin: string | Date, instant: number): Rebours {
    const dateFin = new Date(fin);
    const delta = dateFin.getTime() - instant;
    if (delta <= 0) {
      return { jours: 0, heures: 0, minutes: 0, secondes: 0, termine: true };
    }
    const totalSecondes = Math.floor(delta / 1000);
    const jours = Math.floor(totalSecondes / 86400);
    const heures = Math.floor((totalSecondes % 86400) / 3600);
    const minutes = Math.floor((totalSecondes % 3600) / 60);
    const secondes = totalSecondes % 60;
    return { jours, heures, minutes, secondes, termine: false };
  }
}
