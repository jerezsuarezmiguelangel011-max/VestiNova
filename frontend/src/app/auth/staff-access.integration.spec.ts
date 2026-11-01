import { HttpRequest, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, TestRequest, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { routes } from '../app.routes';
import { authInterceptor } from './auth.interceptor';
import { SESSION_KEY } from './auth.service';

const STAFF = { id: 1, nombre: 'Personal de prueba', correo: 'personal@example.test', rol: 'ADMINISTRADOR', activo: true };
const COMPANY = { id: 10, nombre: 'Empresa A', slug: 'empresa-a', activo: true };

describe('Recorrido web de actores de personal con HTTP controlado', () => {
  let http: HttpTestingController;
  let harness: RouterTestingHarness;
  let router: Router;
  beforeEach(() => sessionStorage.clear());
  afterEach(() => { http?.verify(); sessionStorage.clear(); });
  async function setup() {
    sessionStorage.setItem(SESSION_KEY, 'token-personal');
    await TestBed.configureTestingModule({ providers: [provideRouter(routes), provideHttpClient(withInterceptors([authInterceptor])), provideHttpClientTesting()] }).compileComponents();
    http = TestBed.inject(HttpTestingController); router = TestBed.inject(Router); harness = await RouterTestingHarness.create();
  }
  async function request(match: string | ((request: HttpRequest<unknown>) => boolean)): Promise<TestRequest> {
    let found!: TestRequest; await vi.waitFor(() => { found = http.expectOne(match); }); return found;
  }
  function root(): HTMLElement { return harness.fixture.nativeElement as HTMLElement; }

  it.each(['ENCARGADO_SUCURSAL', 'CAJERO'])('dirige %s a sus sucursales autorizadas y protege URLs de escritura', async role => {
    await setup();
    const navigation = harness.navigateByUrl('/admin/productos/nuevo');
    (await request('/api/auth/me')).flush(STAFF);
    (await request('/api/empresas')).flush([{ ...COMPANY, rol: role }]);
    const context = await request('/api/auth/contexto');
    expect(context.request.headers.get('Authorization')).toBe('Bearer token-personal');
    expect(context.request.headers.get('X-Empresa-Id')).toBe('10');
    context.flush({ empresa: { ...COMPANY, rol: role }, sucursales: [{ id: 20, empresa_id: 10, nombre: 'Sucursal autorizada', codigo: 'CENTRO', activo: true }] });
    await navigation; await harness.fixture.whenStable(); harness.detectChanges();
    expect(router.url.split('?')[0]).toBe('/admin/acceso');
    expect(root().textContent).toContain('Sucursal autorizada');
    expect(root().querySelector('a[href="/admin/productos"]:not(.rail__brand)')).toBeNull();
    http.expectNone(value => value.url.startsWith('/api/admin/productos'));
    http.expectNone(value => value.url.includes('/inventario/'));
  });

  it('restaura superadministración sin conceder empresas automáticamente', async () => {
    await setup();
    const navigation = harness.navigateByUrl('/admin/plataforma');
    (await request('/api/auth/me')).flush({ ...STAFF, es_superadministrador: true });
    await navigation; await harness.fixture.whenStable(); harness.detectChanges();
    expect(router.url).toBe('/admin/plataforma');
    expect(root().textContent).toContain('Acceso de superadministración');
    expect(root().textContent).toContain('Los permisos de plataforma y de cada empresa se validan por separado.');
    http.expectNone('/api/empresas');
    http.expectNone(value => value.url.startsWith('/api/plataforma/'));
  });

  it('un administrador empresarial sin privilegio SaaS no entra a la plataforma', async () => {
    await setup();
    const navigation = harness.navigateByUrl('/admin/plataforma');
    (await request('/api/auth/me')).flush({ ...STAFF, es_superadministrador: false });
    (await request('/api/empresas')).flush([{ ...COMPANY, rol: 'ADMINISTRADOR' }]);
    await navigation; await harness.fixture.whenStable(); harness.detectChanges();
    expect(router.url).toBe('/admin/empresa');
    expect(root().textContent).not.toContain('Acceso de superadministración');
  });
});
