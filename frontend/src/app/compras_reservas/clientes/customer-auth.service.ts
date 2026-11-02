import { isPlatformBrowser } from '@angular/common';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, PLATFORM_ID, inject, signal } from '@angular/core';
import { Observable, Subject, catchError, defer, filter, finalize, map, of, shareReplay, takeUntil, throwError } from 'rxjs';
import { Customer, CustomerCredentials, CustomerLoginResponse, CustomerRegistration, PublicStore } from './customer.models';

export const CUSTOMER_SESSION_KEY = 'vestinova_mvp_cliente';
interface StoredCustomerSession { tienda: string; token: string; }

@Injectable({ providedIn: 'root' })
export class CustomerAuthService {
  private readonly http = inject(HttpClient);
  private readonly browser = isPlatformBrowser(inject(PLATFORM_ID));
  private session = this.readSession();
  private slug: string | null = null;
  private revision = 0;
  private checked = false;
  private readonly changed = new Subject<void>();
  private restoring: Observable<Customer | null> | undefined;
  private readonly identity = signal<Customer | null>(null);
  readonly customer = this.identity.asReadonly();

  token(slug: string): string | null { return this.session?.tienda === slug ? this.session.token : null; }
  store(slug: string): Observable<PublicStore> { return this.http.get<PublicStore>(this.base(slug)); }

  selectStore(slug: string): void {
    if (slug === this.slug) return;
    this.slug = slug; this.revision++; this.changed.next();
    this.identity.set(null); this.checked = false; this.restoring = undefined;
  }

  ensureSession(slug: string): Observable<Customer | null> {
    this.selectStore(slug);
    if (this.checked) return of(this.identity());
    const token = this.token(slug);
    if (!token) { this.checked = true; return of(null); }
    if (this.restoring) return this.restoring;
    const revision = this.revision;
    const request = this.http.get<Customer>(`${this.base(slug)}/cuenta/me`, { headers: { Authorization: `Bearer ${token}` } }).pipe(
      takeUntil(this.changed),
      map(customer => {
        if (revision !== this.revision) return null;
        this.checkIdentity(customer, slug);
        this.identity.set(customer); this.checked = true;
        return customer;
      }),
      catchError(error => {
        if (revision !== this.revision) return of(null);
        if (error instanceof HttpErrorResponse && [401, 403, 404].includes(error.status)) { this.invalidate(slug); return of(null); }
        this.identity.set(null);
        return throwError(() => error);
      }),
      finalize(() => { if (this.restoring === request) this.restoring = undefined; }),
      shareReplay({ bufferSize: 1, refCount: true }),
    );
    this.restoring = request;
    return request;
  }

  login(slug: string, credentials: CustomerCredentials): Observable<Customer> {
    return this.authenticate(slug, 'login', credentials);
  }
  register(slug: string, registration: CustomerRegistration): Observable<Customer> {
    return this.authenticate(slug, 'registro', registration);
  }

  logout(slug: string): Observable<void> {
    return defer(() => {
      const token = this.token(slug);
      if (!token) { this.invalidate(slug); return of(undefined); }
      const revision = this.revision;
      return this.http.post<void>(`${this.base(slug)}/cuenta/logout`, null, { headers: { Authorization: `Bearer ${token}` } }).pipe(
        takeUntil(this.changed), filter(() => revision === this.revision && token === this.token(slug)),
        catchError(error => {
          if (error instanceof HttpErrorResponse && error.status === 401 && revision === this.revision && token === this.token(slug)) {
            this.invalidate(slug); return of(undefined);
          }
          return throwError(() => error);
        }),
        map(() => { if (revision === this.revision) this.invalidate(slug, false); }),
      );
    });
  }

  invalidate(slug: string, cancelRequests = true): void {
    if (this.slug !== slug) return;
    this.revision++; if (cancelRequests) this.changed.next(); this.identity.set(null); this.checked = true; this.restoring = undefined;
    if (this.session?.tienda === slug) {
      this.session = null;
      try { if (this.browser) sessionStorage.removeItem(CUSTOMER_SESSION_KEY); } catch { /* Sesión en memoria. */ }
    }
  }

  private authenticate(slug: string, action: 'login' | 'registro', payload: CustomerCredentials | CustomerRegistration): Observable<Customer> {
    this.selectStore(slug);
    const revision = ++this.revision;
    this.changed.next(); this.restoring = undefined; this.identity.set(null); this.checked = false;
    return this.http.post<CustomerLoginResponse>(`${this.base(slug)}/cuenta/${action}`, payload).pipe(
      takeUntil(this.changed), filter(() => revision === this.revision),
      map(response => {
        this.checkIdentity(response.cliente, slug);
        if (!response.access_token || typeof response.access_token !== 'string') throw new Error('Sesión no compatible.');
        this.session = { tienda: slug, token: response.access_token };
        this.identity.set(response.cliente); this.checked = true;
        try { if (this.browser) sessionStorage.setItem(CUSTOMER_SESSION_KEY, JSON.stringify(this.session)); } catch { /* Sesión en memoria. */ }
        return response.cliente;
      }),
    );
  }

  private base(slug: string): string {
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)) throw new Error('Identificador de tienda no válido.');
    return `/api/tiendas/${encodeURIComponent(slug)}`;
  }
  private checkIdentity(customer: Customer, slug: string): void {
    if (!customer || customer.rol !== 'CLIENTE' || customer.empresa?.slug !== slug) throw new Error('Cuenta no compatible con esta tienda.');
  }
  private readSession(): StoredCustomerSession | null {
    try {
      const stored = this.browser ? JSON.parse(sessionStorage.getItem(CUSTOMER_SESSION_KEY) ?? 'null') : null;
      return typeof stored?.tienda === 'string' && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(stored.tienda)
        && typeof stored?.token === 'string' && stored.token.length > 0 ? stored : null;
    } catch { return null; }
  }
}
