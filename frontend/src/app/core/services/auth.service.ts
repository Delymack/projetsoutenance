import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { UserRole, Utilisateur } from '../models/product.model';

const CLE_TOKEN = 'lb.token';
const CLE_REFRESH = 'lb.refresh';
const CLE_UTILISATEUR = 'lb.utilisateur';

const ROLES_CONNUS: readonly UserRole[] = ['admin', 'gestionnaire', 'vendeur', 'client'];

/** Rôle brut renvoyé par l'API Django (`apps.accounts.models.User.Role`). */
type RoleApi = 'ADMIN' | 'GESTIONNAIRE' | 'VENDEUR' | 'CLIENT';

/** Profil renvoyé par `POST /api/auth/login/` et les vérifications OTP. */
interface UtilisateurApi {
  id: number;
  username: string;
  email?: string | null;
  first_name?: string;
  last_name?: string;
  telephone?: string;
  role: RoleApi;
  avatar_url?: string | null;
}

/** Enveloppe de connexion : SimpleJWT renvoie la paire + le profil. */
interface ReponseLogin {
  access: string;
  refresh: string;
  user: UtilisateurApi;
}

/** Enveloppe d'une vérification OTP (inscription ou connexion). */
interface ReponseVerification {
  message: string;
  access: string;
  refresh: string;
  user?: UtilisateurApi;
}

/** Table de correspondance rôle API → rôle applicatif. */
const VERS_ROLE: Record<RoleApi, UserRole> = {
  ADMIN: 'admin',
  GESTIONNAIRE: 'gestionnaire',
  VENDEUR: 'vendeur',
  CLIENT: 'client',
};

/** Vérifie la forme d'un utilisateur relu depuis localStorage. */
function estUtilisateur(valeur: unknown): valeur is Utilisateur {
  if (typeof valeur !== 'object' || valeur === null) return false;
  const u = valeur as Partial<Utilisateur>;
  return (
    typeof u.id === 'string' &&
    typeof u.nom === 'string' &&
    typeof u.email === 'string' &&
    ROLES_CONNUS.includes(u.role as UserRole)
  );
}

