import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { CatalogListPage } from './catalog-list';
import type { CatalogProduct } from './catalog.models';

const PRODUCT: CatalogProduct = {
  id: 7, nombre: 'Camisa de lino', slug: 'camisa-de-lino', descripcion: 'Lino natural.',
  precio: '149.90', moneda: 'BOB', imagen_url: null, activo: true,
  creado_en: '2026-10-25T12:00:00Z', actualizado_en: '2026-10-25T12:00:00Z',
};
const ENDPOINT = '/api/catalogo/productos';

describe('Catálogo público de prendas', () => {
  let http: HttpTestingController;

  async function setup() {
    await TestBed.configureTestingModule({
      imports: [CatalogListPage],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(CatalogListPage);
    fixture.detectChanges();
    return { fixture, component: fixture.componentInstance, root: fixture.nativeElement as HTMLElement };
  }

  function request() {
    return http.expectOne(request => request.url === ENDPOINT);
  }

  function button(root: HTMLElement, label: string): HTMLButtonElement {
    const match = [...root.querySelectorAll('button')].find(button => button.textContent?.trim() === label);
    expect(match).toBeDefined();
    return match!;
  }

  function submitSearch(root: HTMLElement, value: string): void {
    const input = root.querySelector('#catalog-search') as HTMLInputElement;
    input.value = value;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    root.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
  }

  afterEach(() => http?.verify());

  it('distingue la carga del catálogo vacío sin mostrar prendas inventadas', async () => {
    const { fixture, root } = await setup();
    expect(root.querySelector('[role="status"]')?.textContent).toContain('Cargando prendas');
    expect(root.querySelector('.catalog-card')).toBeNull();
    const initial = request();
    expect(initial.request.params.get('limit')).toBe('20');
    expect(initial.request.params.get('offset')).toBe('0');
    expect(initial.request.params.has('q')).toBe(false);
    initial.flush({ items: [], total: 0, limit: 20, offset: 0 });
    fixture.detectChanges();
    expect(root.textContent).toContain('No hay prendas publicadas');
    expect(root.textContent).not.toContain('Sin coincidencias');
    expect(root.querySelector('.catalog-grid')).toBeNull();
    expect(root.querySelector('.catalog-pagination')).toBeNull();
  });

  it('muestra los datos recibidos, conserva el precio exacto y enlaza al detalle por slug', async () => {
    const { fixture, root } = await setup();
    request().flush({ items: [{ ...PRODUCT, precio: '99999999.99' }], total: 1, limit: 20, offset: 0 });
    fixture.detectChanges();
    const card = root.querySelector('.catalog-card') as HTMLAnchorElement;
    expect(root.querySelectorAll('.catalog-card')).toHaveLength(1);
    expect(card.textContent).toContain('Camisa de lino');
    expect(card.querySelector('.catalog-price')?.textContent).toBe('Bs 99999999.99');
    expect(card.getAttribute('href')).toBe('/catalogo/camisa-de-lino');
    expect(card.getAttribute('aria-label')).toContain('Camisa de lino');
    expect(card.querySelector('vn-catalog-image')).not.toBeNull();
    expect(root.querySelector('label[for="catalog-search"]')).not.toBeNull();
    expect(root.querySelector('.catalog-local-notice')).toBeNull();
  });

  it('busca por nombre en el servidor, recorta espacios y reinicia la paginación', async () => {
    const { fixture, root } = await setup();
    request().flush({ items: [PRODUCT], total: 41, limit: 20, offset: 0 });
    fixture.detectChanges();
    button(root, 'Siguiente').click();
    const second = request();
    expect(second.request.params.get('offset')).toBe('20');
    second.flush({ items: [PRODUCT], total: 41, limit: 20, offset: 20 });
    fixture.detectChanges();
    submitSearch(root, '  lino  ');
    const search = request();
    expect(search.request.params.get('q')).toBe('lino');
    expect(search.request.params.get('offset')).toBe('0');
    expect(search.request.params.get('limit')).toBe('20');
    search.flush({ items: [PRODUCT], total: 21, limit: 20, offset: 0 });
    fixture.detectChanges();
    button(root, 'Siguiente').click();
    const searchPage = request();
    expect(searchPage.request.params.get('q')).toBe('lino');
    expect(searchPage.request.params.get('offset')).toBe('20');
    searchPage.flush({ items: [PRODUCT], total: 21, limit: 20, offset: 20 });
  });

  it('limpia el término y vuelve a la primera página en el servidor', async () => {
    const { fixture, root } = await setup();
    request().flush({ items: [PRODUCT], total: 41, limit: 20, offset: 0 });
    submitSearch(root, 'lino');
    request().flush({ items: [PRODUCT], total: 41, limit: 20, offset: 0 });
    fixture.detectChanges();
    button(root, 'Siguiente').click();
    request().flush({ items: [PRODUCT], total: 41, limit: 20, offset: 20 });
    fixture.detectChanges();
    button(root, 'Limpiar').click();
    const cleared = request();
    expect(cleared.request.params.has('q')).toBe(false);
    expect(cleared.request.params.get('offset')).toBe('0');
    cleared.flush({ items: [PRODUCT], total: 41, limit: 20, offset: 0 });
    fixture.detectChanges();
    expect((root.querySelector('#catalog-search') as HTMLInputElement).value).toBe('');
  });

  it('distingue una búsqueda sin coincidencias y permite limpiarla', async () => {
    const { fixture, root } = await setup();
    request().flush({ items: [PRODUCT], total: 1, limit: 20, offset: 0 });
    submitSearch(root, 'otra prenda');
    request().flush({ items: [], total: 0, limit: 20, offset: 0 });
    fixture.detectChanges();
    expect(root.textContent).toContain('Sin coincidencias');
    expect(root.textContent).not.toContain('No hay prendas publicadas');
    expect(root.querySelector('.catalog-card')).toBeNull();
    button(root, 'Limpiar búsqueda').click();
    const cleared = request();
    expect(cleared.request.params.has('q')).toBe(false);
    cleared.flush({ items: [PRODUCT], total: 1, limit: 20, offset: 0 });
  });

  it('respeta los límites de las páginas y evita avanzar mientras espera una respuesta', async () => {
    const { fixture, component, root } = await setup();
    request().flush({ items: [PRODUCT], total: 21, limit: 20, offset: 0 });
    fixture.detectChanges();
    expect(button(root, 'Anterior').disabled).toBe(true);
    expect(button(root, 'Siguiente').disabled).toBe(false);
    component.page(-1);
    http.expectNone(request => request.url === ENDPOINT);
    button(root, 'Siguiente').click();
    const lastPage = request();
    expect(lastPage.request.params.get('offset')).toBe('20');
    component.page(1);
    component.page(-1);
    http.expectNone(request => request.url === ENDPOINT);
    lastPage.flush({ items: [PRODUCT], total: 21, limit: 20, offset: 20 });
    fixture.detectChanges();
    expect(button(root, 'Siguiente').disabled).toBe(true);
    expect(button(root, 'Anterior').disabled).toBe(false);
    component.page(1);
    http.expectNone(request => request.url === ENDPOINT);
    button(root, 'Anterior').click();
    const firstPage = request();
    expect(firstPage.request.params.get('offset')).toBe('0');
    firstPage.flush({ items: [PRODUCT], total: 21, limit: 20, offset: 0 });
  });

  it('muestra un error controlado y reintenta la misma consulta sin exponer detalles internos', async () => {
    const { fixture, root } = await setup();
    request().flush({ items: [PRODUCT], total: 1, limit: 20, offset: 0 });
    submitSearch(root, 'lino');
    request().flush({ detail: 'SQL interno' }, { status: 500, statusText: 'Error' });
    fixture.detectChanges();
    expect(root.textContent).toContain('No pudimos cargar el catálogo');
    expect(root.querySelector('[role="alert"]')?.textContent).toContain('inténtalo de nuevo');
    expect(root.textContent).not.toContain('SQL interno');
    expect(root.textContent).not.toContain('Sin coincidencias');
    expect(root.textContent).not.toContain('No hay prendas publicadas');
    expect(root.querySelector('.catalog-card')).toBeNull();
    button(root, 'Reintentar').click();
    const retry = request();
    expect(retry.request.params.get('q')).toBe('lino');
    expect(retry.request.params.get('offset')).toBe('0');
    retry.flush({ items: [PRODUCT], total: 1, limit: 20, offset: 0 });
    fixture.detectChanges();
    expect(root.querySelector('[role="alert"]')).toBeNull();
    expect(root.querySelector('.catalog-card')?.textContent).toContain(PRODUCT.nombre);
  });

  it.each([10, 0])('permite volver a la primera página si el total se reduce a %s desde una página posterior', async total => {
    const { fixture, component, root } = await setup();
    request().flush({ items: [PRODUCT], total: 41, limit: 20, offset: 0 });
    fixture.detectChanges();
    button(root, 'Siguiente').click();
    request().flush({ items: [PRODUCT], total: 41, limit: 20, offset: 20 });
    fixture.detectChanges();
    button(root, 'Siguiente').click();
    request().flush({ items: [PRODUCT], total: 41, limit: 20, offset: 40 });
    component.reload();
    request().flush({ items: [], total, limit: 20, offset: 40 });
    fixture.detectChanges();
    expect(root.textContent).toContain('No hay prendas en esta página');
    expect(root.querySelector('.catalog-pagination')).not.toBeNull();
    expect(button(root, 'Anterior').disabled).toBe(false);
    expect(button(root, 'Siguiente').disabled).toBe(true);
    button(root, 'Anterior').click();
    const previous = request();
    expect(previous.request.params.get('offset')).toBe('0');
    previous.flush({ items: total ? [PRODUCT] : [], total, limit: 20, offset: 0 });
  });

  it('cancela la solicitud anterior cuando se envía una nueva búsqueda', async () => {
    const { fixture, root } = await setup();
    const initial = request();
    submitSearch(root, 'lino');
    expect(initial.cancelled).toBe(true);
    const latest = request();
    expect(latest.request.params.get('q')).toBe('lino');
    latest.flush({ items: [PRODUCT], total: 1, limit: 20, offset: 0 });
    fixture.detectChanges();
    expect(root.querySelectorAll('.catalog-card')).toHaveLength(1);
    expect(root.textContent).not.toContain('Cargando prendas');
  });

  it('no envía una búsqueda que excede el máximo del contrato y asocia su mensaje al campo', async () => {
    const { fixture, component, root } = await setup();
    request().flush({ items: [], total: 0, limit: 20, offset: 0 });
    component.filters.controls.q.setValue('x'.repeat(121));
    component.search();
    fixture.detectChanges();
    http.expectNone(request => request.url === ENDPOINT);
    expect(root.querySelector('#catalog-search')?.getAttribute('aria-invalid')).toBe('true');
    expect(root.querySelector('#catalog-search')?.getAttribute('aria-describedby')).toBe('catalog-search-error');
    expect(root.querySelector('#catalog-search-error')?.textContent).toContain('120 caracteres');
  });
});
