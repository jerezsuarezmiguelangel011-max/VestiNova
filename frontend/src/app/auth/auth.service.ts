import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, PLATFORM_ID, inject, signal } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { Observable, catchError, defer, filter, finalize, map, of, shareReplay, tap, throwError } from 'rxjs';
import { Administrator, LoginCredentials, LoginResponse } from './auth.models';
import { CompanyService } from '../company/company.service';

export const SESSION_KEY = 'vestinova_mvp_session';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly browser = isPlatformBrowser(inject(PLATFORM_ID));
  private readonly companies = inject(CompanyService);
  private readonly currentUser = signal<Administrator | null>(null);
  readonly user = this.currentUser.asReadonly();
  private currentToken = this.readStoredToken();
  private checked = false;
  private revision = 0;
  private restoring: Observable<Administrator | null> | undefined;

  token(): string | null { return this.currentToken; }

  ensureSession(): Observable<Administrator | null> {
    if (this.checked) return of(this.currentUser());
    if (!this.currentToken) { this.checked = true; return of(null); }
    if (this.restoring) return this.restoring;
    const revision = this.revision;
    const restoration = this.http.get<Administrator>('/api/auth/me').pipe(
      map(administrator => {
        if (revision !== this.revision) return null;
        this.currentUser.set(administrator);
        this.companies.bindUser(administrator.id);
        this.checked = true;
        return administrator;
      }),
      catchError((error: unknown) => {
        if (revision !== this.revision) return of(null);
        if (error instanceof HttpErrorResponse && [401, 403].includes(error.status)) {
          this.invalidate();
          return of(null);
        }
        return throwError(() => error);
      }),
      finalize(() => { if (this.restoring === restoration) this.restoring = undefined; }),
      shareReplay({ bufferSize: 1, refCount: false }),
    );
    this.restoring = restoration;
    return restoration;
  }

  login(credentials: LoginCredentials): Observable<Administrator> {
    const revision = ++this.revision;
    this.restoring = undefined;
    return this.http.post<LoginResponse>('/api/auth/login', credentials).pipe(
      filter(() => revision === this.revision),
      tap(response => {
        if (revision !== this.revision) return;
        this.currentToken = response.access_token;
        this.currentUser.set(response.administrador);
        this.companies.clear();
        this.companies.bindUser(response.administrador.id);
        this.checked = true;
        try { if (this.browser) sessionStorage.setItem(SESSION_KEY, response.access_token); } catch { /* Sesión en memoria. */ }
      }),
      map(response => response.administrador),
    );
  }

  logout(): Observable<void> {
    return defer(() => {
      const revision = this.revision;
      return this.http.post<void>('/api/auth/logout', null).pipe(filter(() => revision === this.revision), tap(() => this.invalidate()));
    });
  }

  invalidate(): void {
    this.revision++;
    this.currentToken = null;
    this.currentUser.set(null);
    this.checked = true;
    this.restoring = undefined;
    this.companies.clear();
    try { if (this.browser) sessionStorage.removeItem(SESSION_KEY); } catch { /* Storage puede estar bloqueado. */ }
  }

  private readStoredToken(): string | null {
    try { return this.browser ? sessionStorage.getItem(SESSION_KEY) : null; } catch { return null; }
  }
}