/**
 * Service d'authentification.
 *
 * Le JWT est stocké dans localStorage (choix imposed par le cahier des charges)
 * et lu par l'intercepteur HTTP. En production, préférer un cookie HttpOnly
 * + SameSite=Strict pour contrer le XSS.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  private renouvellementEnCours: Promise<string | null> | null = null;

  private readonly utilisateurSig = signal<Utilisateur | null>(this.reprendre());

  /** Utilisateur connecté (null si anonyme). */
  readonly utilisateur = this.utilisateurSig.asReadonly();

  /** Est-on connecté ? */
  readonly connecte = computed(() => this.utilisateurSig() !== null);

  /** Rôle courant. */
  readonly role = computed<UserRole | null>(() => this.utilisateurSig()?.role ?? null);

  // --- API publique ---

  /** JWT brut, ou chaîne vide. */
  get token(): string {
    return this.utilisateurSig()?.token ?? localStorage.getItem(CLE_TOKEN) ?? '';
  }

  /**
   * Connexion par identifiant / e-mail et mot de passe.
   *
   * L'API attend `{username, password}` (`USERNAME_FIELD` de Django) et
   * accepte un e-mail dans ce champ : le backend se connecte par identifiant
   * **ou** par e-mail. La réponse est la paire JWT SimpleJWT
   * `{access, refresh, user}` — `access` devient le porteur envoyé par
   * l'intercepteur.
   */
  async connexion(identifiant: string, motDePasse: string): Promise<Utilisateur> {
    const reponse = await firstValueFrom(
      this.http.post<ReponseLogin>(`${environment.apiUrl}/auth/login/`, {
        username: identifiant.trim(),
        password: motDePasse,
      }),
    );
    const utilisateur = this.versUtilisateurApi(reponse.user, reponse.access);
    this.stocker(utilisateur, reponse.refresh);
    return utilisateur;
  }

  /** Renouvelle l'access JWT expiré sans interrompre la session du client. */
  renouvelerToken(): Promise<string | null> {
    if (this.renouvellementEnCours) return this.renouvellementEnCours;

    const refresh = localStorage.getItem(CLE_REFRESH);
    const utilisateur = this.utilisateurSig();
    if (!refresh || !utilisateur) return Promise.resolve(null);

    this.renouvellementEnCours = firstValueFrom(
      this.http.post<{ access: string; refresh?: string }>(
        `${environment.apiUrl}/auth/refresh/`,
        { refresh },
      ),
    )
      .then((reponse) => {
        if (!reponse.access) return null;
        this.stocker(
          { ...utilisateur, token: reponse.access },
          reponse.refresh ?? refresh,
        );
        return reponse.access;
      })
      .catch(() => null)
      .finally(() => {
        this.renouvellementEnCours = null;
      });

    return this.renouvellementEnCours;
  }

  // --- Système de vérification par code à 6 chiffres ---

  /** Envoie un code de vérification pour l'inscription */
  async signupSendCode(data: {
    nom: string;
    email?: string;
    telephone?: string;
    password: string;
    contact_type: 'email' | 'sms';
  }): Promise<{ message: string; expires_in: number }> {
    return firstValueFrom(
      this.http.post<{ message: string; expires_in: number }>(
        `${environment.apiUrl}/auth/signup/send-code/`,
        data
      )
    );
  }

  /** Vérifie le code d'inscription et crée le compte */
  async signupVerify(contact: string, code: string): Promise<ReponseVerification> {
    const reponse = await firstValueFrom(
      this.http.post<ReponseVerification>(
        `${environment.apiUrl}/auth/signup/verify/`,
        { contact, code }
      )
    );

    // Après vérification réussie, on connecte l'utilisateur avec le profil
    // renvoyé par le backend (le JWT ne contient ni nom, ni e-mail, ni rôle).
    this.stocker(this.versUtilisateurVerification(reponse), reponse.refresh);
    return reponse;
  }

  /** Envoie un code de vérification pour la connexion */
  async loginSendCode(contact: string, contact_type: 'email' | 'sms'): Promise<{ message: string; expires_in: number }> {
    return firstValueFrom(
      this.http.post<{ message: string; expires_in: number }>(
        `${environment.apiUrl}/auth/login/send-code/`,
        { contact, contact_type }
      )
    );
  }

  /** Vérifie le code de connexion */
  async loginVerify(contact: string, code: string): Promise<ReponseVerification> {
    const reponse = await firstValueFrom(
      this.http.post<ReponseVerification>(
        `${environment.apiUrl}/auth/login/verify/`,
        { contact, code }
      )
    );

    this.stocker(this.versUtilisateurVerification(reponse), reponse.refresh);
    return reponse;
  }

  /** Renvoie un nouveau code de vérification */
  async resendCode(contact: string): Promise<{ message: string; expires_in: number }> {
    return firstValueFrom(
      this.http.post<{ message: string; expires_in: number }>(
        `${environment.apiUrl}/auth/resend-code/`,
        { contact }
      )
    );
  }

  // --- Interne ---

  /**
   * Profil applicatif à partir de la réponse OTP.
   *
   * Le backend renvoie le profil complet (`user`) : on l'utilise tel quel.
   * Repli sur le décodage du JWT pour une réponse anciennement mise en cache.
   */
  private versUtilisateurVerification(reponse: ReponseVerification): Utilisateur {
    if (reponse.user) {
      return this.versUtilisateurApi(reponse.user, reponse.access);
    }
    return this.versUtilisateurDepuisToken(reponse.access);
  }

  /** Crée un utilisateur à partir du token JWT (payload décodé) */
  private versUtilisateurDepuisToken(token: string): Utilisateur {
    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      return {
        id: payload.sub || 'u-unknown',
        nom: payload.nom || 'Utilisateur',
        email: payload.email || '',
        role: VERS_ROLE[payload.role as RoleApi] ?? 'client',
        initiales: this.initiales(payload.nom || 'U'),
        token,
      };
    } catch {
      return {
        id: 'u-unknown',
        nom: 'Utilisateur',
        email: '',
        role: 'client',
        initiales: 'U',
        token,
      };
    }
  }

  /** Connexion de démonstration (mode mock) : utilisateur factice + JWT non signé. */
  connexionDemo(role: UserRole = 'client'): Utilisateur {
    const utilisateur: Utilisateur = {
      id: 'u-demo',
      nom: role === 'client' ? 'Client Démo' : `Démo ${role}`,
      email: `${role}@lazani.betsileo`,
      role,
      token: this.fauxJwt(role),
    };
    this.stocker(utilisateur);
    return utilisateur;
  }

  /** Déconnexion : purge le stockage et redirige. */
  deconnexion(retourUrl = '/'): void {
    localStorage.removeItem(CLE_TOKEN);
    localStorage.removeItem(CLE_REFRESH);
    localStorage.removeItem(CLE_UTILISATEUR);
    this.utilisateurSig.set(null);
    void this.router.navigateByUrl(retourUrl);
  }

  /** Le rôle courant est-il dans la liste autorisée ? */
  aRole(...roles: UserRole[]): boolean {
    const r = this.role();
    return r !== null && roles.includes(r);
  }

  /** Vérifie que l'utilisateur possède un rôle (utilisé par RoleGuard). */
  hasRole(roles: UserRole[]): boolean {
    return this.aRole(...roles);
  }

  // --- Interne ---

  /** Profil Django → modèle applicatif (rôle, nom complet, porteur JWT). */
  private versUtilisateurApi(api: UtilisateurApi, token: string): Utilisateur {
    const nom = [api.first_name, api.last_name].filter(Boolean).join(' ').trim() || api.username;
    return {
      id: String(api.id),
      nom,
      // Compte créé par SMS seul : l'API renvoie ``null`` faute d'e-mail.
      email: api.email ?? '',
      telephone: api.telephone ?? '',
      avatarUrl: api.avatar_url ?? '',
      role: VERS_ROLE[api.role] ?? 'client',
      initiales: this.initiales(nom),
      token,
    };
  }

  /** Initiales du badge de profil (2 premières lettres des 2 premiers mots). */
  private initiales(nom: string): string {
    return nom
      .split(' ')
      .filter(Boolean)
      .slice(0, 2)
      .map((mot) => mot[0]?.toUpperCase() ?? '')
      .join('');
  }

  private stocker(utilisateur: Utilisateur, refresh?: string): void {
    localStorage.setItem(CLE_TOKEN, utilisateur.token ?? '');
    if (refresh) localStorage.setItem(CLE_REFRESH, refresh);
    localStorage.setItem(CLE_UTILISATEUR, JSON.stringify(utilisateur));
    this.utilisateurSig.set(utilisateur);
  }

  private reprendre(): Utilisateur | null {
    try {
      const brut = localStorage.getItem(CLE_UTILISATEUR);
      if (!brut) return null;
      const parse: unknown = JSON.parse(brut);
      if (!estUtilisateur(parse)) {
        // Donnée corrompue ou d'une version antérieure : on purge.
        localStorage.removeItem(CLE_UTILISATEUR);
        localStorage.removeItem(CLE_TOKEN);
        return null;
      }
      return parse;
    } catch {
      return null;
    }
  }

  /** Construit un JWT factice : header.base64(payload).signature */
  private fauxJwt(role: UserRole): string {
    const encoder = (o: object) => btoa(JSON.stringify(o)).replace(/=+$/, '');
    const header = encoder({ alg: 'HS256', typ: 'JWT' });
    const payload = encoder({
      sub: 'u-demo',
      role,
      exp: Math.floor(Date.now() / 1000) + 3600 * 8,
    });
    return `${header}.${payload}.demo-signature`;
  }
}