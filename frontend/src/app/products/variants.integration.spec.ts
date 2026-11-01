import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture } from '@angular/core/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, ParamMap, convertToParamMap, provideRouter } from '@angular/router';
import { BehaviorSubject } from 'rxjs';
import { authInterceptor } from '../auth/auth.interceptor';
import { SESSION_KEY } from '../auth/auth.service';
import { CompanyService } from '../company/company.service';
import { Product } from './product.model';
import { VariantPage } from './variant-page';
import { Variant } from './variant.model';

const TOKEN = 'token-solo-pruebas-variantes';
const COMPANY = { id: 10, nombre: 'Empresa de prueba A', slug: 'empresa-a', activo: true, rol: 'ADMINISTRADOR' };
const OTHER_COMPANY = { id: 20, nombre: 'Empresa de prueba B', slug: 'empresa-b', activo: true, rol: 'ADMINISTRADOR' };
const PRODUCT: Product = {
  id: 7, nombre: 'Camisa de prueba', slug: 'camisa-de-prueba', descripcion: 'Prenda de prueba aislada.',
  precio: '149.90', moneda: 'BOB', imagen_url: null, activo: true,
  creado_en: '2026-10-25T12:00:00Z', actualizado_en: '2026-10-25T12:00:00Z',
};
const VARIANT: Variant = {
  id: 31, producto_id: PRODUCT.id, talla: 'M', color: 'VERDE', activo: true,
  creado_en: '2026-10-25T12:05:00Z',
};

/** Componentes/formularios reales e interceptor con HTTP controlado.
 * No ejecuta un navegador real ni inserta datos en PostgreSQL operativo. */
