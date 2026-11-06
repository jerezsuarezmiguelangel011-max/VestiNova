import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { authInterceptor } from '../../autenticacion_usuarios/autenticacion/auth.interceptor';
import { AuthService, SESSION_KEY } from '../../autenticacion_usuarios/autenticacion/auth.service';
import { CatalogApiService } from './catalog-api.service';
import { CatalogShopService } from './catalog-shop.service';

describe('Contrato HTTP del catálogo público', () => {
  let http: HttpTestingController;
  let api: CatalogApiService;

  beforeEach(() => {
    sessionStorage.setItem(SESSION_KEY, 'sesion-administrativa-existente');
    TestBed.configureTestingModule({ providers: [
      provideHttpClient(withInterceptors([authInterceptor])),
      provideHttpClientTesting(), provideRouter([]),
    ] });
    http = TestBed.inject(HttpTestingController);
    api = TestBed.inject(CatalogApiService);
  });
  afterEach(() => { http.verify(); sessionStorage.removeItem(SESSION_KEY); });

  it('consulta la API pública con búsqueda y paginación sin enviar el token administrativo', () => {
    api.list({ q: '  lino  ', limit: 20, offset: 40 }).subscribe();
    const request = http.expectOne(request => request.url === '/api/catalogo/productos');
    expect(request.request.method).toBe('GET');
    expect(request.request.params.keys().sort()).toEqual(['limit', 'offset', 'q']);
    expect(request.request.params.get('q')).toBe('lino');
    expect(request.request.params.get('limit')).toBe('20');
    expect(request.request.params.get('offset')).toBe('40');
    expect(request.request.headers.has('Authorization')).toBe(false);
    expect(request.request.headers.get('ngsw-bypass')).toBe('true');
    request.flush({ items: [], total: 0, limit: 20, offset: 40 });
    expect(TestBed.inject(AuthService).token()).toBe('sesion-administrativa-existente');
  });

  it('omite búsquedas vacías y conserva el total y la paginación del servidor', () => {
    const response = { items: [], total: 32, limit: 20, offset: 20 };
    let received: unknown;
    api.list({ q: '   ', limit: 20, offset: 20 }).subscribe(value => received = value);
    const request = http.expectOne(request => request.url === '/api/catalogo/productos');
    expect(request.request.params.has('q')).toBe(false);
    request.flush(response);
    expect(received).toEqual(response);
  });

  it('codifica el slug como un solo segmento y no convierte un 404 público en cierre de sesión', () => {
    let status: number | undefined;
    api.get('prenda/con espacio').subscribe({ error: error => status = error.status });
    const request = http.expectOne('/api/catalogo/productos/prenda%2Fcon%20espacio');
    expect(request.request.headers.has('Authorization')).toBe(false);
    expect(request.request.headers.get('ngsw-bypass')).toBe('true');
    request.flush({ detail: 'Producto no encontrado.' }, { status: 404, statusText: 'Not Found' });
    expect(status).toBe(404);
    expect(TestBed.inject(AuthService).token()).toBe('sesion-administrativa-existente');
  });

  it('filtra una tienda sin enviar tokens y respeta filtros comerciales', () => {
    TestBed.inject(CatalogShopService).setTienda('demo-moda-andina');
    api.list({
      q: 'Lino', categoria_id: 3, talla: 'M', color: 'AZUL',
      precio_min: 100, precio_max: 300, limit: 20, offset: 0,
    }).subscribe();
    const request = http.expectOne(req => req.url === '/api/catalogo/productos');
    expect(request.request.params.get('tienda')).toBe('demo-moda-andina');
    expect(request.request.params.get('categoria_id')).toBe('3');
    expect(request.request.params.get('talla')).toBe('M');
    expect(request.request.params.get('color')).toBe('AZUL');
    expect(request.request.params.get('precio_min')).toBe('100');
    expect(request.request.params.get('precio_max')).toBe('300');
    expect(request.request.headers.has('Authorization')).toBe(false);
    request.flush({ items: [], total: 0, limit: 20, offset: 0 });

    api.variantes('camisa-lino').subscribe();
    const variants = http.expectOne(req => req.url.endsWith('/camisa-lino/variantes'));
    expect(variants.request.params.get('tienda')).toBe('demo-moda-andina');
    variants.flush([{id: 12, talla: 'M', color: 'AZUL'}]);

    api.categorias().subscribe();
    const categories = http.expectOne(req => req.url === '/api/catalogo/categorias');
    expect(categories.request.params.get('tienda')).toBe('demo-moda-andina');
    categories.flush([{id: 3, nombre: 'Camisas'}]);

    api.sucursales().subscribe();
    const branches = http.expectOne(req => req.url === '/api/catalogo/sucursales');
    expect(branches.request.params.get('tienda')).toBe('demo-moda-andina');
    expect(branches.request.headers.has('Authorization')).toBe(false);
    branches.flush([{ id: 3, nombre: 'Sucursal Andina' }]);

    api.variantesTienda(100, 0).subscribe();
    const download = http.expectOne(req => req.url === '/api/catalogo/variantes');
    expect(download.request.params.get('tienda')).toBe('demo-moda-andina');
    download.flush({items: [], total: 0, limit: 100, offset: 0});
  });

});
