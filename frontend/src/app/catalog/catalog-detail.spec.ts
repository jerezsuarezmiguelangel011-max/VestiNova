import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { BehaviorSubject } from 'rxjs';
import { CatalogDetailPage } from './catalog-detail';
import { CatalogOfflineStoreService } from './catalog-offline-store.service';
import { CatalogProduct } from './catalog.models';

const PRODUCT: CatalogProduct = {
  id: 7, nombre: 'Camisa de lino', slug: 'camisa-de-lino',
  descripcion: 'Lino natural.\n<strong>Manga larga.</strong>',
  precio: '149.90', moneda: 'BOB', imagen_url: null, activo: true,
  creado_en: '2026-10-25T12:00:00Z', actualizado_en: '2026-10-25T12:00:00Z',
};

describe('Detalle público del catálogo', () => {
  let http: HttpTestingController;

  async function setup(slug = PRODUCT.slug) {
    const params = new BehaviorSubject(convertToParamMap({ slug }));
    await TestBed.configureTestingModule({
      imports: [CatalogDetailPage],
      providers: [
        provideHttpClient(), provideHttpClientTesting(), provideRouter([]),
        { provide: CatalogOfflineStoreService, useValue: { read: vi.fn().mockResolvedValue(null) } },
        { provide: ActivatedRoute, useValue: { paramMap: params.asObservable() } },
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(CatalogDetailPage);
    fixture.detectChanges();
    return { fixture, component: fixture.componentInstance, root: fixture.nativeElement as HTMLElement, params };
  }

  afterEach(() => http?.verify());

  it('distingue la carga y muestra datos públicos conservando precio y descripción como texto', async () => {
    const { fixture, component, root } = await setup();
    expect(root.querySelector('[role="status"]')?.textContent).toContain('Cargando producto');
    expect(root.querySelector('article')).toBeNull();
    const request = http.expectOne('/api/catalogo/productos/camisa-de-lino');
    expect(request.request.method).toBe('GET');
    expect(request.request.headers.has('Authorization')).toBe(false);
    request.flush(PRODUCT);
    fixture.detectChanges();
    expect(component.loading()).toBe(false);
    expect(root.querySelector('h1')?.textContent).toBe('Camisa de lino');
    expect(root.querySelector('.catalog-detail__price')?.textContent).toContain('Bs 149.90');
    expect(root.querySelector('.catalog-detail__price')?.textContent).toContain('BOB');
    const description = root.querySelector('.catalog-detail__description');
    expect(description?.textContent).toBe(PRODUCT.descripcion);
    expect(description?.querySelector('strong')).toBeNull();
    expect(root.querySelector('vn-catalog-image')).not.toBeNull();
    expect(root.querySelector('a')?.getAttribute('href')).toBe('/catalogo');
    expect(root.querySelector('.catalog-local-notice')).toBeNull();
  });

  it('presenta un 404 como producto no disponible sin reintentar ni mostrar detalles internos', async () => {
    const { fixture, component, root } = await setup();
    http.expectOne('/api/catalogo/productos/camisa-de-lino').flush(
      { detail: 'Producto ausente: SQL interno' }, { status: 404, statusText: 'Not Found' },
    );
    fixture.detectChanges();
    expect(component.notFound()).toBe(true);
    expect(component.error()).toBeNull();
    expect(component.product()).toBeNull();
    expect(root.querySelector('h1')?.textContent).toBe('Producto no disponible');
    expect(root.textContent).not.toContain('SQL interno');
    expect(root.querySelector('button')).toBeNull();
    http.expectNone('/api/catalogo/productos/camisa-de-lino');
  });

  it('informa que no hay copia tras un fallo de conexión y permite reintentar online', async () => {
    const { fixture, component, root } = await setup();
    http.expectOne('/api/catalogo/productos/camisa-de-lino').error(new ProgressEvent('error'));
    await vi.waitFor(() => expect(component.error()).toContain('No hay un catálogo descargado'));
    fixture.detectChanges();
    expect(component.notFound()).toBe(false);
    expect(root.querySelector('[role="alert"]')?.textContent).toContain('No hay un catálogo descargado');
    http.expectNone('/api/catalogo/productos/camisa-de-lino');
    (root.querySelector('button') as HTMLButtonElement).click();
    fixture.detectChanges();
    expect(root.querySelector('[role="status"]')?.textContent).toContain('Cargando producto');
    http.expectOne('/api/catalogo/productos/camisa-de-lino').flush(PRODUCT);
    fixture.detectChanges();
    expect(root.querySelector('h1')?.textContent).toBe(PRODUCT.nombre);
    expect(component.error()).toBeNull();
  });

  it('cambia de producto al cambiar el slug sin conservar datos del detalle anterior', async () => {
    const { fixture, component, root, params } = await setup();
    http.expectOne('/api/catalogo/productos/camisa-de-lino').flush(PRODUCT);
    fixture.detectChanges();
    params.next(convertToParamMap({ slug: 'falda-plisada' }));
    fixture.detectChanges();
    expect(component.product()).toBeNull();
    expect(root.textContent).not.toContain(PRODUCT.nombre);
    http.expectOne('/api/catalogo/productos/falda-plisada').flush({
      ...PRODUCT, id: 8, nombre: 'Falda plisada', slug: 'falda-plisada', precio: '179.00',
    });
    fixture.detectChanges();
    expect(root.querySelector('h1')?.textContent).toBe('Falda plisada');
    expect(root.querySelector('.catalog-detail__price')?.textContent).toContain('Bs 179.00');
  });

  it('cancela la petición anterior cuando cambia el slug durante la carga', async () => {
    const { fixture, root, params } = await setup();
    const previous = http.expectOne('/api/catalogo/productos/camisa-de-lino');
    params.next(convertToParamMap({ slug: 'falda-plisada' }));
    expect(previous.cancelled).toBe(true);
    http.expectOne('/api/catalogo/productos/falda-plisada').flush({
      ...PRODUCT, id: 8, nombre: 'Falda plisada', slug: 'falda-plisada',
    });
    fixture.detectChanges();
    expect(root.querySelector('h1')?.textContent).toBe('Falda plisada');
  });
});