describe('CU05: variantes por talla y color en la empresa autorizada', () => {
  let http: HttpTestingController;
  let fixture: ComponentFixture<VariantPage>;
  let component: VariantPage;
  let routeParams: BehaviorSubject<ParamMap>;

  beforeEach(() => {
    sessionStorage.clear();
    sessionStorage.setItem(SESSION_KEY, TOKEN);
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });
  afterEach(() => {
    http?.expectNone(request => request.url.includes('/inventario/'));
    http?.verify();
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  function root(): HTMLElement { return fixture.nativeElement as HTMLElement; }

  async function setup(variants: Variant[] | null = [], role = 'ADMINISTRADOR') {
    routeParams = new BehaviorSubject(convertToParamMap({ id: String(PRODUCT.id) }));
    await TestBed.configureTestingModule({
      imports: [VariantPage],
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])), provideHttpClientTesting(), provideRouter([]),
        { provide: ActivatedRoute, useValue: { paramMap: routeParams.asObservable() } },
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    const companies = TestBed.inject(CompanyService);
    companies.ensureForUser(1).subscribe();
    http.expectOne('/api/empresas').flush([{ ...COMPANY, rol: role }, OTHER_COMPANY]);
    companies.select(COMPANY.id);
    fixture = TestBed.createComponent(VariantPage);
    component = fixture.componentInstance;
    fixture.detectChanges();
    if (variants !== null) respond(variants);
    return component;
  }

  function respond(variants: Variant[]) {
    const product = http.expectOne(`/api/admin/productos/${PRODUCT.id}`);
    const list = http.expectOne(`/api/admin/productos/${PRODUCT.id}/variantes`);
    for (const request of [product, list]) {
      expect(request.request.headers.get('Authorization')).toBe(`Bearer ${TOKEN}`);
      expect(request.request.headers.get('X-Empresa-Id')).toBe(String(COMPANY.id));
    }
    product.flush(PRODUCT);
    list.flush(variants);
    fixture.detectChanges();
  }

  function fill(id: string, value: string) {
    const control = root().querySelector(`#${id}`) as HTMLInputElement;
    expect(control).not.toBeNull();
    control.value = value;
    control.dispatchEvent(new Event('input', { bubbles: true }));
    fixture.detectChanges();
  }

  function submit() {
    const form = root().querySelector('form');
    expect(form).not.toBeNull();
    form!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    fixture.detectChanges();
  }

  it('consulta la prenda y sus variantes sin solicitar inventario ni cambiar el precio', async () => {
    await setup([VARIANT]);
    expect(root().textContent).toContain(PRODUCT.nombre);
    expect(root().textContent).toContain('149.90');
    expect(root().textContent).toContain('M');
    expect(root().textContent).toContain('VERDE');
    expect(component.variants()).toEqual([VARIANT]);
    expect(root().querySelector('input[formControlName="precio"]')).toBeNull();
  });

  it('registra, edita solo el campo cambiado y vuelve a consultar la variante guardada', async () => {
    await setup();
    fill('variant-size', ' m ');
    fill('variant-color', ' verde ');
    submit();
    component.submit();
    const create = http.expectOne(`/api/admin/productos/${PRODUCT.id}/variantes`);
    expect(create.request.method).toBe('POST');
    expect(create.request.headers.get('X-Empresa-Id')).toBe(String(COMPANY.id));
    expect(create.request.body).toEqual({ talla: 'M', color: 'VERDE', activo: true });
    create.flush(VARIANT, { status: 201, statusText: 'Created' });
    fixture.detectChanges();
    expect(component.variants()).toEqual([VARIANT]);
    expect(component.notice()).toBeTruthy();

    const edit = root().querySelector('[aria-label="Editar variante M VERDE"]') as HTMLButtonElement;
    expect(edit).not.toBeNull();
    edit.click();
    fixture.detectChanges();
    fill('variant-color', ' azul ');
    submit();
    const update = http.expectOne(`/api/admin/variantes/${VARIANT.id}`);
    expect(update.request.method).toBe('PATCH');
    expect(update.request.body).toEqual({ color: 'AZUL' });
    expect(update.request.headers.get('X-Empresa-Id')).toBe(String(COMPANY.id));
    const edited = { ...VARIANT, color: 'AZUL' };
    update.flush(edited);
    fixture.detectChanges();
    expect(component.variants()).toEqual([edited]);

    component.load();
    respond([edited]);
    expect(component.variants()).toEqual([edited]);
    expect(root().textContent).toContain('AZUL');
    expect(component.product()?.precio).toBe('149.90');
  });

  it('valida campos vacíos y límites y conserva etiquetas visibles', async () => {
    await setup();
    submit();
    expect(component.form.invalid).toBe(true);
    http.expectNone(request => request.method !== 'GET');
    fill('variant-size', 'S'.repeat(31));
    fill('variant-color', 'C'.repeat(61));
    submit();
    expect(component.form.invalid).toBe(true);
    http.expectNone(request => request.method !== 'GET');
    for (const id of ['variant-size', 'variant-color', 'variant-active']) {
      expect(root().querySelector(`label[for="${id}"]`)?.textContent?.trim()).toBeTruthy();
    }
  });

  it('rechaza en pantalla una combinación duplicada normalizada, incluso si está inactiva', async () => {
    await setup([{ ...VARIANT, activo: false }]);
    fill('variant-size', ' m ');
    fill('variant-color', ' verde ');
    submit();
    expect(component.error()).toBeTruthy();
    http.expectNone(request => request.method === 'POST');
    expect(component.variants()).toHaveLength(1);
  });

  it('maneja un duplicado concurrente del servidor conservando lo escrito', async () => {
    await setup();
    fill('variant-size', 'M');
    fill('variant-color', 'VERDE');
    submit();
    http.expectOne(`/api/admin/productos/${PRODUCT.id}/variantes`).flush(
      { detail: 'Ya existe esa combinación de talla y color para el producto.' },
      { status: 409, statusText: 'Conflict' },
    );
    fixture.detectChanges();
    expect(component.error()).toBeTruthy();
    expect(component.variants()).toEqual([]);
    expect((root().querySelector('#variant-size') as HTMLInputElement).value).toBe('M');
    expect((root().querySelector('#variant-color') as HTMLInputElement).value).toBe('VERDE');
    expect(component.saving()).toBe(false);
  });

  it('explica la protección de historial sin reescribir la variante ni descartar su corrección', async () => {
    await setup([VARIANT]);
    component.edit(VARIANT);
    fixture.detectChanges();
    fill('variant-size', 'L');
    submit();
    http.expectOne(`/api/admin/variantes/${VARIANT.id}`).flush(
      { detail: 'No se puede cambiar la talla o el color de una variante con existencias o movimientos registrados. Desactívala y crea otra variante.' },
      { status: 409, statusText: 'Conflict' },
    );
    fixture.detectChanges();
    expect(component.error()).toMatch(/historial|existencias|movimientos/i);
    expect(component.variants()).toEqual([VARIANT]);
    expect((root().querySelector('#variant-size') as HTMLInputElement).value).toBe('L');
    expect(component.editing()?.id).toBe(VARIANT.id);
  });

  it('permite consultar al operador sin formularios ni acciones de escritura', async () => {
    await setup([VARIANT], 'OPERADOR');
    expect(root().querySelector('form')).toBeNull();
    expect(root().querySelector('[aria-label="Editar variante M VERDE"]')).toBeNull();
    expect(component.variants()).toEqual([VARIANT]);
    component.edit(VARIANT);
    component.form.patchValue({ talla: 'L', color: 'AZUL', activo: true });
    component.submit();
    http.expectNone(request => request.method === 'POST' || request.method === 'PATCH');
  });

  it('muestra el recurso ajeno/no disponible como error, sin un formulario de alta ficticio', async () => {
    await setup(null);
    const product = http.expectOne(`/api/admin/productos/${PRODUCT.id}`);
    const variants = http.expectOne(`/api/admin/productos/${PRODUCT.id}/variantes`);
    product.flush({ detail: 'Producto no encontrado.' }, { status: 404, statusText: 'Not Found' });
    expect(variants.cancelled).toBe(true);
    fixture.detectChanges();
    expect(component.loadError()).toBeTruthy();
    expect(component.product()).toBeNull();
    expect(root().querySelector('form')).toBeNull();
  });

  it('cancela respuestas anteriores y limpia datos cuando cambia la empresa', async () => {
    await setup(null);
    const product = http.expectOne(`/api/admin/productos/${PRODUCT.id}`);
    const variants = http.expectOne(`/api/admin/productos/${PRODUCT.id}/variantes`);
    TestBed.inject(CompanyService).select(OTHER_COMPANY.id);
    fixture.detectChanges();
    expect(product.cancelled).toBe(true);
    expect(variants.cancelled).toBe(true);
    expect(component.contextChanged()).toBe(true);
    expect(component.product()).toBeNull();
    expect(component.variants()).toEqual([]);
    expect(root().querySelector('form')).toBeNull();
    component.submit();
    http.expectNone(request => request.method === 'POST' || request.method === 'PATCH');
  });

  it('distingue una caída temporal de una lista vacía y permite reintentar', async () => {
    await setup(null);
    http.expectOne(`/api/admin/productos/${PRODUCT.id}`).flush(PRODUCT);
    http.expectOne(`/api/admin/productos/${PRODUCT.id}/variantes`).flush(
      { detail: 'Información técnica interna' }, { status: 503, statusText: 'Unavailable' },
    );
    fixture.detectChanges();
    expect(component.loadError()).toBeTruthy();
    expect(root().textContent).not.toContain('Información técnica interna');
    expect(root().querySelector('form')).toBeNull();
    const retry = [...root().querySelectorAll('button')].find(button => button.textContent?.trim() === 'Reintentar');
    expect(retry).toBeDefined();
    retry!.click();
    respond([VARIANT]);
    expect(component.loadError()).toBeNull();
    expect(component.variants()).toEqual([VARIANT]);
  });

  it('confirma el descarte y no permite abandonar un guardado todavía pendiente', async () => {
    await setup();
    fill('variant-size', 'M');
    fill('variant-color', 'VERDE');
    vi.mocked(window.confirm).mockReturnValue(false);
    expect(component.canLeave()).toBe(false);
    vi.mocked(window.confirm).mockReturnValue(true);
    expect(component.canLeave()).toBe(true);
    submit();
    expect(component.canLeave()).toBe(false);
    http.expectOne(`/api/admin/productos/${PRODUCT.id}/variantes`).flush(VARIANT, { status: 201, statusText: 'Created' });
    expect(component.canLeave()).toBe(true);
  });

  it.each(['POST', 'PATCH'] as const)('cancela %s de la prenda anterior al reutilizar la ruta para otra prenda', async method => {
    await setup([VARIANT]);
    if (method === 'PATCH') {
      component.edit(VARIANT);
      fixture.detectChanges();
    }
    fill('variant-size', 'L');
    fill('variant-color', 'AZUL');
    submit();
    const mutation = http.expectOne(method === 'POST'
      ? `/api/admin/productos/${PRODUCT.id}/variantes`
      : `/api/admin/variantes/${VARIANT.id}`);
    expect(mutation.request.method).toBe(method);

    routeParams.next(convertToParamMap({ id: '8' }));
    fixture.detectChanges();
    expect(mutation.cancelled).toBe(true);
    const nextProduct = { ...PRODUCT, id: 8, nombre: 'Otra prenda', slug: 'otra-prenda' };
    const nextVariant = { ...VARIANT, id: 41, producto_id: 8, talla: 'XL', color: 'BLANCO' };
    http.expectOne('/api/admin/productos/8').flush(nextProduct);
    http.expectOne('/api/admin/productos/8/variantes').flush([nextVariant]);
    fixture.detectChanges();

    expect(component.product()?.id).toBe(8);
    expect(component.variants()).toEqual([nextVariant]);
    expect(component.editing()).toBeNull();
    expect(component.notice()).toBeNull();
    expect(component.saving()).toBe(false);
    expect(root().textContent).toContain('Otra prenda');
    expect(root().textContent).not.toContain('Variante registrada correctamente.');
    expect(root().textContent).not.toContain('Cambios guardados en la variante.');
  });

  it('cancela las consultas pendientes al pasar de una prenda a una dirección inválida', async () => {
    await setup(null);
    const product = http.expectOne(`/api/admin/productos/${PRODUCT.id}`);
    const variants = http.expectOne(`/api/admin/productos/${PRODUCT.id}/variantes`);
    routeParams.next(convertToParamMap({ id: 'direccion-invalida' }));
    fixture.detectChanges();

    expect(product.cancelled).toBe(true);
    expect(variants.cancelled).toBe(true);
    expect(component.loading()).toBe(false);
    expect(component.product()).toBeNull();
    expect(component.variants()).toEqual([]);
    expect(component.loadError()).toMatch(/dirección.*válida/i);
    expect(root().querySelector('form')).toBeNull();
    component.submit();
    http.expectNone(request => request.method === 'POST' || request.method === 'PATCH');
    http.expectNone(request => request.url.includes('direccion-invalida'));
  });
});
