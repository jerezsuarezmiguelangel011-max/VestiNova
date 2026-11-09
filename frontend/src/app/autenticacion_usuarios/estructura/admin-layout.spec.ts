import { computed, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { AuthService } from '../autenticacion/auth.service';
import { CompanyService, type Company } from '../../organizacion_empresarial/empresa/company.service';
import { AdminLayout } from './admin-layout';

describe('Menú administrativo por rol efectivo de empresa', () => {
  async function setup() {
    const active = signal<Company>({
      id: 1, slug: 'demo-moda-andina', nombre: 'Moda Andina Demo',
      activo: true, rol: 'CAJERO',
      permisos: ['catalogo.consultar', 'inventario.consultar',
        'postventa.consultar', 'postventa.gestionar'],
    });
    const hasPermission = (value: string) => (active().permisos ?? []).includes(value);
    const company = {
      active: active.asReadonly(),
      companies: computed(() => [active()]),
      hasPermission,
      canViewProducts: () => ['ADMINISTRADOR', 'OPERADOR'].includes(active().rol) && hasPermission('catalogo.consultar'),
      canManage: () => hasPermission('catalogo.gestionar'),
      canManageBranches: () => hasPermission('sucursales.gestionar'),
      canViewUsers: () => hasPermission('usuarios.consultar'),
      canViewRoles: () => hasPermission('roles.consultar'),
      canViewAudit: () => hasPermission('auditoria.consultar'),
      canViewPromotions: () => hasPermission('promociones.consultar'),
      canManagePromotions: () => hasPermission('promociones.gestionar'),
      canViewProcurement: () => hasPermission('abastecimiento.consultar'),
      canViewPlan: () => hasPermission('plan.consultar'),
    };
    const auth = {
      user: signal({ id: 2, nombre: 'Caja Demo', correo: 'caja@vestinova.test',
        rol: 'ADMINISTRADOR', es_superadministrador: false }),
      logout: () => of(undefined),
    };
    await TestBed.configureTestingModule({
      imports: [AdminLayout],
      providers: [
        provideRouter([]),
        { provide: CompanyService, useValue: company },
        { provide: AuthService, useValue: auth },
      ],
    }).compileComponents();
    const fixture = TestBed.createComponent(AdminLayout);
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;
    const links = () => [...root.querySelectorAll<HTMLAnchorElement>('.rail__nav a')]
      .map(link => ({ href: link.getAttribute('href'), text: link.textContent?.trim() }));
    return { fixture, active, root, links };
  }

  it('Cajero solo ve sus operaciones y consulta el catálogo sin editar prendas', async () => {
    const { root, links } = await setup();
    const urls = links().map(item => item.href);
    expect(urls).toContain('/admin/caja');
    expect(urls).toContain('/admin/atencion-reservas');
    expect(urls).toContain('/admin/reservas');
    expect(urls).toContain('/admin/postventa');
    expect(urls).toContain('/admin/catalogo-consulta');
    expect(urls).toContain('/admin/acceso');

    expect(urls).not.toContain('/admin/inventario');
    expect(urls).not.toContain('/admin/productos');
    expect(urls).not.toContain('/admin/promociones');
    expect(urls).not.toContain('/admin/conciliacion');
    expect(urls).not.toContain('/admin/abastecimiento');
    expect(urls).not.toContain('/admin/usuarios');
    expect(urls).not.toContain('/admin/reportes-ia');
    expect(urls).not.toContain('/admin/dashboard-predictivo');
    expect(root.textContent).toContain('Consultar catálogo · solo lectura');
    expect(root.textContent).toContain('Operaciones de caja');
    expect(root.querySelector('.rail__brand')?.getAttribute('href')).toBe('/admin');
  });

  it('al cambiar el contexto a Encargado muestra funciones nuevas sin habilitar edición de productos', async () => {
    const { fixture, active, links } = await setup();
    active.set({ ...active(), rol: 'ENCARGADO_SUCURSAL', permisos: [
      'catalogo.consultar', 'inventario.consultar', 'inventario.ajustar',
      'postventa.consultar', 'postventa.gestionar', 'promociones.consultar',
      'abastecimiento.consultar', 'abastecimiento.gestionar',
      'reportes.consultar', 'reportes.ia.consultar',
    ] });
    fixture.detectChanges();
    const urls = links().map(item => item.href);
    expect(urls).toContain('/admin/conciliacion');
    expect(urls).toContain('/admin/inventario');
    expect(urls).toContain('/admin/abastecimiento');
    expect(urls).toContain('/admin/promociones');
    expect(urls).toContain('/admin/reportes-comerciales');
    expect(urls).toContain('/admin/reportes-ia');
    expect(urls).not.toContain('/admin/dashboard-predictivo');
    expect(urls.indexOf('/admin/reportes-comerciales')).toBeLessThan(urls.indexOf('/admin/reportes-ia'));
    expect(urls).not.toContain('/admin/productos');
    expect(links().find(link => link.href === '/admin/promociones')?.text).toContain('Consultar promociones');
    expect(links().find(link => link.href === '/admin/inventario')?.text).toContain('Gestionar inventario');
  });
  it('Administrador encuentra CU20, CU21 y CU22 juntos en la navegación', async () => {
    const { fixture, active, links } = await setup();
    active.set({ ...active(), rol: 'ADMINISTRADOR', permisos: [
      'reportes.consultar', 'reportes.ia.consultar', 'analitica.consultar',
    ] });
    fixture.detectChanges();
    const urls = links().map(item => item.href);
    expect(urls).toContain('/admin/reportes-comerciales');
    expect(urls).toContain('/admin/reportes-ia');
    expect(urls).toContain('/admin/dashboard-predictivo');
    expect(urls.indexOf('/admin/reportes-comerciales')).toBeLessThan(urls.indexOf('/admin/reportes-ia'));
    expect(urls.indexOf('/admin/reportes-ia')).toBeLessThan(urls.indexOf('/admin/dashboard-predictivo'));
  });

  it('no muestra CU21 ni CU22 a un administrador sin los permisos correspondientes', async () => {
    const { fixture, active, links, root } = await setup();
    active.set({ ...active(), rol: 'ADMINISTRADOR', permisos: ['reportes.consultar'] });
    fixture.detectChanges();
    const urls = links().map(item => item.href);
    expect(urls).toContain('/admin/reportes-comerciales');
    expect(urls).not.toContain('/admin/reportes-ia');
    expect(urls).not.toContain('/admin/dashboard-predictivo');
    const disabled = [...root.querySelectorAll<HTMLElement>('.rail__link--disabled')];
    expect(disabled.map(item => item.textContent?.trim())).toEqual([
      'Reportes con IA · CU21 (sin permiso)',
      'Dashboard predictivo · CU22 (sin permiso)',
    ]);
    expect(disabled.every(item => item.getAttribute('aria-disabled') === 'true')).toBe(true);
  });
});
