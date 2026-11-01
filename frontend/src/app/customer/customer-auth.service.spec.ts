import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { authInterceptor } from '../auth/auth.interceptor';
import { AuthService, SESSION_KEY } from '../auth/auth.service';
import { CUSTOMER_SESSION_KEY, CustomerAuthService } from './customer-auth.service';
import { Customer } from './customer.models';

const CLIENT: Customer = { id: 1, nombre: 'Cliente de prueba', correo: 'cliente@example.test', rol: 'CLIENTE', empresa: { slug: 'tienda-a', nombre: 'Tienda A' } };
const LOGIN = { access_token: 'token-cliente-a', token_type: 'bearer', expires_at: '2026-10-25T23:00:00Z', cliente: CLIENT };

describe('Cuenta del cliente por tienda con HTTP controlado', () => {
  let http: HttpTestingController;
  beforeEach(() => {
    sessionStorage.clear();
    TestBed.configureTestingModule({ providers: [provideHttpClient(withInterceptors([authInterceptor])), provideHttpClientTesting(), provideRouter([])] });
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => { http.verify(); sessionStorage.clear(); vi.restoreAllMocks(); });
  function saved() { sessionStorage.setItem(CUSTOMER_SESSION_KEY, JSON.stringify({ tienda: 'tienda-a', token: LOGIN.access_token })); }
  function signIn() {
    const auth = TestBed.inject(CustomerAuthService);
    auth.login('tienda-a', { correo: CLIENT.correo, password: 'a' }).subscribe();
    http.expectOne('/api/tiendas/tienda-a/cuenta/login').flush(LOGIN);
    return auth;
  }

  it('registra sin empresa_id ni rol y conserva exactamente la contraseña enviada', () => {
    const auth = TestBed.inject(CustomerAuthService);
    auth.register('tienda-a', { nombre: CLIENT.nombre, correo: CLIENT.correo, password: ' Abc123! ' }).subscribe();
    const registration = http.expectOne('/api/tiendas/tienda-a/cuenta/registro');
    expect(registration.request.body).toEqual({ nombre: CLIENT.nombre, correo: CLIENT.correo, password: ' Abc123! ' });
    expect(registration.request.headers.has('Authorization')).toBe(false);
    expect(registration.request.headers.has('X-Empresa-Id')).toBe(false);
    registration.flush(LOGIN, { status: 201, statusText: 'Created' });
    expect(auth.customer()).toEqual(CLIENT);
    expect(JSON.parse(sessionStorage.getItem(CUSTOMER_SESSION_KEY)!)).toEqual({ tienda: 'tienda-a', token: LOGIN.access_token });
    expect(sessionStorage.getItem(SESSION_KEY)).toBeNull();
  });

  it('restaura solo con /me antes de exponer identidad y comparte la petición', () => {
    saved();
    const auth = TestBed.inject(CustomerAuthService);
    const identities: unknown[] = [];
    auth.ensureSession('tienda-a').subscribe(value => identities.push(value));
    auth.ensureSession('tienda-a').subscribe(value => identities.push(value));
    expect(auth.customer()).toBeNull();
    const me = http.expectOne('/api/tiendas/tienda-a/cuenta/me');
    expect(me.request.headers.get('Authorization')).toBe(`Bearer ${LOGIN.access_token}`);
    expect(me.request.headers.has('X-Empresa-Id')).toBe(false);
    me.flush(CLIENT);
    expect(identities).toEqual([CLIENT, CLIENT]);
  });

  it('no utiliza el token de A para consultar la cuenta de B', () => {
    saved();
    const auth = TestBed.inject(CustomerAuthService);
    const result = vi.fn();
    auth.ensureSession('tienda-b').subscribe(result);
    http.expectNone('/api/tiendas/tienda-b/cuenta/me');
    expect(result).toHaveBeenCalledWith(null);
    expect(auth.customer()).toBeNull();
    expect(auth.token('tienda-b')).toBeNull();
  });

  it('el token del cliente no se envía a personal, catálogo, metadata ni destinos externos', () => {
    signIn();
    const client = TestBed.inject(HttpClient);
    for (const url of ['/api/auth/me', '/api/admin/productos', '/api/empresas', '/api/plataforma/empresas', '/api/catalogo/productos', '/api/tiendas/tienda-a', 'https://externo.test/api/admin/productos']) {
      client.get(url).subscribe();
      const request = http.expectOne(url);
      expect(request.request.headers.has('Authorization')).toBe(false);
      expect(request.request.headers.has('X-Empresa-Id')).toBe(false);
      request.flush({});
    }
    expect(TestBed.inject(AuthService).token()).toBeNull();
  });

  it('mantiene las identidades de personal y cliente separadas sin filtrar el token de personal a tienda', () => {
    sessionStorage.setItem(SESSION_KEY, 'token-personal');
    const staff = TestBed.inject(AuthService);
    const customer = TestBed.inject(CustomerAuthService);
    customer.login('tienda-a', { correo: CLIENT.correo, password: 'x' }).subscribe();
    const login = http.expectOne('/api/tiendas/tienda-a/cuenta/login');
    expect(login.request.headers.has('Authorization')).toBe(false);
    login.flush(LOGIN);
    customer.logout('tienda-a').subscribe();
    const close = http.expectOne('/api/tiendas/tienda-a/cuenta/logout');
    expect(close.request.headers.get('Authorization')).toBe(`Bearer ${LOGIN.access_token}`);
    close.flush(null, { status: 204, statusText: 'No Content' });
    expect(staff.token()).toBe('token-personal');
  });

  it('un /me rechazado borra solo la sesión del cliente y un 503 permite reintentar sin exponer identidad', () => {
    saved();
    const auth = TestBed.inject(CustomerAuthService);
    auth.ensureSession('tienda-a').subscribe({ error: () => undefined });
    http.expectOne('/api/tiendas/tienda-a/cuenta/me').flush({}, { status: 503, statusText: 'Unavailable' });
    expect(auth.customer()).toBeNull();
    expect(auth.token('tienda-a')).toBe(LOGIN.access_token);
    auth.ensureSession('tienda-a').subscribe();
    http.expectOne('/api/tiendas/tienda-a/cuenta/me').flush({}, { status: 401, statusText: 'Unauthorized' });
    expect(auth.customer()).toBeNull();
    expect(auth.token('tienda-a')).toBeNull();
    expect(sessionStorage.getItem(CUSTOMER_SESSION_KEY)).toBeNull();
  });

  it('un cierre fallido conserva el token para reintentar y lo retira solo al confirmar revocación', () => {
    const auth = signIn();
    auth.logout('tienda-a').subscribe({ error: () => undefined });
    http.expectOne('/api/tiendas/tienda-a/cuenta/logout').flush({}, { status: 503, statusText: 'Unavailable' });
    expect(auth.customer()).toEqual(CLIENT);
    const closed = vi.fn();
    auth.logout('tienda-a').subscribe(closed);
    http.expectOne('/api/tiendas/tienda-a/cuenta/logout').flush(null, { status: 204, statusText: 'No Content' });
    expect(closed).toHaveBeenCalledOnce();
    expect(auth.customer()).toBeNull();
    expect(sessionStorage.getItem(CUSTOMER_SESSION_KEY)).toBeNull();
  });

  it('cambiar de tienda cancela un login pendiente y no deja reaparecer identidad de A', () => {
    const auth = TestBed.inject(CustomerAuthService);
    const emitted = vi.fn();
    auth.login('tienda-a', { correo: CLIENT.correo, password: 'x' }).subscribe(emitted);
    const pending = http.expectOne('/api/tiendas/tienda-a/cuenta/login');
    auth.selectStore('tienda-b');
    expect(pending.cancelled).toBe(true);
    expect(auth.customer()).toBeNull();
    expect(emitted).not.toHaveBeenCalled();
  });

  it('un cierre anterior no borra una sesión nueva', () => {
    const auth = signIn();
    auth.logout('tienda-a').subscribe();
    const close = http.expectOne('/api/tiendas/tienda-a/cuenta/logout');
    auth.login('tienda-a', { correo: CLIENT.correo, password: 'y' }).subscribe();
    expect(close.cancelled).toBe(true);
    http.expectOne('/api/tiendas/tienda-a/cuenta/login').flush({ ...LOGIN, access_token: 'sesion-nueva' });
    expect(auth.token('tienda-a')).toBe('sesion-nueva');
    expect(auth.customer()).toEqual(CLIENT);
  });

  it('rechaza una respuesta de cuenta de otra tienda o con rol de personal', () => {
    const auth = TestBed.inject(CustomerAuthService);
    const error = vi.fn();
    auth.login('tienda-a', { correo: CLIENT.correo, password: 'x' }).subscribe({ error });
    http.expectOne('/api/tiendas/tienda-a/cuenta/login').flush({ ...LOGIN, cliente: { ...CLIENT, rol: 'ADMINISTRADOR' } });
    expect(error).toHaveBeenCalledOnce();
    expect(auth.customer()).toBeNull();
    expect(auth.token('tienda-a')).toBeNull();
  });
});
