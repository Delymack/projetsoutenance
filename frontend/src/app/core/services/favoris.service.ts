import { Injectable, computed, signal } from '@angular/core';

const CLE_FAVORIS = 'lb.favoris';

@Injectable({ providedIn: 'root' })
export class FavorisService {
  private readonly idsSig = signal<Set<string>>(this.restaurer());

  readonly ids = computed(() => [...this.idsSig()]);
  readonly total = computed(() => this.idsSig().size);

  estFavori(vinId: string): boolean {
    return this.idsSig().has(vinId);
  }

  basculer(vinId: string): boolean {
    const prochain = new Set(this.idsSig());
    const actif = !prochain.has(vinId);
    if (actif) {
      prochain.add(vinId);
    } else {
      prochain.delete(vinId);
    }
    this.idsSig.set(prochain);
    this.persist(prochain);
    return actif;
  }

  retirer(vinId: string): void {
    if (!this.idsSig().has(vinId)) return;
    const prochain = new Set(this.idsSig());
    prochain.delete(vinId);
    this.idsSig.set(prochain);
    this.persist(prochain);
  }

  vider(): void {
    this.idsSig.set(new Set());
    localStorage.removeItem(CLE_FAVORIS);
  }

  private restaurer(): Set<string> {
    try {
      const brut = localStorage.getItem(CLE_FAVORIS);
      const ids = brut ? (JSON.parse(brut) as unknown) : [];
      return new Set(Array.isArray(ids) ? ids.filter((id): id is string => typeof id === 'string') : []);
    } catch {
      return new Set();
    }
  }

  private persist(ids: Set<string>): void {
    localStorage.setItem(CLE_FAVORIS, JSON.stringify([...ids]));
  }
}
