import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { BehaviorSubject, of } from 'rxjs';
import { authInterceptor } from '../../autenticacion_usuarios/autenticacion/auth.interceptor';
import { SESSION_KEY } from '../../autenticacion_usuarios/autenticacion/auth.service';
import { CatalogDataService } from '../../catalogo_publico/catalogo/catalog-data.service';
import type { CatalogProduct, CatalogResult } from '../../catalogo_publico/catalogo/catalog.models';
import { PURCHASE_ACCESS_TOKEN } from './purchase-api.service';
import { PurchasePage } from './purchase-page';
import { PurchaseSelectionService } from './purchase-selection.service';

const PRODUCT: CatalogProduct = {
  id: 7, nombre: 'Camisa de lino', slug: 'camisa-de-lino', descripcion: 'Lino natural.',
  precio: '149.90', moneda: 'BOB', imagen_url: null, activo: true,
  creado_en: '2026-10-25T12:00:00Z', actualizado_en: '2026-10-25T12:00:00Z',
};
const SECOND: CatalogProduct = { ...PRODUCT, id: 8, nombre: 'Falda plisada', slug: 'falda-plisada', precio: '179.00' };
const FIRST_ID = '10000000-0000-4000-8000-000000000001';
const SECOND_ID = '10000000-0000-4000-8000-000000000002';
const THIRD_ID = '10000000-0000-4000-8000-000000000003';
const FOURTH_ID = '10000000-0000-4000-8000-000000000004';

function result(product = PRODUCT): CatalogResult<CatalogProduct> {
  return { data: product, source: 'network', downloadedAt: null };
}

