import { HttpRequest, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting, TestRequest } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { routes } from './app.routes';
import { authInterceptor } from './auth/auth.interceptor';
import { SESSION_KEY } from './auth/auth.service';
import { COMPANY_KEY, CompanyService } from './company/company.service';
import { Product } from './products/product.model';

const ADMIN = { id: 1, nombre: 'Administración de prueba', correo: 'admin@vestinova.test', rol: 'ADMINISTRADOR', activo: true };
const A = { id: 10, nombre: 'Empresa A', slug: 'empresa-a', activo: true, rol: 'ADMINISTRADOR' };
const B = { id: 20, nombre: 'Empresa B', slug: 'empresa-b', activo: true, rol: 'ADMINISTRADOR' };
const TOKEN = 'token-solo-del-contrato-http-de-prueba';
const PRODUCT: Product = {
  id: 7, nombre: 'Camisa de prueba A', slug: 'camisa-de-prueba-a', descripcion: 'Descripción inicial.',
  precio: '149.90', moneda: 'BOB', imagen_url: null, activo: true,
  creado_en: '2026-10-25T12:00:00Z', actualizado_en: '2026-10-25T12:00:00Z',
};

/** Integración de rutas, guardas, formularios e interceptor con HTTP controlado.
 * No equivale a prueba de navegador real ni escribe en PostgreSQL operativo. */
