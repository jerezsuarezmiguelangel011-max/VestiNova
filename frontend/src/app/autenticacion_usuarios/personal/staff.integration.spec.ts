import { HttpRequest, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, TestRequest, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { Router, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { routes } from '../../app.routes';
import { authInterceptor } from '../autenticacion/auth.interceptor';
import { AuthService, SESSION_KEY } from '../autenticacion/auth.service';
import { COMPANY_KEY, CompanyService } from '../../organizacion_empresarial/empresa/company.service';
import { CompanyRole, Permission, StaffUser } from './staff.service';
import { StaffUsersPage } from './staff-users-page';
import { StaffRolesPage } from './staff-roles-page';

const PERMISSIONS = ['catalogo.consultar', 'catalogo.gestionar', 'usuarios.consultar', 'usuarios.crear', 'usuarios.editar', 'roles.consultar', 'roles.gestionar', 'sucursales.consultar'];
const COMPANY = { id: 10, nombre: 'Empresa A', slug: 'empresa-a', activo: true, rol: 'ADMINISTRADOR', rol_id: 1, rol_nombre: 'Administrador', rol_sistema: 'ADMINISTRADOR', permisos: PERMISSIONS };
const ACCESS = { empresa_id: 10, usuario_id: 1, nombre: 'Administrador local', rol_id: 1, rol_nombre: 'Administrador', rol_sistema: 'ADMINISTRADOR', permisos: PERMISSIONS };
const ROLES: CompanyRole[] = [
  { id: 1, empresa_id: 10, nombre: 'Administrador', descripcion: 'Sistema', codigo_sistema: 'ADMINISTRADOR', protegido: true, activo: true, permisos: PERMISSIONS },
  { id: 5, empresa_id: 10, nombre: 'Asistente', descripcion: 'Rol local', codigo_sistema: null, protegido: false, activo: true, permisos: ['catalogo.consultar'] },
];
const USER: StaffUser = { id: 8, empresa_id: 10, nombre: 'Persona local', correo: 'persona@example.test', activo: true, rol_id: 5, rol_nombre: 'Asistente', rol_sistema: null, sucursal_ids: [20], rol_activo: true, acceso_habilitado: true };
const BRANCHES = [{ id: 20, empresa_id: 10, codigo: 'CENTRO', nombre: 'Centro', activo: true }];
const CATALOG: Permission[] = [
  { codigo: 'catalogo.consultar', nombre: 'Consultar catálogo', descripcion: 'Consulta prendas', requiere: [] },
  { codigo: 'catalogo.gestionar', nombre: 'Gestionar catálogo', descripcion: 'Gestiona prendas', requiere: ['catalogo.consultar'] },
  { codigo: 'sucursales.consultar', nombre: 'Consultar sucursales', descripcion: 'Consulta sucursales', requiere: [] },
  { codigo: 'inventario.consultar', nombre: 'Consultar inventario', descripcion: 'Consulta existencias', requiere: ['catalogo.consultar', 'sucursales.consultar'] },
  { codigo: 'inventario.registrar', nombre: 'Registrar inventario', descripcion: 'Registra existencias', requiere: ['inventario.consultar'] },
];

describe('CU02 web con rutas, DOM y HTTP controlado', () => {
  let http: HttpTestingController; let harness: RouterTestingHarness;
  beforeEach(() => sessionStorage.clear());
  afterEach(() => { http?.verify(); vi.restoreAllMocks(); sessionStorage.clear(); });
  async function request(match: string | ((request: HttpRequest<unknown>) => boolean)): Promise<TestRequest> {
    let result!: TestRequest; await vi.waitFor(() => { result = http.expectOne(match); }); return result;
  }
  async function setup() {
    sessionStorage.setItem(SESSION_KEY, 'token-personal');
    sessionStorage.setItem(COMPANY_KEY, JSON.stringify({ usuario_id: 1, empresa_id: 10 }));
    await TestBed.configureTestingModule({ providers: [provideRouter(routes), provideHttpClient(withInterceptors([authInterceptor])), provideHttpClientTesting()] }).compileComponents();
    http = TestBed.inject(HttpTestingController); harness = await RouterTestingHarness.create();
  }
  async function bootstrapUsers(twoCompanies = false): Promise<StaffUsersPage> {
    await setup(); const navigation = harness.navigateByUrl('/admin/usuarios');
    (await request('/api/auth/me')).flush({ id: 1, nombre: 'Nombre global', correo: 'admin@example.test', rol: 'ADMINISTRADOR' });
    (await request('/api/empresas')).flush(twoCompanies ? [COMPANY, { ...COMPANY, id: 11, nombre: 'Empresa B', slug: 'b' }] : [COMPANY]);
    const access = await request('/api/admin/acceso');
    expect(access.request.headers.get('Authorization')).toBe('Bearer token-personal'); expect(access.request.headers.get('X-Empresa-Id')).toBe('10'); access.flush(ACCESS);
    (await request(req => req.url === '/api/admin/usuarios')).flush({ items: [USER], total: 21, limit: 20, offset: 0 });
    (await request('/api/admin/roles')).flush(ROLES); (await request('/api/admin/sucursales')).flush(BRANCHES);
    await navigation; harness.detectChanges(); return harness.fixture.debugElement.query(By.directive(StaffUsersPage)).componentInstance as StaffUsersPage;
  }
  function root(): HTMLElement { return harness.fixture.nativeElement as HTMLElement; }
  function input(id: string, value: string): void { const field = root().querySelector<HTMLInputElement>(`#${id}`)!; field.value = value; field.dispatchEvent(new Event(field.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true })); harness.detectChanges(); }

  it('lista, busca, pagina y crea sin recortar la contraseña Unicode', async () => {
    const page = await bootstrapUsers();
    expect(root().textContent).toContain('Persona local'); expect(root().querySelector('a[href="/admin/roles"]')).not.toBeNull();
    page.page(1); const second = http.expectOne(req => req.url === '/api/admin/usuarios' && req.params.get('offset') === '20'); second.flush({ items: [USER], total: 21, limit: 20, offset: 20 });
    input('staff-search', ' persona '); root().querySelector<HTMLFormElement>('.staff-filters')!.dispatchEvent(new Event('submit', { bubbles: true }));
    const search = http.expectOne(req => req.url === '/api/admin/usuarios' && req.params.get('q') === 'persona' && req.params.get('offset') === '0'); search.flush({ items: [USER], total: 1, limit: 20, offset: 0 });
    page.newUser(); harness.detectChanges(); input('staff-name', 'Persona nueva'); input('staff-email', 'nueva@example.test'); input('staff-password', ' Ábcdef1! '); input('staff-role', '5');
    root().querySelector<HTMLFormElement>('.staff-editor form')!.dispatchEvent(new Event('submit', { bubbles: true }));
    const create = http.expectOne(req => req.url === '/api/admin/usuarios' && req.method === 'POST');
    expect(create.request.body).toEqual({ nombre: 'Persona nueva', correo: 'nueva@example.test', password: ' Ábcdef1! ', rol_id: 5, sucursal_ids: [], activo: true });
    create.flush({ ...USER, id: 9 }); http.expectOne(req => req.url === '/api/admin/usuarios' && req.method === 'GET').flush({ items: [USER], total: 1, limit: 20, offset: 0 }); harness.detectChanges();
    expect(root().textContent).toContain('Persona agregada');
  });

  it('edita solo pertenencia, confirma cambios sensibles y conserva formulario ante último administrador 409', async () => {
    const page = await bootstrapUsers(); vi.spyOn(window, 'confirm').mockReturnValue(true);
    page.edit(USER); http.expectOne('/api/admin/usuarios/8').flush(USER); harness.detectChanges();
    expect(root().querySelector('#staff-email')).toBeNull(); expect(root().querySelector('#staff-password')).toBeNull();
    page.form.controls.nombre.setValue('Nombre de esta empresa'); page.form.controls.activo.setValue(false); page.submit();
    const update = http.expectOne('/api/admin/usuarios/8'); expect(update.request.method).toBe('PATCH'); expect(update.request.body).toEqual({ nombre: 'Nombre de esta empresa', activo: false });
    update.flush({ detail: 'La empresa debe conservar al menos un administrador activo.' }, { status: 409, statusText: 'Conflict' }); harness.detectChanges();
    expect(window.confirm).toHaveBeenCalled(); expect(page.editorOpen()).toBe(true); expect(page.form.controls.nombre.value).toBe('Nombre de esta empresa'); expect(root().textContent).toContain('al menos un administrador activo');
    page.form.controls.activo.setValue(true); page.submit(); const success = http.expectOne('/api/admin/usuarios/8'); success.flush({ ...USER, nombre: 'Nombre de esta empresa' });
    http.expectOne(req => req.url === '/api/admin/usuarios').flush({ items: [USER], total: 1, limit: 20, offset: 0 });
    expect(TestBed.inject(AuthService).user()?.nombre).toBe('Nombre global');
  });

  it('cancela detalle y mutación de otra empresa sin mostrar respuestas tardías', async () => {
    const page = await bootstrapUsers(true); const companies = TestBed.inject(CompanyService);
    page.edit(USER); const detail = http.expectOne('/api/admin/usuarios/8'); companies.select(11); expect(detail.cancelled).toBe(true); expect(page.contextChanged()).toBe(true); expect(page.result().items).toEqual([]); expect(page.editorOpen()).toBe(false);
    http.expectNone(req => req.url.startsWith('/api/admin/') && req.headers.get('X-Empresa-Id') === '11');
  });

  it('cancela una creación en curso al cambiar empresa', async () => {
    const page = await bootstrapUsers(true); page.newUser(); page.form.setValue({ nombre: 'Nuevo usuario', correo: 'new@example.test', password: 'Ábcdef1!', rol_id: '5', sucursal_ids: [], activo: true }); page.submit();
    const mutation = http.expectOne(req => req.url === '/api/admin/usuarios' && req.method === 'POST'); TestBed.inject(CompanyService).select(11);
    expect(mutation.cancelled).toBe(true); expect(page.notice()).toBeNull(); expect(page.saving()).toBe(false); expect(page.form.disabled).toBe(true);
  });

  it('revalida permisos al abrir una URL, oculta acciones revocadas y conserva la sesión ante 403', async () => {
    const page = await bootstrapUsers(); page.reload(); http.expectOne(req => req.url === '/api/admin/usuarios').flush({ detail: 'Revocado' }, { status: 403, statusText: 'Forbidden' });
    expect(TestBed.inject(AuthService).token()).toBe('token-personal'); harness.detectChanges(); expect(root().textContent).toContain('Actualizar accesos');
    page.refreshAccess(); http.expectOne('/api/admin/acceso').flush({ ...ACCESS, permisos: ['usuarios.consultar'] }); http.expectOne(req => req.url === '/api/admin/usuarios').flush({ items: [USER], total: 1, limit: 20, offset: 0 }); harness.detectChanges();
    expect(root().textContent).not.toContain('Agregar persona'); expect(root().querySelector('a[href="/admin/roles"]')).toBeNull(); expect(root().querySelector('button[aria-label="Editar acceso de Persona local"]')).toBeNull();
    const navigation = harness.navigateByUrl('/admin/roles'); (await request('/api/admin/acceso')).flush({ ...ACCESS, permisos: ['usuarios.consultar'] });
    (await request('/api/auth/contexto')).flush({ empresa: COMPANY, sucursales: [] }); await navigation;
    expect(TestBed.inject(Router).url).toBe('/admin/acceso?motivo=permiso'); http.expectNone('/api/admin/roles');
  });

  it('conserva roles del sistema, crea un rol con requisitos transitivos y lo desactiva con confirmación', async () => {
    await bootstrapUsers(); const navigation = harness.navigateByUrl('/admin/roles'); (await request('/api/admin/acceso')).flush(ACCESS); (await request('/api/admin/roles')).flush(ROLES); (await request('/api/admin/permisos')).flush(CATALOG);
    await navigation; const page = harness.fixture.debugElement.query(By.directive(StaffRolesPage)).componentInstance as StaffRolesPage; page.edit(ROLES[0]); harness.detectChanges(); expect(page.form.disabled).toBe(true); expect(root().textContent).toContain('Este rol del sistema está protegido'); page.submit(); http.expectNone(req => req.method === 'PATCH');
    page.close(); page.newRole(); page.form.controls.nombre.setValue('Inventario local'); page.togglePermission('inventario.registrar', true); expect(page.form.controls.permisos.value).toEqual(['catalogo.consultar', 'inventario.consultar', 'inventario.registrar', 'sucursales.consultar']);
    page.togglePermission('catalogo.consultar', false); expect(page.form.controls.permisos.value).toEqual(['sucursales.consultar']); page.togglePermission('catalogo.gestionar', true); page.submit();
    const create = http.expectOne(req => req.url === '/api/admin/roles' && req.method === 'POST'); expect(create.request.body.permisos).toEqual(['catalogo.consultar', 'catalogo.gestionar', 'sucursales.consultar']);
    const custom = { ...ROLES[1], id: 6, nombre: 'Inventario local', permisos: create.request.body.permisos }; create.flush(custom); http.expectOne('/api/admin/acceso').flush(ACCESS);
    vi.spyOn(window, 'confirm').mockReturnValue(true); page.edit(custom); page.form.controls.activo.setValue(false); page.submit(); const patch = http.expectOne('/api/admin/roles/6'); expect(patch.request.body).toEqual({ activo: false }); patch.flush({ ...custom, activo: false }); http.expectOne('/api/admin/acceso').flush(ACCESS);
    expect(page.roles().find(role => role.id === 6)?.activo).toBe(false); expect(window.confirm).toHaveBeenCalled();
  });
});
