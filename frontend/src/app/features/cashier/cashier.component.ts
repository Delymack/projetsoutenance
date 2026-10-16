import { DatePipe, DecimalPipe } from '@angular/common';
import { CdkDragDrop, DragDropModule } from '@angular/cdk/drag-drop';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  HostListener,
  ViewChild,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatTooltipModule } from '@angular/material/tooltip';
import { TranslateModule } from '@ngx-translate/core';
import { catchError, debounceTime, of, startWith, switchMap } from 'rxjs';

import { PanierLigne, Vin } from '../../core/models/product.model';
import { LangueService } from '../../core/services/langue.service';
import { SonService, VarianteSon } from '../../core/services/son.service';
import { TactileService } from '../../core/services/tactile.service';
import { PanierService } from '../../core/services/panier.service';
import { SyncService } from '../../core/services/sync.service';
import { CommandesService } from '../../core/services/commandes.service';
import { VinService } from '../../core/services/vin.service';
import { LecteurCodeComponent } from '../../shared/components/lecteur-code/lecteur-code.component';
import { CustomerDisplayComponent } from './customer-display.component';

import { ModePaiementApi } from '../../core/models/vente-api.model';

/** Clé du compteur séquentiel de tickets. */
const CLE_TICKET_SEQ = 'lb.caisse.ticket.seq';

/** Clé de stockage des tickets en attente (Park & Resume). */
const CLE_PANIERS_ATTENTE = 'lb.caisse.paniers.attente';

/** Ticket de caisse suspendu. */
export interface PanierEnAttente {
  id: string;
  date: string;
  lignes: PanierLigne[];
  total: number;
  client: string;
  modePaiement: ModePaiementApi;
}

export interface OptionModePaiement {
  code: ModePaiementApi;
  libelle: string;
  icone: string;
  badge?: string;
}

interface SpeechRecognitionEventLike extends Event {
  results: {
    [index: number]: {
      [index: number]: {
        transcript: string;
      };
    };
  };
}

interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
}

type SpeechWindow = Window & {
  webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  SpeechRecognition?: new () => SpeechRecognitionLike;
};

