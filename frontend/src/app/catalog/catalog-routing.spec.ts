import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { routes } from '../app.routes';
import { authInterceptor } from '../auth/auth.interceptor';
import { AuthService, SESSION_KEY } from '../auth/auth.service';

describe('Navegación pública del catálogo', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    sessionStorage.removeItem(SESSION_KEY);
    TestBed.configureTestingModule({ providers: [
      provideRouter(routes), provideHttpClient(withInterceptors([authInterceptor])),
      provideHttpClientTesting(),
    ] });
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => { http.verify(); vi.restoreAllMocks(); });

  it('abre listado y detalle con las rutas reales sin restaurar una sesión administrativa', async () => {
    const ensureSession = vi.spyOn(TestBed.inject(AuthService), 'ensureSession');
    const harness = await RouterTestingHarness.create('/catalogo');
    const list = http.expectOne(request => request.url === '/api/catalogo/productos');
    expect(list.request.headers.has('Authorization')).toBe(false);
    list.flush({ items: [], total: 0, limit: 20, offset: 0 });
    harness.detectChanges();
    expect(harness.routeNativeElement?.querySelector('header')?.textContent).toContain('VestiNova');
    expect(harness.routeNativeElement?.querySelector('main')).not.toBeNull();
    expect(ensureSession).not.toHaveBeenCalled();

    await harness.navigateByUrl('/catalogo/prenda-inexistente');
    http.expectOne('/api/catalogo/productos/prenda-inexistente').flush({}, { status: 404, statusText: 'Not Found' });
    harness.detectChanges();
    expect(harness.routeNativeElement?.textContent).toContain('Producto no disponible');
    expect(harness.routeNativeElement?.querySelector('.catalog-back')?.getAttribute('href')).toBe('/catalogo');
    expect(ensureSession).not.toHaveBeenCalled();
    http.expectNone(request => request.url.startsWith('/api/admin/') || request.url.startsWith('/api/auth/'));
  });
});
