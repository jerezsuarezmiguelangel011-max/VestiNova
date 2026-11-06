import { Injectable, computed, signal } from '@angular/core';

/**
 * El ámbito de navegación pública pertenece a una empresa. Elegir sucursal
 * NO restringe el catálogo ni autoriza operaciones: solo preselecciona
 * dónde consultar existencias. El servidor valida siempre empresa y sucursal.
 */
@Injectable({ providedIn: 'root' })
export class StorefrontContextService {
  readonly company = signal<string | null>(null);
  readonly branch = signal<number | null>(null);
  readonly hasBranchFilter = computed(() => this.branch() !== null);

  selectCompany(slug: string): void {
    if (this.company() === slug) return;
    this.company.set(slug);
    this.branch.set(null);
  }

  selectBranch(branchId: number | null, allowedIds: readonly number[]): void {
    this.branch.set(branchId !== null && allowedIds.includes(branchId) ? branchId : null);
  }
}
