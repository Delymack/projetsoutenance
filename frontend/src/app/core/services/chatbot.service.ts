import { Injectable, computed, inject, signal } from '@angular/core';

import { MessageChat, RegleChatbot } from '../models/chat.model';
import { LangueService } from './langue.service';

/** Délai de « rédaction » avant l'apparition de la réponse (ms). */
const DELAI_REPONSE_MS = 550;

/**
 * Moteur du chatbot.
 *
 * Choix assumé : **aucun appel à un modèle de langage**. Le soutenance porte sur
 * une application de gestion, pas sur une IA ; brancher une API distante
 * rendrait la démonstration dépendante du réseau et du quota. On implémente donc
 * un moteur à règles, ce qui est :
 *  - déterministe (démonstration reproductible) ;
 *  - hors ligne (le service worker sert la page, le bot reste utile) ;
 *  - et surtout lisible — c'est précisément ce que l'on peut expliquer en soutenance.
 *
 * Si un LLM devait être branché plus tard, il suffirait de remplacer `repondre()`
 * par un appel HTTP : l'interface du composant (`messages`, `envoyer()`) ne change
 * pas.
 *
 * La reconnaissance des mots-clés se fait sur un texte normalisé (minuscules,
 * sans accents ni ponctuation) et accepte aussi quelques termes malgaches, pour
 * que le bot reste utile quand l'interface est en langue mg.
 */
@Injectable({ providedIn: 'root' })
export class ChatbotService {
  private readonly langue = inject(LangueService);

  /** Conversation en cours. */
  readonly messages = signal<MessageChat[]>([]);

  /** Le robot est en train de « rédiger ». */
  readonly redacte = signal(false);

  /** Prises de contact envoyées par le formulaire « conseiller ». */
  readonly demandes = signal<{ nom: string; email: string; message: string; date: string }[]>([]);

  /** Conversation non vide : sert à proposer une remise à zéro. */
  readonly aDesMessages = computed(() => this.messages().length > 0);

  /**
   * Règles, de la plus précise à la plus large.
   * L'ordre compte : la première règle satisfaite gagne. Les formulations
   * ambiguës (« bonjour », « vin ») sont donc traitées en dernier.
   */
  private readonly regles: RegleChatbot[] = [
    {
      groupes: [['horaire', 'ouverture', 'ouvert', 'ferme', 'fermeture', 'fotoana', 'miasa', 'misokatra']],
      reponse: 'horaires',
      suggestions: ['CHATBOT.questions.livraison', 'CHATBOT.questions.paiement'],
    },
    {
      groupes: [
        ['livraison', 'livrer', 'andefasana', 'fandefasana', 'frais'],
        ['gratuit', 'free', 'gratis', '100', 'minimum', 'seuil'],
      ],
      reponse: 'livraison',
      suggestions: ['CHATBOT.questions.horaires', 'CHATBOT.questions.paiement'],
    },
    {
      groupes: [
        ['paiement', 'payer', 'payer', 'regler', 'fandoavam', 'vola', 'mobile', 'mvola', 'orange money', 'carte', 'karatra'],
      ],
      reponse: 'paiement',
      suggestions: ['CHATBOT.questions.livraison', 'CHATBOT.questions.vinRouge'],
    },
    {
      groupes: [
        ['millesime', 'annee', 'année', 'vintage', 'taona'],
        ['mieux', 'meilleur', 'conseil', 'recommand', 'atolotra', 'ampy', 'tsara'],
      ],
      reponse: 'millesime',
      suggestions: ['CHATBOT.questions.vinRouge', 'CHATBOT.questions.vinBlanc'],
    },
    {
      groupes: [
        ['promotion', 'promo', 'remise', 'reduction', 'reduction', 'fihenam', 'mihena', 'code'],
      ],
      reponse: 'promo',
      suggestions: ['CHATBOT.questions.horaires', 'CHATBOT.questions.livraison'],
    },
    {
      groupes: [['rouge', 'symfony', 'grenat', 'cabernet', 'syrah', 'malbec', 'mena']],
      reponse: 'vinRouge',
      suggestions: ['CHATBOT.questions.vinBlanc', 'CHATBOT.questions.vinTable'],
    },
    {
      groupes: [
        ['blanc', 'blanche', 'sec', 'frais', 'fraîche', 'chardonnay', 'sauvignon', 'vermentino', 'maitso', 'mamay'],
      ],
      reponse: 'vinBlanc',
      suggestions: ['CHATBOT.questions.vinRouge', 'CHATBOT.questions.dessert'],
    },
    {
      groupes: [
        ['mousseux', 'petillant', 'effervescent', 'champagne', 'boussel'],
      ],
      reponse: 'vinMousseux',
      suggestions: ['CHATBOT.questions.fete', 'CHATBOT.questions.vinBlanc'],
    },
    {
      groupes: [
        ['vin de table', 'vin local', 'tradition', 'petit-lait', 'lait', 'village', 'divano', 'malagasy', 'fety'],
      ],
      reponse: 'vinTable',
      suggestions: ['CHATBOT.questions.vinRouge', 'CHATBOT.questions.millesime'],
    },
    {
      groupes: [
        ['dessert', 'gateau', 'gateau', 'sucre', 'sucr', 'chocolat', 'mofo', 'mofo'],
      ],
      reponse: 'dessert',
      suggestions: ['CHATBOT.questions.vinMousseux', 'CHATBOT.questions.fete'],
    },
    {
      groupes: [['fete', 'fete', 'mariage', 'anniversaire', 'cadeau', 'maniry', 'fankasina', 'hafatra', 'cadeau']],
      reponse: 'fete',
      suggestions: ['CHATBOT.questions.vinMousseux', 'CHATBOT.questions.vinRouge'],
    },
    {
      groupes: [['accord', 'plat', 'manger', 'restaurant', 'sakafo', 'akoho', 'hena']],
      reponse: 'accord',
      suggestions: ['CHATBOT.questions.vinRouge', 'CHATBOT.questions.vinBlanc'],
    },
    {
      groupes: [
        ['stock', 'rupture', 'disponible', 'disponibilite', 'trano', 'tsy', 'vita', 'dispo'],
      ],
      reponse: 'stock',
      suggestions: ['CHATBOT.questions.vinRouge', 'CHATBOT.questions.horaires'],
    },
    {
      groupes: [
        ['commande', 'commander', 'commande', 'panier', 'kajy', 'baovao', 'livraison de commande'],
      ],
      reponse: 'commande',
      suggestions: ['CHATBOT.questions.livraison', 'CHATBOT.questions.paiement'],
    },
    {
      groupes: [
        ['quel', 'quelle', 'conseil', 'choisir', 'choisir', 'recommande', 'recommand', 'profil', 'sommelier', 'mpitsara'],
      ],
      reponse: 'marge',
      suggestions: ['CHATBOT.questions.vinRouge', 'CHATBOT.questions.vinBlanc'],
    },
  ];

