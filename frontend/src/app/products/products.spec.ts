import { HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter, Router } from '@angular/router';
import { productError } from './product-errors';
import { decimalPrice, ProductFormPage, productPrice } from './product-form';
import { ProductListPage } from './product-list';
import { Product } from './product.model';
import { ProductService } from './product.service';
import { FormControl } from '@angular/forms';
import type { MockInstance } from 'vitest';
import { CompanyService } from '../company/company.service';
import { BehaviorSubject, Subject } from 'rxjs';

beforeEach(() => sessionStorage.clear());
afterEach(() => { sessionStorage.clear(); vi.restoreAllMocks(); });

const PRODUCT: Product = {
  id: 7, nombre: 'Camisa de lino', slug: 'camisa-de-lino', descripcion: 'Lino natural.',
  precio: '149.90', moneda: 'BOB', imagen_url: null, activo: true,
  creado_en: '2026-10-25T12:00:00Z', actualizado_en: '2026-10-25T12:00:00Z',
};

const COMPANIES = [
  { id: 1, nombre: 'Empresa A', slug: 'empresa-a', activo: true, rol: 'ADMINISTRADOR' },
  { id: 2, nombre: 'Empresa B', slug: 'empresa-b', activo: true, rol: 'OPERADOR' },
];

function selectCompany(http: HttpTestingController) {
  const companies = TestBed.inject(CompanyService);
  companies.ensureForUser(1).subscribe();
  http.expectOne('/api/empresas').flush(COMPANIES);
  companies.select(1);
  return companies;
}

describe('Contrato HTTP de productos', () => {
  let http: HttpTestingController;
  let service: ProductService;
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    http = TestBed.inject(HttpTestingController);
    service = TestBed.inject(ProductService);
    selectCompany(http);
  });
  afterEach(() => http.verify());

  it('envía filtros y paginación al servidor incluyendo activo=false', () => {
    service.list({ q: 'lino', activo: false, limit: 20, offset: 40 }).subscribe();
    const request = http.expectOne(request => request.url === '/api/admin/productos');
    expect(request.request.params.get('q')).toBe('lino');
    expect(request.request.params.get('activo')).toBe('false');
    expect(request.request.params.get('limit')).toBe('20');
    expect(request.request.params.get('offset')).toBe('40');
    request.flush({ items: [], total: 0, limit: 20, offset: 40 });
  });

  it('conserva el importe decimal como string al crear y editar', () => {
    service.create({ nombre: 'Camisa', descripcion: '', precio: '99999999.99' }).subscribe();
    const create = http.expectOne('/api/admin/productos');
    expect(create.request.method).toBe('POST');
    expect(create.request.body.precio).toBe('99999999.99');
    create.flush(PRODUCT);
    service.update(7, { precio: '149.95' }).subscribe();
    const update = http.expectOne('/api/admin/productos/7');
    expect(update.request.method).toBe('PATCH');
    expect(update.request.body).toEqual({ precio: '149.95' });
    update.flush(PRODUCT);
  });

  it('fija la empresa al suscribirse y cancela lecturas cuando cambia el contexto', () => {
    const emitted = vi.fn();
    service.get(7).subscribe(emitted);
    const request = http.expectOne('/api/admin/productos/7');
    expect(request.request.headers.get('X-Empresa-Id')).toBe('1');
    TestBed.inject(CompanyService).select(2);
    expect(request.cancelled).toBe(true);
    expect(emitted).not.toHaveBeenCalled();
    service.get(7).subscribe();
    const next = http.expectOne('/api/admin/productos/7');
    expect(next.request.headers.get('X-Empresa-Id')).toBe('2');
    next.flush(PRODUCT);
  });

  it('no consulta productos sin una empresa validada', () => {
    TestBed.inject(CompanyService).clear();
    const error = vi.fn();
    service.list({ limit: 20, offset: 0 }).subscribe({ error });
    http.expectNone(request => request.url.startsWith('/api/admin/productos'));
    expect(error.mock.calls[0][0].status).toBe(403);
  });

  it('no conserva confirmaciones de otra empresa aunque no haya páginas montadas', () => {
    service.notice.set('Producto registrado correctamente.');
    TestBed.inject(CompanyService).select(2);
    expect(service.notice()).toBeNull();
  });
});

