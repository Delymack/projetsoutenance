import { Injectable, Signal, computed, inject, signal } from '@angular/core';


/** clés */
const CLE_TELEPHONE = 'lb.profil.telephone';
const CLE_VILLE = 'lb.profil.ville';
const CLE_ADRESSES = 'lb.profil.adresses';
const CLE_PREFS = 'lb.profil.prefs';

/** adresse */
export interface AdresseProfil {
  id: string;
  libelle: string;
  destinataire: string;
  telephone: string;
  ligne: string;
  ville: string;
  notes?: string;
  parDefaut: boolean;
}

/** préférences */
export interface PreferencesProfil {
  promotions: boolean;
  stock: boolean;
  commandes: boolean;
  newsletter: boolean;
}

/** défauts */
const PREFERENCES_DEFAUT: PreferencesProfil = {
  promotions: true,
  stock: true,
  commandes: true,
  newsletter: false,
};

/** barème */
const COMPLETUDE_COORDONNEES = 40;
const COMPLETUDE_ADRESSE = 20;
const COMPLETUDE_DEFAUT = 20;
const COMPLETUDE_PREFERENCES = 20;
const PREFERENCES_MINIMALES = 2;

/** garde */
function estAdresseProfil(valeur: unknown): valeur is AdresseProfil {
  if (typeof valeur !== 'object' || valeur === null) return false;
  const a = valeur as Partial<AdresseProfil>;
  return (
    typeof a.id === 'string' &&
    typeof a.libelle === 'string' &&
    typeof a.destinataire === 'string' &&
    typeof a.telephone === 'string' &&
    typeof a.ligne === 'string' &&
    typeof a.ville === 'string' &&
    typeof a.parDefaut === 'boolean' &&
    (a.notes === undefined || typeof a.notes === 'string')
  );
}

/** booléen */
function booleen(valeur: unknown, defaut: boolean): boolean {
  return typeof valeur === 'boolean' ? valeur : defaut;
}

/** carnet d'adresses */
@Injectable({ providedIn: 'root' })
export class ProfilService {
 /** état */
  private readonly telephoneSig = signal<string>(this.lireTexte(CLE_TELEPHONE));
  private readonly villeSig = signal<string>(this.lireTexte(CLE_VILLE));
  private readonly adressesSig = signal<AdresseProfil[]>(this.lireAdresses());
  private readonly preferencesSig = signal<PreferencesProfil>(this.lirePreferences());

 /** API */
  readonly telephone: Signal<string> = this.telephoneSig.asReadonly();
  readonly ville: Signal<string> = this.villeSig.asReadonly();
  readonly adresses: Signal<AdresseProfil[]> = this.adressesSig.asReadonly();
  readonly preferences: Signal<PreferencesProfil> = this.preferencesSig.asReadonly();

 /** adresse par défaut */
  readonly adresseParDefaut: Signal<AdresseProfil | null> = computed(
    () => this.adressesSig().find((adresse) => adresse.parDefaut) ?? null,
  );

 /** complétude */
  readonly completude: Signal<number> = computed(() => {
    let score = 0;

    if (this.telephoneSig().trim() && this.villeSig().trim()) {
      score += COMPLETUDE_COORDONNEES;
    }

    if (this.adressesSig().length > 0) {
      score += COMPLETUDE_ADRESSE;
    }

    const defaut = this.adresseParDefaut();
    if (
      defaut &&
      defaut.ligne.trim() &&
      defaut.ville.trim() &&
      defaut.destinataire.trim() &&
      defaut.telephone.trim()
    ) {
      score += COMPLETUDE_DEFAUT;
    }

    const prefs = this.preferencesSig();
    const actives = [prefs.promotions, prefs.stock, prefs.commandes, prefs.newsletter].filter(
      (actif) => actif,
    ).length;
    if (actives >= PREFERENCES_MINIMALES) {
      score += COMPLETUDE_PREFERENCES;
    }

    return Math.round(score);
  });

 /** téléphone */
  majTelephone(valeur: string): void {
    const suivant = valeur.trim();
    this.telephoneSig.set(suivant);
    this.ecrireTexte(CLE_TELEPHONE, suivant);
  }

 /** ville */
  majVille(valeur: string): void {
    const suivant = valeur.trim();
    this.villeSig.set(suivant);
    this.ecrireTexte(CLE_VILLE, suivant);
  }