describe('Flujo administrativo con empresa: CU01 y registro/edición de CU05', () => {
  let http: HttpTestingController;
  let harness: RouterTestingHarness;
  let router: Router;

  beforeEach(() => sessionStorage.clear());
  afterEach(() => {
    http?.verify();
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  async function setup() {
    await TestBed.configureTestingModule({
      providers: [provideRouter(routes), provideHttpClient(withInterceptors([authInterceptor])), provideHttpClientTesting()],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
    harness = await RouterTestingHarness.create();
  }

  function root(): HTMLElement { return harness.fixture.nativeElement as HTMLElement; }

  async function request(match: string | ((request: HttpRequest<unknown>) => boolean)): Promise<TestRequest> {
    let found!: TestRequest;
    await vi.waitFor(() => { found = http.expectOne(match); });
    return found;
  }

  async function stable(): Promise<void> {
    await harness.fixture.whenStable();
    harness.detectChanges();
  }

  function fill(selector: string, value: string): void {
    const input = root().querySelector(selector) as HTMLInputElement | HTMLTextAreaElement;
    expect(input).not.toBeNull();
    input.value = value;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    harness.detectChanges();
  }

  function submit(): void {
    const form = root().querySelector('form');
    expect(form).not.toBeNull();
    form!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    harness.detectChanges();
  }

  function choose(companyId: number): void {
    const select = root().querySelector('#company-choice') as HTMLSelectElement;
    expect(select).not.toBeNull();
    select.value = String(companyId);
    select.dispatchEvent(new Event('change', { bubbles: true }));
    harness.detectChanges();
    submit();
  }

  function page(items: Product[]) { return { items, total: items.length, limit: 20, offset: 0 }; }

  it('recorre login, elección explícita, alta, edición, cambio de empresa y cierre desde las pantallas reales', async () => {
    await setup();
    await harness.navigateByUrl('/admin/login');
    fill('#login-email', ADMIN.correo);
    fill('#login-password', 'Clave de prueba!2026');
    submit();
    const login = await request('/api/auth/login');
    expect(login.request.headers.has('X-Empresa-Id')).toBe(false);
    login.flush({ access_token: TOKEN, token_type: 'bearer', expires_at: '2026-10-25T23:00:00Z', administrador: ADMIN });
    const companies = await request('/api/empresas');
    expect(companies.request.headers.get('Authorization')).toBe(`Bearer ${TOKEN}`);
    expect(companies.request.headers.has('X-Empresa-Id')).toBe(false);
    companies.flush([A, B]);
    await stable();
    expect(router.url).toBe('/admin/empresa');
    expect(TestBed.inject(CompanyService).active()).toBeNull();
    expect((root().querySelector('button[type="submit"]') as HTMLButtonElement).disabled).toBe(true);
    http.expectNone(request => request.url === '/api/admin/productos');

    choose(A.id);
    const firstList = await request(request => request.url === '/api/admin/productos');
    expect(firstList.request.headers.get('X-Empresa-Id')).toBe(String(A.id));
    firstList.flush(page([]));
    await stable();
    expect(router.url).toBe('/admin/productos');
    expect(root().textContent).toContain('Empresa A');
    (root().querySelector('a[href="/admin/productos/nuevo"]') as HTMLAnchorElement).click();
    await stable();
    fill('#product-name', PRODUCT.nombre);
    fill('#product-price', '149,90');
    fill('#product-description', PRODUCT.descripcion);
    submit();
    const create = await request('/api/admin/productos');
    expect(create.request.method).toBe('POST');
    expect(create.request.headers.get('X-Empresa-Id')).toBe(String(A.id));
    expect(create.request.body.precio).toBe('149.90');
    expect(create.request.body).not.toHaveProperty('empresa_id');
    create.flush(PRODUCT, { status: 201, statusText: 'Created' });
    (await request(request => request.url === '/api/admin/productos')).flush(page([PRODUCT]));
    await stable();
    expect(root().textContent).toContain('Producto registrado correctamente.');
    expect(root().querySelector('tbody')?.textContent).toContain(PRODUCT.nombre);

    (root().querySelector('a[href="/admin/productos/7/editar"]') as HTMLAnchorElement).click();
    const load = await request('/api/admin/productos/7');
    expect(load.request.headers.get('X-Empresa-Id')).toBe(String(A.id));
    load.flush(PRODUCT);
    await stable();
    fill('#product-description', 'Descripción editada en la empresa A.');
    submit();
    const patch = await request('/api/admin/productos/7');
    expect(patch.request.method).toBe('PATCH');
    expect(patch.request.headers.get('X-Empresa-Id')).toBe(String(A.id));
    expect(patch.request.body).toEqual({ descripcion: 'Descripción editada en la empresa A.' });
    patch.flush({ ...PRODUCT, descripcion: patch.request.body.descripcion });
    (await request(request => request.url === '/api/admin/productos')).flush(page([{ ...PRODUCT, descripcion: 'Descripción editada en la empresa A.' }]));
    await stable();
    expect(root().textContent).toContain('Cambios guardados en el producto.');

    (root().querySelector('a[href="/admin/empresa"]') as HTMLAnchorElement).click();
    await stable();
    choose(B.id);
    const otherList = await request(request => request.url === '/api/admin/productos');
    expect(otherList.request.headers.get('X-Empresa-Id')).toBe(String(B.id));
    otherList.flush(page([]));
    await stable();
    expect(root().textContent).toContain('Empresa B');
    expect(root().textContent).not.toContain(PRODUCT.nombre);
    expect(root().textContent).not.toContain('Cambios guardados en el producto.');

    const logout = [...root().querySelectorAll('button')].find(button => button.textContent?.trim() === 'Cerrar sesión');
    expect(logout).toBeDefined();
    logout!.click();
    const revoke = await request('/api/auth/logout');
    expect(revoke.request.headers.has('X-Empresa-Id')).toBe(false);
    revoke.flush(null, { status: 204, statusText: 'No Content' });
    await stable();
    expect(router.url).toBe('/admin/login');
    expect(sessionStorage.getItem(SESSION_KEY)).toBeNull();
    expect(sessionStorage.getItem(COMPANY_KEY)).toBeNull();
    await harness.navigateByUrl('/admin/productos');
    expect(router.url).toBe('/admin/login');
  });

  it('abre variantes desde la prenda, registra y edita una combinación y la consulta al volver a entrar', async () => {
    sessionStorage.setItem(SESSION_KEY, TOKEN);
    await setup();
    const navigation = harness.navigateByUrl('/admin/productos');
    (await request('/api/auth/me')).flush(ADMIN);
    (await request('/api/empresas')).flush([A]);
    (await request(value => value.url === '/api/admin/productos')).flush(page([PRODUCT]));
    await navigation;
    await stable();
    (root().querySelector('a[href="/admin/productos/7/variantes"]') as HTMLAnchorElement).click();
    (await request('/api/admin/productos/7')).flush(PRODUCT);
    (await request('/api/admin/productos/7/variantes')).flush([]);
    await stable();
    expect(router.url).toBe('/admin/productos/7/variantes');
    fill('#variant-size', ' m ');
    fill('#variant-color', ' verde ');
    submit();
    const create = await request('/api/admin/productos/7/variantes');
    expect(create.request.headers.get('X-Empresa-Id')).toBe(String(A.id));
    expect(create.request.body).toEqual({ talla: 'M', color: 'VERDE', activo: true });
    const variant = { id: 31, producto_id: 7, talla: 'M', color: 'VERDE', activo: true, creado_en: '2026-10-25T12:00:00Z' };
    create.flush(variant, { status: 201, statusText: 'Created' });
    await stable();
    (root().querySelector('[aria-label="Editar variante M VERDE"]') as HTMLButtonElement).click();
    await stable();
    fill('#variant-color', ' azul ');
    submit();
    const update = await request('/api/admin/variantes/31');
    expect(update.request.method).toBe('PATCH');
    expect(update.request.body).toEqual({ color: 'AZUL' });
    const edited = { ...variant, color: 'AZUL' };
    update.flush(edited);
    await stable();
    (root().querySelector('a.products-back') as HTMLAnchorElement).click();
    (await request(value => value.url === '/api/admin/productos')).flush(page([PRODUCT]));
    await stable();
    (root().querySelector('a[href="/admin/productos/7/variantes"]') as HTMLAnchorElement).click();
    (await request('/api/admin/productos/7')).flush(PRODUCT);
    (await request('/api/admin/productos/7/variantes')).flush([edited]);
    await stable();
    expect(root().querySelector('tbody')?.textContent).toContain('AZUL');
    expect(root().textContent).toContain('149.90');
    http.expectNone(value => value.url.includes('/inventario/'));
  });

  it('restaura la empresa guardada solo después de validar sesión y pertenencia con el servidor', async () => {
    sessionStorage.setItem(SESSION_KEY, TOKEN);
    sessionStorage.setItem(COMPANY_KEY, JSON.stringify({ usuario_id: ADMIN.id, empresa_id: B.id }));
    await setup();
    const navigation = harness.navigateByUrl('/admin/productos');
    const me = await request('/api/auth/me');
    expect(me.request.headers.has('X-Empresa-Id')).toBe(false);
    me.flush(ADMIN);
    http.expectNone(request => request.url === '/api/admin/productos');
    (await request('/api/empresas')).flush([A, B]);
    const list = await request(request => request.url === '/api/admin/productos');
    expect(list.request.headers.get('X-Empresa-Id')).toBe(String(B.id));
    list.flush(page([]));
    await navigation;
    await stable();
    expect(TestBed.inject(CompanyService).active()?.id).toBe(B.id);
    expect(root().textContent).toContain('Empresa B');
  });

  it('descarta una selección almacenada revocada y exige elegir entre las empresas vigentes', async () => {
    sessionStorage.setItem(SESSION_KEY, TOKEN);
    sessionStorage.setItem(COMPANY_KEY, JSON.stringify({ usuario_id: ADMIN.id, empresa_id: 999 }));
    await setup();
    const navigation = harness.navigateByUrl('/admin/productos');
    (await request('/api/auth/me')).flush(ADMIN);
    (await request('/api/empresas')).flush([A, B]);
    await navigation;
    await stable();
    expect(router.url).toBe('/admin/empresa');
    expect(TestBed.inject(CompanyService).active()).toBeNull();
    expect(sessionStorage.getItem(COMPANY_KEY)).toBeNull();
    http.expectNone(request => request.url.startsWith('/api/admin/productos'));
    const choices = [...root().querySelectorAll('#company-choice option')].map(option => option.textContent);
    expect(choices.join(' ')).toContain('Empresa A');
    expect(choices.join(' ')).toContain('Empresa B');
  });

  it('permite consulta al operador y protege tanto acciones visibles como URLs de escritura', async () => {
    sessionStorage.setItem(SESSION_KEY, TOKEN);
    await setup();
    const navigation = harness.navigateByUrl('/admin/productos/nuevo');
    (await request('/api/auth/me')).flush(ADMIN);
    (await request('/api/empresas')).flush([{ ...A, rol: 'OPERADOR' }]);
    const list = await request(request => request.url === '/api/admin/productos');
    expect(list.request.headers.get('X-Empresa-Id')).toBe(String(A.id));
    list.flush(page([PRODUCT]));
    await navigation;
    await stable();
    expect(router.url.split('?')[0]).toBe('/admin/productos');
    expect(root().querySelector('a[href="/admin/productos/nuevo"]')).toBeNull();
    expect(root().querySelector('a[href="/admin/productos/7/editar"]')).toBeNull();
    expect(root().querySelector('tbody')?.textContent).toContain(PRODUCT.nombre);
    await harness.navigateByUrl('/admin/productos/7/editar');
    await stable();
    expect(router.url.split('?')[0]).toBe('/admin/productos');
    http.expectNone('/api/admin/productos/7');
  });
});
