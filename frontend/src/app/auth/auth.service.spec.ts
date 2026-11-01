import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { AuthService, SESSION_KEY } from './auth.service';
import { Administrator } from './auth.models';
import { CompanyService, COMPANY_KEY } from '../company/company.service';

const ADMIN: Administrator = { id: 1, nombre: 'Administración', correo: 'admin@vestinova.test', rol: 'ADMINISTRADOR' };
const LOGIN = { access_token: 'token-local-prueba', token_type: 'bearer', expires_at: '2026-10-25T12:00:00Z', administrador: ADMIN };

describe('Sesión del administrador', () => {
  let http: HttpTestingController;
  beforeEach(() => {
    sessionStorage.clear();
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => { http.verify(); sessionStorage.clear(); vi.restoreAllMocks(); });

  it('guarda solo el token de una respuesta válida y conserva la contraseña exacta enviada', () => {
    const auth = TestBed.inject(AuthService);
    auth.login({ correo: ADMIN.correo, password: ' Clave de prueba ' }).subscribe();
    const request = http.expectOne('/api/auth/login');
    expect(request.request.method).toBe('POST');
    expect(request.request.body.password).toBe(' Clave de prueba ');
    request.flush(LOGIN);
    expect(auth.user()).toEqual(ADMIN);
    expect(sessionStorage.getItem(SESSION_KEY)).toBe(LOGIN.access_token);
    expect(sessionStorage.length).toBe(1);
  });

  it('restaura con /me antes de exponer identidad y comparte consultas concurrentes', () => {
    sessionStorage.setItem(SESSION_KEY, 'token-previo');
    const auth = TestBed.inject(AuthService);
    const identities: unknown[] = [];
    auth.ensureSession().subscribe(user => identities.push(user));
    auth.ensureSession().subscribe(user => identities.push(user));
    expect(auth.user()).toBeNull();
    http.expectOne('/api/auth/me').flush(ADMIN);
    expect(identities).toEqual([ADMIN, ADMIN]);
    auth.ensureSession().subscribe();
    http.expectNone('/api/auth/me');
  });

  it('no consulta ni permite restaurar una sesión sin token', () => {
    const auth = TestBed.inject(AuthService);
    let identity: unknown = 'sin-respuesta';
    auth.ensureSession().subscribe(user => identity = user);
    expect(identity).toBeNull();
    http.expectNone('/api/auth/me');
  });

  it('elimina el token rechazado por el servidor', () => {
    sessionStorage.setItem(SESSION_KEY, 'revocado');
    const auth = TestBed.inject(AuthService);
    let identity: unknown = 'sin-respuesta';
    auth.ensureSession().subscribe(user => identity = user);
    http.expectOne('/api/auth/me').flush({ detail: 'Sesión no válida' }, { status: 401, statusText: 'Unauthorized' });
    expect(identity).toBeNull();
    expect(auth.token()).toBeNull();
    expect(sessionStorage.getItem(SESSION_KEY)).toBeNull();
  });

  it('conserva el token ante una caída temporal y permite reintentar /me', () => {
    sessionStorage.setItem(SESSION_KEY, 'válido');
    const auth = TestBed.inject(AuthService);
    auth.ensureSession().subscribe({ error: () => undefined });
    http.expectOne('/api/auth/me').flush({}, { status: 503, statusText: 'Unavailable' });
    expect(auth.token()).toBe('válido');
    auth.ensureSession().subscribe();
    http.expectOne('/api/auth/me').flush(ADMIN);
    expect(auth.user()).toEqual(ADMIN);
  });

  it('cierra la sesión después de la revocación y limpia el almacenamiento', () => {
    sessionStorage.setItem(SESSION_KEY, 'token');
    const auth = TestBed.inject(AuthService);
    auth.logout().subscribe();
    const request = http.expectOne('/api/auth/logout');
    expect(request.request.method).toBe('POST');
    expect(auth.token()).toBe('token');
    request.flush(null, { status: 204, statusText: 'No Content' });
    expect(auth.user()).toBeNull();
    expect(auth.token()).toBeNull();
    expect(sessionStorage.getItem(SESSION_KEY)).toBeNull();
  });

  it('mantiene la sesión si no se pudo revocar para permitir reintentar el cierre', () => {
    sessionStorage.setItem(SESSION_KEY, 'token');
    const auth = TestBed.inject(AuthService);
    auth.logout().subscribe({ error: () => undefined });
    http.expectOne('/api/auth/logout').flush({}, { status: 503, statusText: 'Unavailable' });
    expect(auth.token()).toBe('token');
  });

  it('una respuesta /me tardía no restaura una sesión invalidada', () => {
    sessionStorage.setItem(SESSION_KEY, 'token');
    const auth = TestBed.inject(AuthService);
    auth.ensureSession().subscribe();
    const request = http.expectOne('/api/auth/me');
    auth.invalidate();
    request.flush(ADMIN);
    expect(auth.user()).toBeNull();
    expect(auth.token()).toBeNull();
  });

  it('un login tardío no reactiva ni emite una identidad invalidada', () => {
    const auth = TestBed.inject(AuthService);
    const emitted = vi.fn();
    auth.login({ correo: ADMIN.correo, password: 'clave' }).subscribe(emitted);
    const request = http.expectOne('/api/auth/login');
    auth.invalidate();
    request.flush(LOGIN);
    expect(auth.user()).toBeNull();
    expect(auth.token()).toBeNull();
    expect(emitted).not.toHaveBeenCalled();
  });

  it('un logout tardío no borra la identidad ni empresa de una sesión nueva', () => {
    const auth = TestBed.inject(AuthService);
    auth.login({ correo: ADMIN.correo, password: 'clave' }).subscribe();
    http.expectOne('/api/auth/login').flush(LOGIN);
    const closed = vi.fn();
    auth.logout().subscribe(closed);
    const logout = http.expectOne('/api/auth/logout');
    auth.login({ correo: ADMIN.correo, password: 'otra' }).subscribe();
    http.expectOne('/api/auth/login').flush({ ...LOGIN, access_token: 'sesion-nueva' });
    const companies = TestBed.inject(CompanyService);
    companies.ensureForUser(ADMIN.id).subscribe();
    http.expectOne('/api/empresas').flush([{ id: 5, nombre: 'Empresa nueva', slug: 'empresa', activo: true, rol: 'ADMINISTRADOR' }]);
    logout.flush(null, { status: 204, statusText: 'No Content' });
    expect(auth.token()).toBe('sesion-nueva');
    expect(auth.user()).toEqual(ADMIN);
    expect(companies.active()?.id).toBe(5);
    expect(closed).not.toHaveBeenCalled();
  });

  it('invalidar sesión retira también el contexto y su almacenamiento', () => {
    const auth = TestBed.inject(AuthService);
    auth.login({ correo: ADMIN.correo, password: 'clave' }).subscribe();
    http.expectOne('/api/auth/login').flush(LOGIN);
    const companies = TestBed.inject(CompanyService);
    companies.ensureForUser(ADMIN.id).subscribe();
    http.expectOne('/api/empresas').flush([{ id: 5, nombre: 'Empresa', slug: 'empresa', activo: true, rol: 'ADMINISTRADOR' }]);
    expect(sessionStorage.getItem(COMPANY_KEY)).not.toBeNull();
    auth.invalidate();
    expect(companies.active()).toBeNull();
    expect(sessionStorage.getItem(COMPANY_KEY)).toBeNull();
  });
});