describe('Importes de producto sin conversión a float', () => {
  it.each(['0', '0.00', '-1.00', '10.001', '1e3', '100000000.00', 'NaN'])('rechaza %s', value => {
    expect(productPrice(new FormControl(value))).not.toBeNull();
  });
  it.each(['0.01', '99999999.99', '12,50', '20'])('admite %s', value => {
    expect(productPrice(new FormControl(value))).toBeNull();
  });
  it('normaliza separador, ceros y centavos sin perder el límite de precisión', () => {
    expect(decimalPrice('00012,5')).toBe('12.50');
    expect(decimalPrice('99999999.99')).toBe('99999999.99');
    expect(decimalPrice('1')).toBe('1.00');
  });
});

describe('Formulario de producto', () => {
  let http: HttpTestingController;
  let navigate: MockInstance<Router['navigate']>;
  async function setup(id?: string) {
    const routeParams = new BehaviorSubject(convertToParamMap(id ? { id } : {}));
    await TestBed.configureTestingModule({
      imports: [ProductFormPage],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([]),
        { provide: ActivatedRoute, useValue: { paramMap: routeParams.asObservable() } },
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    selectCompany(http);
    navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    const fixture = TestBed.createComponent(ProductFormPage);
    fixture.detectChanges();
    return { fixture, component: fixture.componentInstance, root: fixture.nativeElement as HTMLElement, routeParams };
  }
  afterEach(() => http?.verify());

  it('asocia errores y etiquetas y no envía un formulario inválido', async () => {
    const { component, fixture, root } = await setup();
    component.submit();
    fixture.detectChanges();
    http.expectNone('/api/admin/productos');
    expect(root.querySelector('#product-name')?.getAttribute('aria-invalid')).toBe('true');
    expect(root.querySelector('#product-name-error')?.textContent).toContain('obligatorio');
    for (const label of root.querySelectorAll('label[for]')) {
      expect(root.querySelector(`[id="${label.getAttribute('for')}"]`)).not.toBeNull();
    }
  });

  it('crea una sola vez mientras espera, conserva decimales y confirma solo tras respuesta', async () => {
    const { component, fixture, root } = await setup();
    component.form.setValue({ nombre: '  Camisa de lino  ', descripcion: ' Lino natural. ', precio: '149,9', slug: '', imagen_url: '', activo: true });
    component.submit();
    component.submit();
    fixture.detectChanges();
    const request = http.expectOne('/api/admin/productos');
    expect(request.request.body).toEqual({ nombre: 'Camisa de lino', descripcion: 'Lino natural.', precio: '149.90', imagen_url: null, activo: true });
    expect(navigate).not.toHaveBeenCalled();
    expect((root.querySelector('button[type="submit"]') as HTMLButtonElement).disabled).toBe(true);
    const cancel = [...root.querySelectorAll('a')].find(link => link.textContent?.trim() === 'Cancelar');
    expect(cancel?.hasAttribute('href')).toBe(false);
    request.flush(PRODUCT, { status: 201, statusText: 'Created' });
    await fixture.whenStable();
    expect(navigate).toHaveBeenCalledExactlyOnceWith(['/admin/productos']);
    expect(TestBed.inject(ProductService).notice()).toBe('Producto registrado correctamente.');
  });

  it('carga desde API y envía únicamente los campos modificados', async () => {
    const { component } = await setup('7');
    http.expectOne('/api/admin/productos/7').flush(PRODUCT);
    component.submit();
    http.expectNone('/api/admin/productos/7');
    expect(component.error()).toBe('No hay cambios para guardar.');
    component.form.controls.descripcion.setValue('Lino de manga larga.');
    component.submit();
    const update = http.expectOne('/api/admin/productos/7');
    expect(update.request.method).toBe('PATCH');
    expect(update.request.body).toEqual({ descripcion: 'Lino de manga larga.' });
    update.flush({ ...PRODUCT, descripcion: 'Lino de manga larga.' });
  });

  it('no permite borrar el identificador existente y descarta esquemas de imagen inseguros', async () => {
    const { component } = await setup('7');
    http.expectOne('/api/admin/productos/7').flush(PRODUCT);
    component.form.controls.slug.setValue('');
    component.form.controls.imagen_url.setValue('javascript:alert(1)');
    component.submit();
    expect(component.form.controls.slug.invalid).toBe(true);
    expect(component.form.controls.imagen_url.invalid).toBe(true);
    http.expectNone('/api/admin/productos/7');
  });

  it('conserva los datos del formulario ante un slug duplicado', async () => {
    const { component, fixture, root } = await setup();
    component.form.patchValue({ nombre: 'Camisa de lino', precio: '149.90', slug: 'camisa-de-lino' });
    component.submit();
    http.expectOne('/api/admin/productos').flush({ detail: 'slug duplicado; contenido técnico' }, { status: 409, statusText: 'Conflict' });
    fixture.detectChanges();
    expect(root.querySelector('[role="alert"]')?.textContent).toContain('Ya existe un producto');
    expect(root.textContent).not.toContain('contenido técnico');
    expect(component.form.controls.nombre.value).toBe('Camisa de lino');
    expect(component.saving()).toBe(false);
  });

  it('distingue un producto inexistente de un formulario nuevo', async () => {
    const { root, fixture } = await setup('99');
    http.expectOne('/api/admin/productos/99').flush({}, { status: 404, statusText: 'Not Found' });
    fixture.detectChanges();
    expect(root.querySelector('[role="alert"]')?.textContent).toContain('No encontramos este producto');
    expect(root.querySelector('form')).toBeNull();
  });

  it('impide cambiar de contexto durante el guardado y confirma el descarte de cambios', async () => {
    const { component } = await setup();
    component.form.patchValue({ nombre: 'Camisa de prueba', precio: '120.00' });
    component.form.markAsDirty();
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    expect(component.canLeave()).toBe(false);
    expect(confirm).toHaveBeenCalledOnce();
    confirm.mockReturnValue(true);
    expect(component.canLeave()).toBe(true);
    component.submit();
    expect(component.canLeave()).toBe(false);
    expect(component.form.disabled).toBe(true);
    http.expectOne('/api/admin/productos').flush(PRODUCT, { status: 201, statusText: 'Created' });
  });

  it('no duplica un alta confirmada aunque falle la navegación posterior', async () => {
    const { component, fixture, root } = await setup();
    navigate.mockRejectedValue(new Error('Navegación cancelada'));
    component.form.patchValue({ nombre: 'Camisa de prueba', precio: '120.00' });
    component.submit();
    http.expectOne('/api/admin/productos').flush(PRODUCT, { status: 201, statusText: 'Created' });
    await fixture.whenStable();
    fixture.detectChanges();
    component.submit();
    http.expectNone('/api/admin/productos');
    expect(root.textContent).toContain('Producto guardado');
    expect(root.querySelector('form')).toBeNull();
    expect(component.error()).toContain('se guardó');
  });

  it('borra el formulario anterior si se invalida su contexto empresarial', async () => {
    const { component, fixture, root } = await setup('7');
    const pending = http.expectOne('/api/admin/productos/7');
    TestBed.inject(CompanyService).select(2);
    expect(pending.cancelled).toBe(true);
    fixture.detectChanges();
    expect(component.original()).toBeNull();
    expect(root.querySelector('form')).toBeNull();
    component.submit();
    http.expectNone('/api/admin/productos/7');
  });

  it('descarta una respuesta tardía de guardar A al reutilizar la ruta para editar B', async () => {
    const { component, routeParams } = await setup('7');
    http.expectOne('/api/admin/productos/7').flush(PRODUCT);
    const lateSave = new Subject<Product>();
    vi.spyOn(TestBed.inject(ProductService), 'update').mockReturnValue(lateSave);
    component.form.controls.precio.setValue('200.00');
    component.submit();
    expect(component.saving()).toBe(true);

    // Angular puede reutilizar el componente al cambiar solo :id.
    routeParams.next(convertToParamMap({ id: '8' }));
    const productB = { ...PRODUCT, id: 8, nombre: 'Pantalón recto', slug: 'pantalon-recto' };
    http.expectOne('/api/admin/productos/8').flush(productB);
    lateSave.next({ ...PRODUCT, precio: '200.00' });
    lateSave.complete();

    expect(navigate).not.toHaveBeenCalled();
    expect(component.saved()).toBeNull();
    expect(component.original()).toEqual(productB);
    expect(component.form.controls.nombre.value).toBe('Pantalón recto');
    expect(component.form.enabled).toBe(true);
    expect(component.saving()).toBe(false);
    expect(TestBed.inject(ProductService).notice()).toBeNull();
  });

  it('cancela la carga de A aunque el nuevo identificador sea inválido', async () => {
    const { component, routeParams } = await setup('7');
    const pendingA = http.expectOne('/api/admin/productos/7');
    routeParams.next(convertToParamMap({ id: 'invalido' }));
    expect(pendingA.cancelled).toBe(true);
    expect(component.original()).toBeNull();
    expect(component.loading()).toBe(false);
    expect(component.loadError()).toContain('no es válida');
  });
});

describe('Directorio de productos', () => {
  let http: HttpTestingController;
  async function setup() {
    await TestBed.configureTestingModule({
      imports: [ProductListPage],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    selectCompany(http);
    const fixture = TestBed.createComponent(ProductListPage);
    fixture.detectChanges();
    return { fixture, component: fixture.componentInstance, root: fixture.nativeElement as HTMLElement };
  }
  afterEach(() => http?.verify());

  it('separa carga, lista vacía y datos reales de respuesta', async () => {
    const { root, fixture, component } = await setup();
    expect(root.querySelector('[role="status"]')?.textContent).toContain('Cargando productos');
    http.expectOne(request => request.url === '/api/admin/productos').flush({ items: [], total: 0, limit: 20, offset: 0 });
    fixture.detectChanges();
    expect(root.textContent).toContain('Esta empresa todavía no tiene productos');
    expect(root.querySelector('table')).toBeNull();
    component.reload();
    http.expectOne(request => request.url === '/api/admin/productos').flush({ items: [PRODUCT], total: 1, limit: 20, offset: 0 });
    fixture.detectChanges();
    expect(root.querySelector('tbody')?.textContent).toContain('Camisa de lino');
    expect(root.querySelector('tbody')?.textContent).toContain('Bs 149.90');
    expect(root.querySelector('[role="region"]')?.getAttribute('tabindex')).toBe('0');
    expect(root.querySelector('caption')?.textContent).toContain('Productos registrados');
  });

  it('cambia de página en servidor y reinicia offset al buscar', async () => {
    const { component } = await setup();
    http.expectOne(request => request.url === '/api/admin/productos').flush({ items: [PRODUCT], total: 41, limit: 20, offset: 0 });
    component.page(1);
    const second = http.expectOne(request => request.params.get('offset') === '20');
    second.flush({ items: [PRODUCT], total: 41, limit: 20, offset: 20 });
    component.filters.setValue({ q: 'lino', activo: 'false' });
    component.search();
    const search = http.expectOne(request => request.params.get('q') === 'lino');
    expect(search.request.params.get('offset')).toBe('0');
    expect(search.request.params.get('activo')).toBe('false');
    search.flush({ items: [], total: 0, limit: 20, offset: 0 });
  });

  it('muestra error controlado con reintento sin fingir que no hay productos', async () => {
    const { root, fixture } = await setup();
    http.expectOne(request => request.url === '/api/admin/productos').flush({ detail: 'SQL interno' }, { status: 500, statusText: 'Error' });
    fixture.detectChanges();
    expect(root.textContent).toContain('No pudimos cargar los productos');
    expect(root.textContent).not.toContain('Esta empresa todavía no tiene productos');
    expect(root.textContent).not.toContain('SQL interno');
    [...root.querySelectorAll('button')].find(button => button.textContent?.trim() === 'Reintentar')?.click();
    http.expectOne(request => request.url === '/api/admin/productos').flush({ items: [], total: 0, limit: 20, offset: 0 });
  });

  it('cambiar empresa limpia resultados y oculta escritura al operador', async () => {
    const { root, fixture } = await setup();
    const previous = http.expectOne(request => request.url === '/api/admin/productos');
    TestBed.inject(CompanyService).select(2);
    expect(previous.cancelled).toBe(true);
    const next = http.expectOne(request => request.url === '/api/admin/productos');
    expect(next.request.headers.get('X-Empresa-Id')).toBe('2');
    next.flush({ items: [PRODUCT], total: 1, limit: 20, offset: 0 });
    fixture.detectChanges();
    expect(root.textContent).toContain('Solo consulta');
    expect(root.querySelector('a[href="/admin/productos/nuevo"]')).toBeNull();
    expect(root.querySelector('a[href="/admin/productos/7/editar"]')).toBeNull();
  });
});

describe('Errores del servidor de productos', () => {
  it('no transforma un permiso denegado en datos vacíos ni muestra detalles internos', () => {
    expect(productError(new HttpErrorResponse({ status: 403, error: { detail: 'Interno' } }))).toContain('no tiene permiso');
    expect(productError(new HttpErrorResponse({ status: 500, error: { detail: 'Clave secreta' } }))).not.toContain('Clave secreta');
  });
});
