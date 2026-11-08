import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { CompanyService } from '../organizacion_empresarial/empresa/company.service';
import { CustomerAuthService } from '../compras_reservas/clientes/customer-auth.service';
import { CustomerWishlistApi } from '../compras_reservas/deseos/customer-wishlist-api.service';
import { RecommendationsApi } from '../catalogo_publico/recomendaciones/recommendations-api.service';
import { CustomerRecommendationsService } from '../catalogo_publico/recomendaciones/customer-recommendations.service';
import { ReportsApi } from './reports-api.service';

describe('Primer grupo · CU19 CU20 CU23 API', () => {
  let http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(), provideHttpClientTesting(),
        { provide: CompanyService, useValue: {
          scoped: (factory: (company: { id: number }) => unknown) => factory({ id: 7 }),
        } },
        { provide: CustomerAuthService, useValue: { token: () => 'sesion-cliente-test' } },
      ],
    });
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());

  it('CU19 solo consulta recomendaciones del tenant elegido, sin token personal', () => {
    const api = TestBed.inject(RecommendationsApi);
    api.list('tienda-ejemplo', { producto_slug: 'prenda-base', talla: 'M', sucursal_id: 4 })
      .subscribe(data => expect(data.items).toEqual([]));
    const req = http.expectOne(request => request.url === '/api/catalogo/recomendaciones');
    expect(req.request.params.get('tienda')).toBe('tienda-ejemplo');
    expect(req.request.params.get('producto_slug')).toBe('prenda-base');
    expect(req.request.params.get('sucursal_id')).toBe('4');
    expect(req.request.headers.has('Authorization')).toBe(false);
    req.flush({ tienda: 'tienda-ejemplo', basado_en: 'prenda-base',
      consultado_en: '2026-11-08T10:00:00Z', criterio: 'REGLAS_SIMILITUD_CATALOGO', items: [] });
  });

  it('CU20 exige empresa seleccionada y transmite período y sucursal', () => {
    const api = TestBed.inject(ReportsApi);
    api.load({ tipo: 'ventas', desde: '2026-11-01', hasta: '2026-11-08', sucursal_id: 2 })
      .subscribe();
    const req = http.expectOne(request => request.url === '/api/admin/reportes-comerciales');
    expect(req.request.headers.get('X-Empresa-Id')).toBe('7');
    expect(req.request.params.get('tipo')).toBe('ventas');
    expect(req.request.params.get('sucursal_id')).toBe('2');
    req.flush({ tipo: 'ventas', desde: '2026-11-01', hasta: '2026-11-08',
      zona_horaria: 'UTC', nota: '', por_sucursal: [], totales: {} });
  });

  it('CU19 guarda consentimiento y visitas únicamente con token del cliente', () => {
    const service = TestBed.inject(CustomerRecommendationsService);
    service.setPreferences('tienda-ejemplo', true).subscribe(result =>
      expect(result.habilitado).toBe(true));
    const consent = http.expectOne('/api/tiendas/tienda-ejemplo/cuenta/recomendaciones/preferencias');
    expect(consent.request.method).toBe('PUT');
    expect(consent.request.headers.get('Authorization')).toBe('Bearer sesion-cliente-test');
    expect(consent.request.body).toEqual({ habilitado: true });
    consent.flush({ habilitado: true, historial_borrado: false });

    service.registerView('tienda-ejemplo', 'polera-clasica').subscribe();
    const visit = http.expectOne('/api/tiendas/tienda-ejemplo/cuenta/recomendaciones/visitas');
    expect(visit.request.method).toBe('POST');
    expect(visit.request.body).toEqual({ producto_slug: 'polera-clasica' });
    visit.flush({ registrado: true });

    service.recommendations('tienda-ejemplo', { talla: 'M', color: 'Azul' }).subscribe();
    const feed = http.expectOne(req =>
      req.url === '/api/tiendas/tienda-ejemplo/cuenta/recomendaciones/sugerencias');
    expect(feed.request.params.get('color')).toBe('Azul');
    feed.flush({ tienda: 'tienda-ejemplo', basado_en: null, consultado_en: '',
      criterio: 'REGLAS_HISTORIAL_CONSENTIDO', items: [] });
  });

  it('CU23 usa sesión del cliente y guarda la variante, no solo el producto', () => {
    const api = TestBed.inject(CustomerWishlistApi);
    api.add('tienda-ejemplo', 54).subscribe(response => expect(response.agregado).toBe(true));
    const req = http.expectOne('/api/tiendas/tienda-ejemplo/cuenta/deseos');
    expect(req.request.method).toBe('POST');
    expect(req.request.headers.get('Authorization')).toBe('Bearer sesion-cliente-test');
    expect(req.request.body).toEqual({ variante_id: 54 });
    req.flush({ variante_id: 54, agregado: true });
  });
});