 /** ajout d'adresse */
  ajouterAdresse(adresse: Omit<AdresseProfil, 'id'>): AdresseProfil {
    const liste = this.adressesSig();
    const premiere = liste.length === 0;
    const creee: AdresseProfil = {
      ...adresse,
      id: this.creerId(),
      parDefaut: premiere || adresse.parDefaut === true,
    };
    const normalisee = premiere
      ? [creee]
      : this.appliquerParDefaut([...liste, creee], creee.id);
    this.majAdresses(normalisee);
    return normalisee.find((element) => element.id === creee.id) ?? creee;
  }

 /** modification d'adresse */
  modifierAdresse(id: string, patch: Partial<AdresseProfil>): void {
    const liste = this.adressesSig();
    if (!liste.some((adresse) => adresse.id === id)) return;

    let cible = liste.map((adresse) => (adresse.id === id ? { ...adresse, ...patch, id } : adresse));

    if (patch.parDefaut === true) {
      cible = this.appliquerParDefaut(cible, id);
    } else if (patch.parDefaut === false && cible.length > 0) {
      cible = this.appliquerParDefaut(cible, cible[0].id);
    }

    this.majAdresses(cible);
  }

 /** retrait d'adresse */
  retirerAdresse(id: string): void {
    const liste = this.adressesSig();
    const reste = liste.filter((adresse) => adresse.id !== id);
    if (reste.length === liste.length) return;

    if (reste.length === 0) {
      this.majAdresses([]);
      return;
    }

    const conservee = reste.find((adresse) => adresse.parDefaut) ?? reste[0];
    this.majAdresses(this.appliquerParDefaut(reste, conservee.id));
  }

 /** adresse par défaut */
  definirAdresseParDefaut(id: string): void {
    const liste = this.adressesSig();
    if (!liste.some((adresse) => adresse.id === id)) return;
    this.majAdresses(this.appliquerParDefaut(liste, id));
  }

 /** préférences */
  majPreferences(patch: Partial<PreferencesProfil>): void {
    const suivante: PreferencesProfil = { ...this.preferencesSig(), ...patch };
    this.preferencesSig.set(suivante);
    this.ecrirePreferences(suivante);
  }

 /** interne */
  private majAdresses(liste: AdresseProfil[]): void {
    this.adressesSig.set(liste);
    try {
      localStorage.setItem(CLE_ADRESSES, JSON.stringify(liste));
    } catch {
      console.warn('Adresses non enregistrées (stockage indisponible).');
    }
  }

  private appliquerParDefaut(liste: AdresseProfil[], id: string): AdresseProfil[] {
    return liste.map((adresse) => ({ ...adresse, parDefaut: adresse.id === id }));
  }

  private creerId(): string {
    return `a-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  }

  private ecrirePreferences(preferences: PreferencesProfil): void {
    try {
      localStorage.setItem(CLE_PREFS, JSON.stringify(preferences));
    } catch {
      console.warn('Préférences non enregistrées (stockage indisponible).');
    }
  }

 /** lecture */
  private lireTexte(cle: string): string {
    try {
      return localStorage.getItem(cle) ?? '';
    } catch {
      return '';
    }
  }

  private ecrireTexte(cle: string, valeur: string): void {
    try {
      localStorage.setItem(cle, valeur);
    } catch {
      console.warn('Profil non enregistré (stockage indisponible).');
    }
  }

  private lireAdresses(): AdresseProfil[] {
    try {
      const brut = localStorage.getItem(CLE_ADRESSES);
      if (!brut) return [];
      const parse: unknown = JSON.parse(brut);
      return Array.isArray(parse) ? parse.filter(estAdresseProfil) : [];
    } catch {
      return [];
    }
  }

  private lirePreferences(): PreferencesProfil {
    try {
      const brut = localStorage.getItem(CLE_PREFS);
      if (!brut) return { ...PREFERENCES_DEFAUT };
      const parse = JSON.parse(brut) as unknown;
      if (typeof parse !== 'object' || parse === null) return { ...PREFERENCES_DEFAUT };
      const prefs = parse as Partial<PreferencesProfil>;
      return {
        promotions: booleen(prefs.promotions, PREFERENCES_DEFAUT.promotions),
        stock: booleen(prefs.stock, PREFERENCES_DEFAUT.stock),
        commandes: booleen(prefs.commandes, PREFERENCES_DEFAUT.commandes),
        newsletter: booleen(prefs.newsletter, PREFERENCES_DEFAUT.newsletter),
      };
    } catch {
      return { ...PREFERENCES_DEFAUT };
    }
  }
}