@Component({
  selector: 'app-cashier',
  standalone: true,
  imports: [
    DatePipe,
    DecimalPipe,
    RouterLink,
    ReactiveFormsModule,
    DragDropModule,
    TranslateModule,
    MatButtonModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatTooltipModule,
    LecteurCodeComponent,
    CustomerDisplayComponent,
  ],
  templateUrl: './cashier.component.html',
  styleUrl: './cashier.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CashierComponent {
  private readonly vinsService = inject(VinService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly langue = inject(LangueService);
  private readonly sync = inject(SyncService);
  private readonly commandes = inject(CommandesService);
  private readonly son = inject(SonService);
  private readonly tactileService = inject(TactileService);
  readonly panier = inject(PanierService);

  @ViewChild('champRecherche') champRecherche?: ElementRef<HTMLInputElement>;

  readonly recherche = new FormControl('', { nonNullable: true });
  readonly vins = signal<Vin[]>([]);
  readonly chargement = signal(true);
  readonly message = signal<string | null>(null);
  readonly paiementOk = signal(false);
  readonly ecouteVocale = signal(false);
  /** Formulaire de saisie manuelle du code-barres (repli du scan caméra). */
  readonly scanForm = new FormGroup({
    code: new FormControl('', {
      nonNullable: true,
      validators: [Validators.required, Validators.minLength(6)],
    }),
  });

  readonly scanOuvert = signal(false);
  readonly scanErreur = signal(false);
  readonly scanResultat = signal<Vin | null>(null);

 /** Son de validation (optionnel, ). */
  readonly sonActif = this.son.actif;

  /** Mode tactile : détection automatique, bascule manuelle possible. */
  readonly tactile = this.tactileService.actif;

  readonly ticketLignes = computed(() => this.panier.lignes());

  readonly modesPaiement: OptionModePaiement[] = [
    { code: 'ESPECES', libelle: 'Espèces', icone: 'payments' },
    { code: 'CARTE', libelle: 'Carte bancaire', icone: 'credit_card' },
  ];

  /** Mode de règlement sélectionné (défaut : espèces). */
  readonly modePaiement = signal<ModePaiementApi>('ESPECES');

  /** Client libre saisi au comptoir. */
  readonly clientNom = new FormControl('Client Comptoir', { nonNullable: true });

  /** Référence de transaction / SMS pour paiement mobile ou chèque. */
  readonly referencePaiement = new FormControl('', { nonNullable: true });

  /** Montant en espèces remis par le client (en Ariary). */
  readonly montantRecu = signal<number>(0);

  /** Coupures de billets usuelles à Madagascar (MGA). */
  readonly coupuresAriary = [5000, 10000, 20000, 50000, 100000];

  /** Rendu de monnaie calculé en direct. */
  readonly renduMonnaie = computed(() => {
    if (this.modePaiement() !== 'ESPECES') return 0;
    const total = this.panier.total();
    const recu = this.montantRecu();
    return recu >= total ? recu - total : 0;
  });

  /** Reste à percevoir si le montant reçu est insuffisant. */
  readonly resteAPayer = computed(() => {
    if (this.modePaiement() !== 'ESPECES') return 0;
    const total = this.panier.total();
    const recu = this.montantRecu();
    return recu > 0 && recu < total ? total - recu : 0;
  });

  /** Tickets mis en attente pour encaisser le client suivant. */
  readonly paniersEnAttente = signal<PanierEnAttente[]>(this.lirePaniersEnAttente());
  readonly nbPaniersEnAttente = computed(() => this.paniersEnAttente().length);
  readonly tiroirAttenteOuvert = signal<boolean>(false);

  /** Données de synthèse du dernier encaissement pour impression ticket / reçu. */
  readonly dernierEncaissement = signal<{
    client: string;
    mode: ModePaiementApi;
    recu: number;
    rendu: number;
  }>({
    client: 'Client Comptoir',
    mode: 'ESPECES',
    recu: 0,
    rendu: 0,
  });

  /** Instance SpeechRecognition courante (libérée à la destruction). */
  private reconnaissance: SpeechRecognitionLike | null = null;

  constructor() {
    // Ne laisse pas le micro ouvert si le composant est détruit.
    this.destroyRef.onDestroy(() => this.arreterReconnaissance());

    this.recherche.valueChanges
      .pipe(
        startWith(''),
        debounceTime(160),
        switchMap((terme) =>
          this.vinsService
            .lister({ recherche: terme, enStock: true, tri: 'nom' })
            .pipe(catchError(() => of([]))),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((vins) => {
        this.vins.set(vins);
        this.chargement.set(false);
      });

    // Pré-remplissage automatique si transmis depuis une commande Click-and-Collect
    const clientPredefini = localStorage.getItem('lb.caisse.client_predefini');
    if (clientPredefini) {
      this.clientNom.setValue(clientPredefini);
      localStorage.removeItem('lb.caisse.client_predefini');
    }
  }

  ajouter(vin: Vin): void {
    this.panier.ajouter(vin);
    this.flash(this.langue.t('CAISSE.scanAjoute', { vin: vin.nom }));
    this.jouerSon('ajout');
  }

  deposer(event: CdkDragDrop<PanierLigne[]>): void {
    const vin = event.item.data as Vin | undefined;
    if (vin) this.ajouter(vin);
  }

  modifierQuantite(ligne: PanierLigne, delta: number): void {
    this.panier.majQuantite(ligne.vin.id, ligne.quantite + delta);
  }

 // ---------- scan code-barres / QR ----------

  /** Ouvre le panneau de scan (caméra + saisie clavier de repli). */
  ouvrirScanner(): void {
    this.scanOuvert.set(!this.scanOuvert());
    if (!this.scanOuvert()) this.scanResultat.set(null);
  }

  /** Referme le panneau et libère la caméra. */
  fermerScanner(): void {
    this.scanOuvert.set(false);
    this.scanResultat.set(null);
    this.scanErreur.set(false);
    this.scanForm.reset();
  }

  /** Code décodé par la caméra. */
  surCodeScanne(code: string): void {
    this.resoudreCode(code);
  }

  /** Validation du code saisi au clavier (douchette ou scanneur USB). */
  validerCodeSaisi(): void {
    if (this.scanForm.invalid) return;
    this.resoudreCode(this.scanForm.getRawValue().code.trim());
  }

  /** Cherche le vin correspondant au code et l'ajoute au panier. */
  private resoudreCode(code: string): void {
    if (!code) return;

    this.scanForm.setValue({ code });
    this.vinsService
      .parCodeBarres(code)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (vin) => {
          this.jouerSon('scan');
          if (!vin) {
            this.scanResultat.set(null);
            this.scanErreur.set(true);
            this.flash(this.langue.t('CAISSE.scanIntrouvable'));
            return;
          }

          this.scanErreur.set(false);
          this.scanResultat.set(vin);
          // Ajout immédiat : en caisse, un scan valide ne doit pas exiger un second clic.
          this.ajouter(vin);
          this.scanForm.reset();
        },
        error: (erreur: unknown) => {
          console.error('Lecture du code-barres impossible.', erreur);
          this.scanErreur.set(true);
        },
      });
  }

  rechercheVocale(): void {
    const speechWindow = window as SpeechWindow;
    const Recognition = speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition;
    if (!Recognition) {
      this.flash(this.langue.t('CAISSE.vocalIndisponible'));
      return;
    }
    // Une session précédente encore active écrirait en double dans le champ.
    this.arreterReconnaissance();

    const recognition = new Recognition();
    this.reconnaissance = recognition;
    recognition.lang = 'fr-FR';
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onresult = (event) => {
      const texte = event.results[0]?.[0]?.transcript ?? '';
      this.recherche.setValue(texte);
      this.ecouteVocale.set(false);
    };
    recognition.onerror = () => {
      this.ecouteVocale.set(false);
      this.flash(this.langue.t('CAISSE.vocalEchec'));
    };
    recognition.onend = () => this.ecouteVocale.set(false);
    this.ecouteVocale.set(true);
    recognition.start();
  }

  /** Interrompt la session vocale courante s'il y en a une. */
  private arreterReconnaissance(): void {
    if (!this.reconnaissance) return;
    try {
      this.reconnaissance.onresult = null;
      this.reconnaissance.onend = null;
      this.reconnaissance.onerror = null;
      this.reconnaissance.stop();
    } catch {
      // Session déjà terminée : rien à faire.
    }
    this.reconnaissance = null;
    this.ecouteVocale.set(false);
  }

  ouvrirEcranClient(): void {
    window.open('/ecran-client', 'lb-ecran-client', 'width=520,height=780,noopener,noreferrer');
  }

  imprimerTicket(): void {
    // Le ticket imprimé doit porter l'heure exacte et un numéro définitif.
    this.horodatage.set(new Date());
    this.numeroTicket.set(this.calculerNumeroTicket());
    window.print();
  }

  async encaisser(): Promise<void> {
    if (this.panier.estVide()) return;
    // F1 ou double-clic : un seul encaissement à la fois.
    if (this.encaissementEnCours()) return;
    this.encaissementEnCours.set(true);

    const mode = this.modePaiement();
    const client = this.clientNom.value.trim() || 'Client Comptoir';
    const refPaiement = this.referencePaiement.value.trim();
    const total = this.panier.total();
    let recu = this.montantRecu();

    // En espèces, si aucun montant n'a été saisi, on valide sur le montant exact.
    if (mode === 'ESPECES' && recu <= 0) {
      recu = total;
      this.montantRecu.set(recu);
    }

    try {
      const vente = await this.sync.enregistrerVente(
        this.panier.lignes(),
        mode,
        client,
        refPaiement,
      );
      const enAttente = vente.id === 0;
      if (!enAttente) this.commandes.enregistrerDepuisApi(vente);

      const rendu = recu >= total ? recu - total : 0;
      this.dernierEncaissement.set({
        client,
        mode,
        recu,
        rendu,
      });

      this.panier.vider();
      this.paiementOk.set(!enAttente);

      const messageSucces = enAttente
        ? 'Vente enregistrée localement, en attente de synchronisation.'
        : `${this.langue.t('CAISSE.paiementAccepte')} (${mode}${rendu > 0 ? ' · Rendu: ' + rendu.toLocaleString() + ' Ar' : ''})`;

      this.flash(messageSucces);
      this.jouerSon(enAttente ? 'erreur' : 'succes');
      this.numeroTicket.set(this.calculerNumeroTicket());

      // Réinitialiser les champs de caisse pour le prochain client
      this.montantRecu.set(0);
      this.referencePaiement.reset();
      this.clientNom.setValue('Client Comptoir');

      if (!enAttente) {
        void import('canvas-confetti').then((module) =>
          module.default({ particleCount: 90, spread: 70, origin: { y: 0.72 } }),
        );
        window.setTimeout(() => this.paiementOk.set(false), 2400);
      }
    } catch (erreur) {
      console.error('Encaissement backend impossible.', erreur);
      this.flash(this.langue.t('CAISSE.paiementRefuse'));
      this.jouerSon('erreur');
    } finally {
      this.encaissementEnCours.set(false);
    }
  }

  // ---------- Fonctionnalités de Paiement & Monnaie (Ariary MGA) ----------

  changerModePaiement(mode: ModePaiementApi): void {
    this.modePaiement.set(mode);
    if (mode === 'ESPECES' && this.montantRecu() === 0 && !this.panier.estVide()) {
      this.montantRecu.set(this.panier.total());
    }
  }

  cycleModePaiement(): void {
    const modes = this.modesPaiement.map((m) => m.code);
    const idx = modes.indexOf(this.modePaiement());
    const code = modes[(idx + 1) % modes.length];
    const libelle = this.modesPaiement.find((m) => m.code === code)?.libelle ?? code;
    this.changerModePaiement(code);
    this.flash(`Mode sélectionné : ${libelle}`);
  }

  ajouterCoupure(montant: number): void {
    this.montantRecu.update((v) => v + montant);
    this.jouerSon('scan');
  }

  definirMontantExact(): void {
    this.montantRecu.set(this.panier.total());
    this.jouerSon('scan');
  }

  reinitialiserMontantRecu(): void {
    this.montantRecu.set(0);
  }

  surSaisieMontantRecu(valeur: string): void {
    const n = parseFloat(valeur) || 0;
    this.montantRecu.set(n >= 0 ? n : 0);
  }

  // ---------- Fonctionnalités de Mise en Attente (Park & Resume) ----------

  mettreEnAttente(): void {
    if (this.panier.estVide()) {
      this.flash('Le panier est vide.');
      return;
    }

    const ticket: PanierEnAttente = {
      id: `ATT-${Date.now().toString(36).toUpperCase()}`,
      date: new Date().toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }),
      lignes: [...this.panier.lignes()],
      total: this.panier.total(),
      client: this.clientNom.value.trim() || 'Client Comptoir',
      modePaiement: this.modePaiement(),
    };

    const liste = [ticket, ...this.paniersEnAttente()];
    this.sauvegarderPaniersEnAttente(liste);
    this.panier.vider();
    this.montantRecu.set(0);
    this.flash(`Ticket ${ticket.id} mis en attente (${ticket.client}).`);
    this.jouerSon('succes');
  }

  reprendrePanier(id: string): void {
    const ticket = this.paniersEnAttente().find((p) => p.id === id);
    if (!ticket) return;

    if (!this.panier.estVide()) {
      if (!confirm('Le panier actuel contient des articles. Remplacer par le ticket en attente ?')) {
        return;
      }
    }

    this.panier.restaurerLignes(ticket.lignes);
    this.clientNom.setValue(ticket.client);
    this.modePaiement.set(ticket.modePaiement);
    this.montantRecu.set(0);

    const liste = this.paniersEnAttente().filter((p) => p.id !== id);
    this.sauvegarderPaniersEnAttente(liste);
    this.tiroirAttenteOuvert.set(false);
    this.flash(`Ticket ${ticket.id} repris au comptoir.`);
    this.jouerSon('ajout');
  }

  supprimerPanierEnAttente(id: string): void {
    const liste = this.paniersEnAttente().filter((p) => p.id !== id);
    this.sauvegarderPaniersEnAttente(liste);
    this.flash('Ticket en attente supprimé.');
  }

  basculerTiroirAttente(): void {
    this.tiroirAttenteOuvert.set(!this.tiroirAttenteOuvert());
  }

  private lirePaniersEnAttente(): PanierEnAttente[] {
    try {
      const brut = localStorage.getItem(CLE_PANIERS_ATTENTE);
      return brut ? JSON.parse(brut) : [];
    } catch {
      return [];
    }
  }

  private sauvegarderPaniersEnAttente(liste: PanierEnAttente[]): void {
    this.paniersEnAttente.set(liste);
    try {
      localStorage.setItem(CLE_PANIERS_ATTENTE, JSON.stringify(liste));
    } catch {
      // Stockage local plein ou désactivé
    }
  }

  // ---------- Reçu numérique & Partage WhatsApp ----------

  partagerWhatsApp(): void {
    const enc = this.dernierEncaissement();
    const lignes = this.ticketLignes();
    const dateStr = this.horodatage().toLocaleString('fr-FR');
    let message = `🍷 *LAZAN'I BETSILEO - Ticket de Caisse*\n`;
    message += `Ticket : *${this.numeroTicket()}*\n`;
    message += `Date : ${dateStr}\n`;
    message += `Client : *${enc.client}*\n`;
    message += `--------------------------------\n`;
    lignes.forEach((l) => {
      message += `• ${l.quantite}× ${l.vin.nom} : ${(l.prixUnitaire * l.quantite).toLocaleString()} Ar\n`;
    });
    message += `--------------------------------\n`;
    message += `*TOTAL : ${this.panier.total().toLocaleString()} Ar*\n`;
    message += `Paiement : ${enc.mode}\n`;
    if (enc.mode === 'ESPECES' && enc.recu > 0) {
      message += `Reçu : ${enc.recu.toLocaleString()} Ar\n`;
      message += `Rendu de monnaie : ${enc.rendu.toLocaleString()} Ar\n`;
    }
    message += `\n_Merci de votre confiance et bonne dégustation !_`;

    const url = `https://wa.me/?text=${encodeURIComponent(message)}`;
    window.open(url, '_blank');
  }

  /** Verrou d'encaissement : empêche le double paiement. */
  private readonly encaissementEnCours = signal(false);

  /** Numéro de ticket provisoire : il change à chaque encaissement. */
  readonly numeroTicket = signal(this.calculerNumeroTicket());
  /** Horodatage affiché sur le ticket (rafraîchi à l'impression). */
  readonly horodatage = signal(new Date());

  totalLigne(ligne: PanierLigne): number {
    return this.panier.totalLigne(ligne);
  }

  /** Numéro séquentiel lisible : TJJMMAA-NNN, compteur persistant. */
  private calculerNumeroTicket(): string {
    const maintenant = new Date();
    const jour = maintenant.toISOString().slice(2, 10).replace(/-/g, '');
    const serie = String(this.lireSequence()).padStart(3, '0').slice(-3);
    return `T${jour}-${serie}`;
  }

  /** Incrémente et renvoie le compteur de tickets du jour (persistant). */
  private lireSequence(): number {
    let suivant = 1;
    try {
      const brut = Number(localStorage.getItem(CLE_TICKET_SEQ));
      if (Number.isFinite(brut) && brut >= 0) suivant = brut + 1;
      localStorage.setItem(CLE_TICKET_SEQ, String(suivant));
    } catch {
      // Stockage indisponible : on reste sur un numéro éphémère.
      suivant = Math.floor(Math.random() * 1000) + 1;
    }
    return suivant;
  }

  @HostListener('window:keydown', ['$event'])
  gererRaccourcis(event: KeyboardEvent): void {
    if (event.key === 'F1') {
      event.preventDefault();
      void this.encaisser();
    }
    if (event.key === 'F2') {
      event.preventDefault();
      this.cycleModePaiement();
    }
    if (event.key === 'F3') {
      event.preventDefault();
      const champ = this.champRecherche?.nativeElement;
      champ?.focus();
      champ?.select();
    }
    if (event.key === 'F4') {
      event.preventDefault();
      if (!this.panier.estVide()) {
        this.mettreEnAttente();
      } else if (this.nbPaniersEnAttente() > 0) {
        this.basculerTiroirAttente();
      }
    }
    if (event.key === 'Escape') {
      if (this.tiroirAttenteOuvert()) {
        event.preventDefault();
        this.tiroirAttenteOuvert.set(false);
        return;
      }
      if (this.scanOuvert()) {
        event.preventDefault();
        this.fermerScanner();
        return;
      }
      if (!this.panier.estVide()) {
        event.preventDefault();
        if (!confirm(this.langue.t('CAISSE.panierVide') + ' ?')) return;
        this.panier.vider();
        this.montantRecu.set(0);
        this.flash(this.langue.t('CAISSE.panierVide'));
      }
    }
  }

  /** Bascule le mode tactile à la main (la détection auto reste la référence). */
  basculerTactile(): void {
    this.tactileService.basculer();
  }

  /** Active ou désactive le son de validation. */
  basculerSon(): void {
    this.son.basculer();
  }

  /** Joue un signal sonore court (délégué à SonService). */
  private jouerSon(variante: VarianteSon): void {
    this.son.jouer(variante);
  }

  private flash(message: string): void {
    this.message.set(message);
    window.setTimeout(() => {
      if (this.message() === message) this.message.set(null);
    }, 2200);
  }

  }