describe('Selección y confirmación de compra desde prendas reales del catálogo', () => {
  let http: HttpTestingController;

  async function setup(options: { slug?: string | null; token?: () => string | null; local?: boolean } = {}) {
    sessionStorage.setItem(SESSION_KEY, 'sesion-administrativa-existente');
    const params = new BehaviorSubject(convertToParamMap(options.slug === null ? {} : { slug: options.slug ?? PRODUCT.slug }));
    const get = vi.fn((slug: string) => of<CatalogResult<CatalogProduct>>({
      ...result(slug === SECOND.slug ? SECOND : PRODUCT), source: options.local ? 'local' : 'network',
      downloadedAt: options.local ? '2026-10-25T12:00:00Z' : null,
    }));
    await TestBed.configureTestingModule({
      imports: [PurchasePage],
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])), provideHttpClientTesting(), provideRouter([]),
        { provide: CatalogDataService, useValue: { get } },
        { provide: ActivatedRoute, useValue: { queryParamMap: params.asObservable() } },
        ...(options.token ? [{ provide: PURCHASE_ACCESS_TOKEN, useValue: options.token }] : []),
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(PurchasePage);
    fixture.detectChanges();
    return { fixture, component: fixture.componentInstance, root: fixture.nativeElement as HTMLElement, params, get };
  }

  function capabilities(enabled = true) {
    const request = http.expectOne('/api/compras/capacidades');
    expect(request.request.method).toBe('GET');
    expect(request.request.headers.get('ngsw-bypass')).toBe('true');
    request.flush({ habilitado: enabled, detail: enabled ? 'Compra disponible.' : 'Falta el contexto de cliente, empresa, sucursal e inventario.' });
    return request;
  }

  function confirmButton(root: HTMLElement): HTMLButtonElement {
    return root.querySelector('.purchase-confirm') as HTMLButtonElement;
  }

  afterEach(() => {
    http?.verify();
    sessionStorage.removeItem(SESSION_KEY);
    vi.restoreAllMocks();
  });

  it('carga la prenda pública y mantiene confirmar desactivado mientras verifica las dependencias', async () => {
    const { root, get, component } = await setup();
    expect(get).toHaveBeenCalledExactlyOnceWith(PRODUCT.slug);
    expect(root.querySelector('.purchase-line h3')?.textContent).toBe(PRODUCT.nombre);
    expect(root.querySelector('.purchase-price')?.textContent).toContain('Bs 149.90');
    expect(root.textContent).toContain('referenciales');
    expect(root.querySelector('vn-catalog-image')).not.toBeNull();
    expect(confirmButton(root).disabled).toBe(true);
    component.confirm();
    http.expectNone('/api/compras');
    const request = capabilities();
    expect(request.request.headers.has('Authorization')).toBe(false);
  });

  it('explica la dependencia ausente sin inventar cliente, empresa, sucursal o disponibilidad', async () => {
    const { root, fixture, component } = await setup();
    capabilities(false);
    fixture.detectChanges();
    expect(root.querySelector('.purchase-dependency')?.textContent).toContain('Falta el contexto');
    expect(root.textContent).toContain('Compra no disponible');
    expect(confirmButton(root).disabled).toBe(true);
    component.confirm();
    http.expectNone('/api/compras');
    expect(root.querySelector('.purchase-receipt')).toBeNull();
    expect(root.querySelectorAll('input')).toHaveLength(1);
  });

  it('identifica el precio referencial de una copia local y su fecha sin habilitar compras ficticias', async () => {
    const { root, fixture } = await setup({ local: true });
    capabilities(false);
    fixture.detectChanges();
    expect(root.querySelector('.purchase-local')?.textContent).toContain('puede estar desactualizado');
    expect(root.querySelector('.purchase-local')?.textContent).toContain('25/10/2026 08:00');
    expect(confirmButton(root).disabled).toBe(true);
    http.expectNone('/api/compras');
  });

  it('mantiene varias prendas sin duplicarlas y conserva la selección entre visitas a la página', async () => {
    const { root, fixture, component, params } = await setup();
    capabilities(false);
    component.updateQuantity(PRODUCT.id, '3');
    params.next(convertToParamMap({ slug: SECOND.slug }));
    fixture.detectChanges();
    expect(root.querySelectorAll('.purchase-line')).toHaveLength(2);
    params.next(convertToParamMap({ slug: PRODUCT.slug }));
    fixture.detectChanges();
    expect(root.querySelectorAll('.purchase-line')).toHaveLength(2);
    expect(TestBed.inject(PurchaseSelectionService).lines()[0].cantidad).toBe('3');
    fixture.destroy();
    const reopened = TestBed.createComponent(PurchasePage);
    reopened.detectChanges();
    capabilities(false);
    reopened.detectChanges();
    expect((reopened.nativeElement as HTMLElement).querySelectorAll('.purchase-line')).toHaveLength(2);
    expect(reopened.componentInstance.lines()[0].cantidad).toBe('3');
    reopened.componentInstance.remove(SECOND.id);
    reopened.detectChanges();
    expect((reopened.nativeElement as HTMLElement).querySelectorAll('.purchase-line')).toHaveLength(1);
  });

  it('rechaza cantidades no enteras o no positivas y no confirma una selección vacía', async () => {
    const { root, fixture, component } = await setup();
    capabilities();
    for (const value of ['0', '-1', '1.5', '1e2', '', '2147483648', String(Number.MAX_SAFE_INTEGER)]) {
      component.updateQuantity(PRODUCT.id, value);
      fixture.detectChanges();
      expect(confirmButton(root).disabled).toBe(true);
      expect(root.querySelector('input')?.getAttribute('aria-invalid')).toBe('true');
      component.confirm();
      http.expectNone('/api/compras');
    }
    const input = root.querySelector('input') as HTMLInputElement;
    input.value = '2';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    fixture.detectChanges();
    expect(confirmButton(root).disabled).toBe(false);
    component.remove(PRODUCT.id);
    fixture.detectChanges();
    expect(confirmButton(root).disabled).toBe(true);
    expect(root.textContent).toContain('Todavía no elegiste prendas');
  });

  it('envía solo UUID, identificadores y cantidades, y muestra exclusivamente el recibo del servidor', async () => {
    vi.spyOn(crypto, 'randomUUID').mockReturnValue(FIRST_ID);
    const { root, fixture, component } = await setup();
    capabilities();
    component.updateQuantity(PRODUCT.id, '2');
    fixture.detectChanges();
    confirmButton(root).click();
    component.confirm();
    fixture.detectChanges();
    const request = http.expectOne('/api/compras');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({ id: FIRST_ID, items: [{ producto_id: 7, cantidad: 2 }] });
    expect(request.request.headers.has('Authorization')).toBe(false);
    expect(request.request.headers.get('ngsw-bypass')).toBe('true');
    expect(root.querySelector('.purchase-receipt')).toBeNull();
    expect(confirmButton(root).disabled).toBe(true);
    expect((root.querySelector('input') as HTMLInputElement).disabled).toBe(true);
    http.expectNone('/api/compras');
    request.flush({
      id: FIRST_ID, estado: 'CONFIRMADA', moneda: 'BOB', total: '240.00', creado_en: '2026-10-25T13:00:00Z',
      items: [{ producto_id: 7, nombre: 'Camisa de lino', cantidad: 2, precio_unitario: '120.00', subtotal: '240.00' }],
    }, { status: 201, statusText: 'Created' });
    fixture.detectChanges();
    const receipt = root.querySelector('.purchase-receipt');
    expect(receipt?.textContent).toContain('Compra confirmada');
    expect(receipt?.textContent).toContain('Bs 120.00');
    expect(receipt?.querySelector('.purchase-total')?.textContent).toContain('Bs 240.00');
    expect(receipt?.textContent).not.toContain('149.90');
    expect(receipt?.querySelector('input')).toBeNull();
    expect(root.textContent?.toLowerCase()).not.toContain('pagad');
    expect(component.lines()).toHaveLength(0);
  });

  it.each([503, 500])('conserva la selección y no anuncia confirmación ante HTTP %s', async status => {
    const { root, fixture, component } = await setup();
    capabilities();
    component.confirm();
    http.expectOne('/api/compras').flush({ detail: 'SQL interno que no debe mostrarse' }, { status, statusText: 'Unavailable' });
    fixture.detectChanges();
    expect(component.receipt()).toBeNull();
    expect(root.querySelector('.purchase-receipt')).toBeNull();
    expect(root.querySelector('[role="alert"]')?.textContent).toContain('selección se conserva');
    expect(root.textContent).not.toContain('SQL interno');
    expect(root.querySelector('.purchase-line h3')?.textContent).toBe(PRODUCT.nombre);
  });

  it('reutiliza el UUID al reintentar la misma selección tras un fallo de red', async () => {
    const random = vi.spyOn(crypto, 'randomUUID').mockReturnValue(FIRST_ID);
    const { root, fixture, component } = await setup();
    capabilities();
    component.confirm();
    const first = http.expectOne('/api/compras');
    const original = first.request.body;
    first.error(new ProgressEvent('error'));
    fixture.detectChanges();
    expect(root.querySelector('.purchase-receipt')).toBeNull();
    confirmButton(root).click();
    const retry = http.expectOne('/api/compras');
    expect(retry.request.body).toEqual(original);
    expect(random).toHaveBeenCalledTimes(1);
    retry.flush({}, { status: 503, statusText: 'Unavailable' });
  });

  it('cambia el UUID cuando cambian cantidades o líneas de la selección', async () => {
    vi.spyOn(crypto, 'randomUUID').mockReturnValueOnce(FIRST_ID).mockReturnValueOnce(SECOND_ID)
      .mockReturnValueOnce(THIRD_ID).mockReturnValueOnce(FOURTH_ID);
    const { fixture, component, params } = await setup();
    capabilities();
    const selection = TestBed.inject(PurchaseSelectionService);
    expect(selection.command()?.id).toBe(FIRST_ID);
    component.updateQuantity(PRODUCT.id, '2');
    expect(selection.command()?.id).toBe(SECOND_ID);
    params.next(convertToParamMap({ slug: SECOND.slug }));
    fixture.detectChanges();
    expect(selection.command()).toEqual({ id: THIRD_ID, items: [{ producto_id: 7, cantidad: 2 }, { producto_id: 8, cantidad: 1 }] });
    component.remove(SECOND.id);
    expect(selection.command()?.id).toBe(FOURTH_ID);
  });

  it('no presenta como confirmación una respuesta incompleta o con otro estado', async () => {
    const { root, fixture, component } = await setup();
    capabilities();
    component.confirm();
    const request = http.expectOne('/api/compras');
    request.flush({ id: request.request.body.id, estado: 'PENDIENTE', moneda: 'BOB', total: '149.90', items: [] });
    fixture.detectChanges();
    expect(component.receipt()).toBeNull();
    expect(root.querySelector('.purchase-receipt')).toBeNull();
    expect(root.querySelector('[role="alert"]')?.textContent).toContain('No se pudo verificar');
    expect(component.lines()).toHaveLength(1);
  });

  it('permite un token futuro de cliente únicamente en el adaptador de compras', async () => {
    const { component } = await setup({ token: () => 'acceso-cliente-verificado' });
    const request = capabilities();
    expect(request.request.headers.get('Authorization')).toBe('Bearer acceso-cliente-verificado');
    component.confirm();
    const purchase = http.expectOne('/api/compras');
    expect(purchase.request.headers.get('Authorization')).toBe('Bearer acceso-cliente-verificado');
    expect(sessionStorage.getItem(SESSION_KEY)).toBe('sesion-administrativa-existente');
    purchase.flush({}, { status: 403, statusText: 'Forbidden' });
  });

  it('permite abrir la selección vacía y no habilita confirmación si falla la comprobación de capacidades', async () => {
    const { root, fixture, component, get } = await setup({ slug: null });
    expect(get).not.toHaveBeenCalled();
    http.expectOne('/api/compras/capacidades').flush({ detail: 'Interno' }, { status: 503, statusText: 'Unavailable' });
    fixture.detectChanges();
    expect(confirmButton(root).disabled).toBe(true);
    expect(root.querySelector('[role="alert"]')?.textContent).toContain('No se pudo verificar');
    component.confirm();
    http.expectNone('/api/compras');
  });
});
