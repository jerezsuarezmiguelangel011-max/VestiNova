import { HttpRequest, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, TestRequest, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { routes } from '../app.routes';
import { authInterceptor } from '../auth/auth.interceptor';
import { CUSTOMER_SESSION_KEY, CustomerAuthService } from './customer-auth.service';
import { CustomerAccessPage } from './customer-access-page';
import { PASSWORD_POLICY_MESSAGE } from './password-policy';

const STORE = { slug: 'tienda-a', nombre: 'Tienda A' };
const CUSTOMER = { id: 1, nombre: 'Cliente de prueba', correo: 'cliente@example.test', rol: 'CLIENTE', empresa: STORE };
const RESPONSE = { access_token: 'token-cliente', token_type: 'bearer', expires_at: '2026-10-25T23:00:00Z', cliente: CUSTOMER };

/** Rutas/componentes reales con respuestas HTTP simuladas; no prueba PostgreSQL ni un navegador físico. */
describe('Recorrido web CU01 del cliente por tienda', () => {
  let http: HttpTestingController;
  let harness: RouterTestingHarness;
  let router: Router;
  beforeEach(() => sessionStorage.clear());
  afterEach(() => { http?.verify(); sessionStorage.clear(); vi.restoreAllMocks(); });
  async function setup() {
    await TestBed.configureTestingModule({ providers: [provideRouter(routes), provideHttpClient(withInterceptors([authInterceptor])), provideHttpClientTesting()] }).compileComponents();
    http = TestBed.inject(HttpTestingController); router = TestBed.inject(Router);
    harness = await RouterTestingHarness.create();
  }
  async function request(match: string | ((request: HttpRequest<unknown>) => boolean)): Promise<TestRequest> {
    let found!: TestRequest;
    await vi.waitFor(() => { found = http.expectOne(match); });
    return found;
  }
  function root(): HTMLElement { return harness.fixture.nativeElement as HTMLElement; }
  async function stable() { await harness.fixture.whenStable(); harness.detectChanges(); }
  function fill(selector: string, value: string) {
    const input = root().querySelector(selector) as HTMLInputElement;
    expect(input).not.toBeNull(); input.value = value; input.dispatchEvent(new Event('input', { bubbles: true })); harness.detectChanges();
  }
  function submit() { root().querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); harness.detectChanges(); }
  function click(text: string) { const button = [...root().querySelectorAll('button')].find(button => button.textContent?.trim() === text); expect(button).toBeDefined(); button!.click(); harness.detectChanges(); }
  async function access() {
    const navigation = harness.navigateByUrl('/tienda/tienda-a/acceso');
    (await request('/api/tiendas/tienda-a')).flush(STORE);
    await navigation; await stable();
  }

  it('registra, presenta cuenta exclusiva de tienda y confirma cierre tras reintento', async () => {
    await setup(); await access();
    expect(root().textContent).toContain('Tienda A');
    expect(root().querySelector('#company-choice')).toBeNull();
    click('Crear cuenta');
    fill('#customer-name', ' Cliente de prueba '); fill('#customer-email', 'Cliente@Example.test');
    fill('#customer-password', ' Clave1! '); fill('#customer-confirm', ' Clave1! '); submit();
    const registration = await request('/api/tiendas/tienda-a/cuenta/registro');
    expect(registration.request.body).toEqual({ nombre: 'Cliente de prueba', correo: 'cliente@example.test', password: ' Clave1! ' });
    registration.flush(RESPONSE, { status: 201, statusText: 'Created' });
    await stable();
    expect(router.url).toBe('/tienda/tienda-a/cuenta');
    expect(root().textContent).toContain(CUSTOMER.nombre);
    expect(root().querySelector('.rail')).toBeNull();
    click('Cerrar sesión');
    (await request('/api/tiendas/tienda-a/cuenta/logout')).flush({}, { status: 503, statusText: 'Unavailable' });
    await stable();
    expect(root().textContent).toContain('Reintenta');
    expect(sessionStorage.getItem(CUSTOMER_SESSION_KEY)).not.toBeNull();
    click('Cerrar sesión');
    (await request('/api/tiendas/tienda-a/cuenta/logout')).flush(null, { status: 204, statusText: 'No Content' });
    (await request('/api/tiendas/tienda-a')).flush(STORE);
    await stable();
    expect(router.url).toBe('/tienda/tienda-a/acceso');
    expect(sessionStorage.getItem(CUSTOMER_SESSION_KEY)).toBeNull();
  });

  it('valida registro completo y confirmación sin imponer la política nueva al login', async () => {
    await setup(); await access(); click('Crear cuenta');
    fill('#customer-name', 'ab'); fill('#customer-email', 'invalido');
    fill('#customer-password', 'abc'); fill('#customer-confirm', 'distinta'); submit();
    expect(root().textContent).toContain(PASSWORD_POLICY_MESSAGE);
    expect(root().textContent).toContain('Las contraseñas deben coincidir');
    expect(root().textContent).toContain('entre 3 y 120');
    http.expectNone('/api/tiendas/tienda-a/cuenta/registro');
    click('Iniciar sesión'); fill('#customer-email', CUSTOMER.correo); fill('#customer-password', 'abc'); submit();
    const page = harness.routeDebugElement?.componentInstance as CustomerAccessPage;
    expect(Object.fromEntries(Object.entries(page.form.controls).map(([key, control]) => [key, control.errors]))).toEqual({ nombre: null, correo: null, password: null, confirmacion: null });
    const login = await request('/api/tiendas/tienda-a/cuenta/login');
    expect(login.request.body.password).toBe('abc');
    login.flush({}, { status: 401, statusText: 'Unauthorized' }); await stable();
    expect(root().textContent).toContain('no son válidos');
  });

  it('no entra al panel administrativo con una sesión exclusiva de cliente', async () => {
    await setup();
    TestBed.inject(CustomerAuthService).login('tienda-a', { correo: CUSTOMER.correo, password: 'x' }).subscribe();
    (await request('/api/tiendas/tienda-a/cuenta/login')).flush(RESPONSE);
    await harness.navigateByUrl('/admin/productos'); await stable();
    expect(router.url).toBe('/admin/login');
    http.expectNone('/api/empresas');
    http.expectNone(value => value.url.startsWith('/api/admin/'));
  });

  it('restaura una cuenta guardada consultando la API antes de presentar datos', async () => {
    await setup();
    // Nueva instancia del servicio equivale al inicio de aplicación, con token y sin identidad.
    sessionStorage.setItem(CUSTOMER_SESSION_KEY, JSON.stringify({ tienda: STORE.slug, token: RESPONSE.access_token }));
    const navigation = harness.navigateByUrl('/tienda/tienda-a/cuenta');
    const me = await request('/api/tiendas/tienda-a/cuenta/me');
    expect(root().textContent).not.toContain(CUSTOMER.nombre);
    me.flush(CUSTOMER); await navigation; await stable();
    expect(root().textContent).toContain(CUSTOMER.nombre);
    expect(router.url).toBe('/tienda/tienda-a/cuenta');
  });

  it('una restauración no verificable oculta la cuenta y permite reintentar', async () => {
    await setup();
    sessionStorage.setItem(CUSTOMER_SESSION_KEY, JSON.stringify({ tienda: STORE.slug, token: RESPONSE.access_token }));
    const navigation = harness.navigateByUrl('/tienda/tienda-a/cuenta');
    (await request('/api/tiendas/tienda-a/cuenta/me')).flush({}, { status: 503, statusText: 'Unavailable' });
    (await request('/api/tiendas/tienda-a')).flush(STORE);
    (await request('/api/tiendas/tienda-a/cuenta/me')).flush({}, { status: 503, statusText: 'Unavailable' });
    await navigation; await stable();
    expect(root().textContent).not.toContain(CUSTOMER.nombre);
    expect(root().querySelector('form')).toBeNull();
    expect(root().textContent).toContain('Reintentar');
    click('Reintentar');
    (await request('/api/tiendas/tienda-a')).flush(STORE);
    (await request('/api/tiendas/tienda-a/cuenta/me')).flush(CUSTOMER);
    await stable();
    expect(router.url).toBe('/tienda/tienda-a/cuenta');
  });

  it('muestra conflicto de correo de esa tienda y no expone detalles internos', async () => {
    await setup(); await access(); click('Crear cuenta');
    fill('#customer-name', CUSTOMER.nombre); fill('#customer-email', CUSTOMER.correo);
    fill('#customer-password', 'Clave123!'); fill('#customer-confirm', 'Clave123!'); submit();
    (await request('/api/tiendas/tienda-a/cuenta/registro')).flush({ detail: 'SQL privado' }, { status: 409, statusText: 'Conflict' });
    await stable();
    expect(root().textContent).toContain('ya está registrado en esta tienda');
    expect(root().textContent).not.toContain('SQL privado');
  });

  it('cancela un envío anterior al cambiar el enlace público de tienda', async () => {
    await setup(); await access();
    fill('#customer-email', CUSTOMER.correo); fill('#customer-password', 'x'); submit();
    const previous = await request('/api/tiendas/tienda-a/cuenta/login');
    const navigation = harness.navigateByUrl('/tienda/tienda-b/acceso');
    (await request('/api/tiendas/tienda-b')).flush({ slug: 'tienda-b', nombre: 'Tienda B' });
    await navigation; await stable();
    expect(previous.cancelled).toBe(true);
    expect(router.url).toBe('/tienda/tienda-b/acceso');
    expect(root().textContent).toContain('Tienda B');
    expect(TestBed.inject(CustomerAuthService).customer()).toBeNull();
  });
});
