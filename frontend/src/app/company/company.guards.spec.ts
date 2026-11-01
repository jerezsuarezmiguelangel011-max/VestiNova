import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRouteSnapshot, CanActivateFn, Router, RouterStateSnapshot, UrlTree, provideRouter } from '@angular/router';
import { Observable, firstValueFrom, of } from 'rxjs';
import { AuthService } from '../auth/auth.service';
import { companyAdminGuard, companyGuard } from './company.guards';
import { COMPANY_KEY } from './company.service';

describe('Rutas empresariales y permisos de escritura', () => {
  let http: HttpTestingController;
  beforeEach(() => {
    sessionStorage.removeItem(COMPANY_KEY);
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([]), { provide: AuthService, useValue: { ensureSession: () => of({ id: 10 }) } }] });
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => { http.verify(); sessionStorage.removeItem(COMPANY_KEY); });
  function run(guard: CanActivateFn) {
    return firstValueFrom(TestBed.runInInjectionContext(() => guard({} as ActivatedRouteSnapshot, {} as RouterStateSnapshot)) as Observable<boolean | UrlTree>);
  }

  it('exige elegir empresa cuando el servidor devuelve varias y ninguna está validada', async () => {
    const result = run(companyGuard);
    http.expectOne('/api/empresas').flush([
      { id: 1, nombre: 'Empresa A', slug: 'a', activo: true, rol: 'ADMINISTRADOR' },
      { id: 2, nombre: 'Empresa B', slug: 'b', activo: true, rol: 'ADMINISTRADOR' },
    ]);
    expect(TestBed.inject(Router).serializeUrl(await result as UrlTree)).toBe('/admin/empresa');
  });

  it('permite consultar con la única pertenencia autorizada', async () => {
    const result = run(companyGuard);
    http.expectOne('/api/empresas').flush([{ id: 1, nombre: 'Empresa A', slug: 'a', activo: true, rol: 'OPERADOR' }]);
    expect(await result).toBe(true);
  });

  it('no permite abrir creación o edición con rol de operador', async () => {
    const result = run(companyAdminGuard);
    http.expectOne('/api/empresas').flush([{ id: 1, nombre: 'Empresa A', slug: 'a', activo: true, rol: 'OPERADOR' }]);
    expect(TestBed.inject(Router).serializeUrl(await result as UrlTree)).toBe('/admin/productos?motivo=permiso');
  });

  it('permite escritura solo tras validar una pertenencia administrativa', async () => {
    const result = run(companyAdminGuard);
    http.expectOne('/api/empresas').flush([{ id: 1, nombre: 'Empresa A', slug: 'a', activo: true, rol: 'ADMINISTRADOR' }]);
    expect(await result).toBe(true);
  });

  it('conserva pantalla de selección para reintentar ante caída de API', async () => {
    const result = run(companyGuard);
    http.expectOne('/api/empresas').flush({}, { status: 503, statusText: 'Unavailable' });
    expect(TestBed.inject(Router).serializeUrl(await result as UrlTree)).toBe('/admin/empresa');
  });
});
