import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { authInterceptor } from './auth.interceptor';
import { AuthService, SESSION_KEY } from './auth.service';
import { CompanyService } from '../company/company.service';

describe('Autorización HTTP del MVP', () => {
  let http: HttpTestingController;
  let client: HttpClient;
  beforeEach(() => {
    sessionStorage.setItem(SESSION_KEY, 'token-de-prueba');
    TestBed.configureTestingModule({ providers: [provideHttpClient(withInterceptors([authInterceptor])), provideHttpClientTesting(), provideRouter([])] });
    http = TestBed.inject(HttpTestingController);
    client = TestBed.inject(HttpClient);
  });
  afterEach(() => { http.verify(); sessionStorage.clear(); vi.restoreAllMocks(); });
  it('añade Bearer únicamente a la API propia y no al login ni URLs externas', () => {
    client.get('/api/admin/productos').subscribe();
    const own = http.expectOne('/api/admin/productos');
    expect(own.request.headers.get('Authorization')).toBe('Bearer token-de-prueba');
    own.flush([]);
    client.get('https://externo.test/imagen').subscribe();
    const external = http.expectOne('https://externo.test/imagen');
    expect(external.request.headers.has('Authorization')).toBe(false);
    external.flush({});
    client.get('/api/catalogo/productos').subscribe();
    const catalog = http.expectOne('/api/catalogo/productos');
    expect(catalog.request.headers.has('Authorization')).toBe(false);
    catalog.flush({ items: [] });
    TestBed.inject(AuthService).login({ correo: 'admin@vestinova.test', password: 'prueba' }).subscribe({ error: () => undefined });
    const login = http.expectOne('/api/auth/login');
    expect(login.request.headers.has('Authorization')).toBe(false);
    login.flush({}, { status: 401, statusText: 'Unauthorized' });
  });
  it('un 401 privado invalida la sesión y redirige al acceso', () => {
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    client.get('/api/admin/productos').subscribe({ error: () => undefined });
    http.expectOne('/api/admin/productos').flush({}, { status: 401, statusText: 'Unauthorized' });
    expect(TestBed.inject(AuthService).token()).toBeNull();
    expect(navigate).toHaveBeenCalledWith(['/admin/login'], { queryParams: { motivo: 'sesion' } });
  });
  it('un 403 no borra una sesión válida', () => {
    client.get('/api/admin/productos').subscribe({ error: () => undefined });
    http.expectOne('/api/admin/productos').flush({}, { status: 403, statusText: 'Forbidden' });
    expect(TestBed.inject(AuthService).token()).toBe('token-de-prueba');
  });

  it('envía empresa solo a recursos operacionales privados y conserva público/externos sin cabeceras', () => {
    const companies = TestBed.inject(CompanyService);
    companies.ensureForUser(1).subscribe();
    const companiesRequest = http.expectOne('/api/empresas');
    expect(companiesRequest.request.headers.get('Authorization')).toBe('Bearer token-de-prueba');
    expect(companiesRequest.request.headers.has('X-Empresa-Id')).toBe(false);
    companiesRequest.flush([{ id: 8, nombre: 'Empresa', slug: 'empresa', activo: true, rol: 'ADMINISTRADOR' }]);
    for (const url of ['/api/admin/productos?limit=20', '/api/movil/descarga']) {
      client.get(url).subscribe();
      const request = http.expectOne(url);
      expect(request.request.headers.get('X-Empresa-Id')).toBe('8');
      expect(request.request.headers.get('Authorization')).toBe('Bearer token-de-prueba');
      request.flush({});
    }
    for (const url of ['/api/catalogo/productos', '/api/empresas-falso', 'https://externo.test/api/admin/productos', '//externo.test/api/admin/productos']) {
      client.get(url).subscribe();
      const request = http.expectOne(url);
      expect(request.request.headers.has('X-Empresa-Id')).toBe(false);
      expect(request.request.headers.has('Authorization')).toBe(false);
      request.flush({});
    }
  });

  it('un 401 anterior no invalida el token de un login posterior', () => {
    const auth = TestBed.inject(AuthService);
    client.get('/api/admin/productos').subscribe({ error: () => undefined });
    const previous = http.expectOne('/api/admin/productos');
    auth.login({ correo: 'admin@vestinova.test', password: 'clave' }).subscribe();
    http.expectOne('/api/auth/login').flush({ access_token: 'nuevo-token', administrador: { id: 1, nombre: 'Admin', correo: 'admin@vestinova.test', rol: 'ADMINISTRADOR' } });
    previous.flush({}, { status: 401, statusText: 'Unauthorized' });
    expect(auth.token()).toBe('nuevo-token');
  });
});
