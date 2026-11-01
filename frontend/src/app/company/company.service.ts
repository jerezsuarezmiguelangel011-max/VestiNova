import { isPlatformBrowser } from '@angular/common';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, PLATFORM_ID, computed, inject, signal } from '@angular/core';
import { Observable, Subject, catchError, defer, filter, finalize, map, of, shareReplay, takeUntil, throwError } from 'rxjs';

export interface Company {
  id: number;
  nombre: string;
  slug: string;
  activo: boolean;
  rol: 'ADMINISTRADOR' | 'ENCARGADO_SUCURSAL' | 'CAJERO' | 'OPERADOR';
}

export const COMPANY_KEY = 'vestinova_mvp_empresa';

@Injectable({ providedIn: 'root' })
export class CompanyService {
  private readonly http = inject(HttpClient);
  private readonly browser = isPlatformBrowser(inject(PLATFORM_ID));
  private readonly selected = signal<Company | null>(null);
  readonly active = this.selected.asReadonly();
  readonly companies = signal<Company[]>([]);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly revision = signal(0);
  readonly canManage = computed(() => this.active()?.rol === 'ADMINISTRADOR');
  readonly canViewProducts = computed(() => ['ADMINISTRADOR', 'OPERADOR'].includes(this.active()?.rol ?? ''));
  private readonly changed = new Subject<number>();
  readonly changes$ = this.changed.asObservable();
  private userId: number | null = null;
  private checked = false;
  private pending: Observable<boolean> | undefined;

  bindUser(userId: number): void {
    if (this.userId === userId) return;
    this.userId = userId;
    this.checked = false;
    this.pending = undefined;
    this.companies.set([]);
    this.error.set(null);
    this.loading.set(false);
    this.change(null);
    const remembered = this.remembered();
    if (remembered && remembered.usuario_id !== userId) this.forget();
  }

  clear(): void {
    this.userId = null;
    this.checked = false;
    this.pending = undefined;
    this.companies.set([]);
    this.loading.set(false);
    this.error.set(null);
    this.forget();
    this.change(null);
  }

  ensureForUser(userId: number): Observable<boolean> {
    this.bindUser(userId);
    if (this.checked) return of(true);
    if (this.pending) return this.pending;
    const revision = this.revision();
    const principal = this.userId;
    this.loading.set(true);
    this.error.set(null);
    const request = this.http.get<unknown>('/api/empresas').pipe(
      takeUntil(this.changes$.pipe(filter(value => value !== revision))),
      map(response => {
        if (principal !== this.userId || revision !== this.revision()) return false;
        if (!Array.isArray(response) || !response.every(value => this.validCompany(value))) {
          throw new Error('Respuesta de empresas no compatible.');
        }
        const companies = response as Company[];
        this.companies.set(companies);
        this.checked = true;
        const remembered = this.remembered();
        const saved = remembered?.usuario_id === principal ? companies.find(value => value.id === remembered.empresa_id) : undefined;
        const choice = saved ?? (companies.length === 1 ? companies[0] : null);
        this.selected.set(choice);
        if (choice) this.remember(choice.id); else this.forget();
        // The principal revision was emitted when binding; this is its validated
        // first selection. Later explicit changes always increment the revision.
        return true;
      }),
      catchError(() => {
        if (principal === this.userId && revision === this.revision()) {
          this.error.set('No pudimos consultar tus empresas. Revisa la conexión e inténtalo nuevamente.');
          this.selected.set(null);
        }
        return of(false);
      }),
      finalize(() => {
        if (this.pending === request) { this.pending = undefined; this.loading.set(false); }
      }),
      shareReplay({ bufferSize: 1, refCount: true }),
    );
    this.pending = request;
    return request;
  }

  refresh(): Observable<boolean> {
    if (this.userId === null) return of(false);
    const principal = this.userId;
    this.checked = false;
    this.pending = undefined;
    this.change(null);
    return this.ensureForUser(principal);
  }

  select(companyId: number): boolean {
    const company = this.companies().find(value => value.id === companyId);
    if (!company || !this.checked || this.loading() || this.userId === null) return false;
    if (company.id !== this.active()?.id || company.rol !== this.active()?.rol) this.change(company);
    this.remember(company.id);
    return true;
  }

  scoped<T>(factory: (company: Company) => Observable<T>): Observable<T> {
    return defer(() => {
      const company = this.active();
      if (!company) return throwError(() => new HttpErrorResponse({ status: 403, error: { detail: 'Selecciona una empresa autorizada antes de continuar.' } }));
      const revision = this.revision();
      return factory(company).pipe(takeUntil(this.changes$.pipe(filter(value => value !== revision))));
    });
  }

  private change(company: Company | null): void {
    this.selected.set(company);
    const revision = this.revision() + 1;
    this.revision.set(revision);
    this.changed.next(revision);
  }

  private validCompany(value: unknown): value is Company {
    if (!value || typeof value !== 'object') return false;
    const item = value as Company;
    return Number.isSafeInteger(item.id) && item.id > 0 && typeof item.nombre === 'string' && typeof item.slug === 'string' && item.activo === true && ['ADMINISTRADOR', 'ENCARGADO_SUCURSAL', 'CAJERO', 'OPERADOR'].includes(item.rol);
  }

  private remembered(): { usuario_id: number; empresa_id: number } | null {
    try {
      const item = this.browser ? JSON.parse(sessionStorage.getItem(COMPANY_KEY) ?? 'null') : null;
      return Number.isSafeInteger(item?.usuario_id) && Number.isSafeInteger(item?.empresa_id) ? item : null;
    } catch { return null; }
  }

  private remember(companyId: number): void {
    try { if (this.browser) sessionStorage.setItem(COMPANY_KEY, JSON.stringify({ usuario_id: this.userId, empresa_id: companyId })); } catch { /* Selección en memoria cuando el almacenamiento está bloqueado. */ }
  }

  private forget(): void {
    try { if (this.browser) sessionStorage.removeItem(COMPANY_KEY); } catch { /* Storage puede estar bloqueado. */ }
  }
}