  constructor() {
    // Message d'accueil dès l'ouverture du panneau.
    this.ajouterMessage('bot', 'CHATBOT.reponses.accueil', [
      'CHATBOT.questions.horaires',
      'CHATBOT.questions.livraison',
      'CHATBOT.questions.vinRouge',
    ]);
  }

  /**
   * Traite un message utilisateur.
   * Le message est ajouté immédiatement (réactivité perçue), puis la réponse
   * arrive après un court délai : sans cela, la réponse paraîtrait instantanée
   * et factice.
   */
  envoyer(texte: string): void {
    const contenu = texte.trim();
    if (!contenu) return;

    this.ajouterMessage('user', contenu, []);

    const reponse = this.repondre(contenu);
    this.redacte.set(true);
    setTimeout(() => {
      this.redacte.set(false);
      this.ajouterMessage('bot', reponse.reponse, reponse.suggestions);
    }, DELAI_REPONSE_MS);
  }

  /** Enregistre une prise de contact avec un conseiller (simulation). */
  envoyerDemande(demande: { nom: string; email: string; message: string }): void {
    this.demandes.update((demandes) => [
      { ...demande, date: new Date().toISOString() },
      ...demandes,
    ]);
    this.ajouterMessage('bot', 'CHATBOT.conseillerForm.succes', ['CHATBOT.questions.horaires']);
  }

  /** Remet la conversation à zéro (nouvel accueil inclus). */
  reinitialiser(): void {
    this.messages.set([]);
    this.ajouterMessage('bot', 'CHATBOT.reponses.accueil', [
      'CHATBOT.questions.horaires',
      'CHATBOT.questions.livraison',
      'CHATBOT.questions.vinRouge',
    ]);
  }

  // --- Moteur de règles ---

  /**
   * Choisit la règle correspondant au message.
   * Une règle à plusieurs groupes exige **tous** les groupes satisfaits : c'est ce
   * qui permet de distinguer « livraison gratuite » de « livraison » seul.
   */
  private repondre(texte: string): { reponse: string; suggestions: string[] } {
    const normalise = this.normaliser(texte);

    for (const regle of this.regles) {
      if (regle.groupes.every((groupe) => groupe.some((mot) => normalise.includes(mot)))) {
        return {
          reponse: regle.reponse,
          suggestions: regle.suggestions ?? [],
        };
      }
    }

    return { reponse: 'defaut', suggestions: ['CHATBOT.questions.horaires', 'CHATBOT.questions.livraison'] };
  }

  /**
   * Normalise un message : minuscules, sans accents, ponctuation réduite aux
   * espaces. « Horaires ? » devient « horaires », « où êtes-vous » devient
   * « ou etes vous » — ce qui rend le robot tolérant aux fautes de frappe.
   */
  private normaliser(texte: string): string {
    return texte
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-z0-9+ ]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  /**
   * Ajoute un message à la conversation.
   * `texte` est une **clé i18n** : la traduction est effectuée au moment de
   * l'envoi. Conséquence assumée : changer de langue ne réécrit pas l'historique
   * de la conversation (il reste dans la langue de l'échange) — c'est le
   * comportement attendu d'un vrai support.
   */
  private ajouterMessage(role: MessageChat['role'], texte: string, suggestions: string[]): void {
    const message: MessageChat = {
      id: `m-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      role,
      texte,
      date: new Date(),
      suggestions,
    };
    this.messages.update((messages) => [...messages, message]);
  }

  /** Traduit une clé i18n avec la langue courante du chatbot. */
  traduire(cle: string): string {
    return this.langue.t(cle);
  }
}