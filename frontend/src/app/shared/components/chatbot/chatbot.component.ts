import { DatePipe, DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, ElementRef, effect, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatTooltipModule } from '@angular/material/tooltip';
import { RouterLink } from '@angular/router';
import { TranslateModule } from '@ngx-translate/core';
import { Subscription, fromEvent } from 'rxjs';

import { ChatbotService } from '../../../core/services/chatbot.service';
import { LangueService } from '../../../core/services/langue.service';
import { NotificationService } from '../../../core/services/notification.service';
import { VinService } from '../../../core/services/vin.service';
import { Vin } from '../../../core/models/product.model';

/**
 * Chatbot flottant.
 *
 * Composant « tout-en-un » : bulle de lancement, panneau de conversation,
 * suggestions de relance et formulaire de contact d'un conseiller. Il est monté
 * une seule fois dans `AppComponent`, hors écran client.
 *
 * Deux détails d'implémentation méritent d'être signalés en soutenance :
 *  - le défilement vers le dernier message est fait **après** la mise à jour du
 *    DOM (`afterNextRender`), sinon la zone de conversation reste en haut ;
 *  - la fermeture au clic extérieur utilise un écouteur posé à l'ouverture et
 *    retiré à la fermeture : pas de fuite de mémoire sur une page à cycle de vie long.
 */
@Component({
  selector: 'app-chatbot',
  standalone: true,
  imports: [
    DatePipe,
    DecimalPipe,
    RouterLink,
    ReactiveFormsModule,
    TranslateModule,
    MatButtonModule,
    MatIconModule,
    MatFormFieldModule,
    MatInputModule,
    MatTooltipModule,
  ],
  templateUrl: './chatbot.component.html',
  styleUrl: './chatbot.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ChatbotComponent {
  private readonly chatbotService = inject(ChatbotService);
  private readonly langue = inject(LangueService);
  private readonly notification = inject(NotificationService);
  private readonly vins = inject(VinService);

  /** Messages de la conversation (source de vérité : `ChatbotService`). */
  readonly messages = this.chatbotService.messages;
  readonly redacte = this.chatbotService.redacte;

  /** Le panneau est-il ouvert ? */
  readonly ouvert = signal(false);

  /** Le formulaire « Parler à un conseiller » est-il affiché ? */
  readonly formulaireOuvert = signal(false);

  /** Champ de saisie du message (une seule ligne : le robot ne lit pas les paragraphes). */
  readonly formulaire = new FormControl('', {
    nonNullable: true,
    validators: [Validators.required, Validators.minLength(2), Validators.maxLength(300)],
  });

  /** Formulaire de prise de contact avec un conseiller. */
  readonly conseillerForm = new FormGroup({
    nom: new FormControl('', {
      nonNullable: true,
      validators: [Validators.required, Validators.maxLength(60)],
    }),
    email: new FormControl('', {
      nonNullable: true,
      validators: [Validators.required, Validators.email],
    }),
    message: new FormControl('', {
      nonNullable: true,
      validators: [Validators.required, Validators.minLength(10), Validators.maxLength(600)],
    }),
  });

  /** Vins proposés en réponse à « quoi choisir ? » (liens sous la réponse du robot). */
  readonly suggestionsVins = signal<Vin[]>([]);

  private readonly zone = viewChild<ElementRef<HTMLDivElement>>('zone');

  constructor() {
    // Le défilement automatique suit le dernier message, qu'il vienne de
    // l'utilisateur ou du robot. `effect` est utilisé plutôt qu'un abonnement :
    // `messages` est un signal, il n'a donc pas besoin d'être converti en flux.
    effect(() => {
      this.messages();
      queueMicrotask(() => {
        const element = this.zone()?.nativeElement;
        if (element) element.scrollTop = element.scrollHeight;
      });
    });
  }

  /** Écouteur de clic extérieur, actif seulement tant que le panneau est ouvert. */
  private clicExterieur: Subscription | null = null;

  /** Ouvre / ferme le panneau. */
  basculer(): void {
    if (this.ouvert()) {
      this.fermer();
      return;
    }

    this.ouvert.set(true);
    this.ecouterClicExterieur();
  }

  /** Referme le panneau et libère l'écouteur de clic extérieur. */
  fermer(): void {
    this.ouvert.set(false);
    this.formulaireOuvert.set(false);
    this.clicExterieur?.unsubscribe();
    this.clicExterieur = null;
  }

  /** Envoie le message saisi. */
  envoyer(): void {
    const texte = this.formulaire.value.trim();
    if (!texte) return;

    this.chatbotService.envoyer(texte);
    this.formulaire.setValue('');

    // « quoi choisir » : on propose trois vins réels du catalogue.
    if (/chois|conseil|recommand|profil|sommelier/i.test(texte)) {
      this.vins.lister({ enStock: true, tri: 'note' }).subscribe((vins) => {
        this.suggestionsVins.set(vins.slice(0, 3));
      });
    } else {
      this.suggestionsVins.set([]);
    }
  }

  /** Envoie une suggestion affichée sous le dernier message du robot. */
  envoyerSuggestion(cle: string): void {
    this.chatbotService.envoyer(this.langue.t(cle));
  }

  /** Ouvre le formulaire de contact avec un conseiller. */
  ouvrirFormulaire(): void {
    this.formulaireOuvert.set(true);
  }

  /** Envoie la demande au conseiller (simulation : aucun backend requis). */
  async envoyerDemande(): Promise<void> {
    if (this.conseillerForm.invalid) {
      this.conseillerForm.markAllAsTouched();
      return;
    }

    const valeur = this.conseillerForm.getRawValue();
    // Petit délai : la requête réseau (si le backend est branché) prendrait du
    // temps, l'interface ne doit pas clignoter.
    await new Promise((resolve) => setTimeout(resolve, 700));

    this.chatbotService.envoyerDemande({
      nom: valeur.nom.trim(),
      email: valeur.email.trim(),
      message: valeur.message.trim(),
    });
    this.conseillerForm.reset();
    this.formulaireOuvert.set(false);

    // Si les notifications sont accordées, le client est prévenu par ailleurs.
    this.notification.notifier(
      'commande',
      this.langue.t('CHATBOT.conseillerForm.succesTitre'),
      this.langue.t('CHATBOT.conseillerForm.succesDetail'),
      '/historique',
    );
  }

  /**
   * Traduit une clé i18n : les messages du robot sont stockés sous forme de clés,
   * la traduction se fait au moment du rendu (un changement de langue se répercute
   * donc aussi sur les messages déjà échangés).
   */
  texte(cle: string): string {
    return this.chatbotService.traduire(cle);
  }

  /**
   * Message d'erreur de la saisie : le robot n'a aucun intérêt à recevoir un
   * message vide, on le signale donc explicitement.
   */
  erreurConversation(): string {
    if (!this.formulaire.errors || (!this.formulaire.touched && !this.formulaire.dirty)) return '';
    return 'CHATBOT.erreurs.messageCourt';
  }

  /**
   * Referme le panneau quand on clique ailleurs.
   * L'écouteur est posé à l'ouverture et retiré à la fermeture : le laisser en
   * place ferait s'empiler une subscription par ouverture.
   */
  private ecouterClicExterieur(): void {
    this.clicExterieur?.unsubscribe();
    this.clicExterieur = fromEvent<MouseEvent>(document, 'click').subscribe((event) => {
      const hote = document.querySelector('app-chatbot');
      // Un clic à l'intérieur du panneau (message, bouton) ne doit pas le fermer.
      if (!event.target || (hote && hote.contains(event.target as Node))) return;
      this.fermer();
    });
  }
}