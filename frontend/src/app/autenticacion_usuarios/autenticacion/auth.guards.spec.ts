import { TestBed } from '@angular/core/testing';
import { ActivatedRouteSnapshot, CanActivateFn, Router, RouterStateSnapshot, UrlTree, provideRouter } from '@angular/router';
import { Observable, firstValueFrom, of, throwError } from 'rxjs';
import { AuthService } from './auth.service';
import { adminGuard, guestGuard } from './auth.guards';

describe('Rutas privadas del MVP', () => {
  function setup(response: Observable<unknown>) {
    TestBed.configureTestingModule({ providers: [provideRouter([]), { provide: AuthService, useValue: { ensureSession: () => response } }] });
  }
  function run(guard: CanActivateFn) {
    return firstValueFrom(TestBed.runInInjectionContext(() => guard({} as ActivatedRouteSnapshot, {} as RouterStateSnapshot)) as Observable<boolean | UrlTree>);
  }
  it('permite el acceso cuando el servidor restauró la cuenta', async () => {
    setup(of({ id: 1 }));
    expect(await run(adminGuard)).toBe(true);
  });
  it('redirige al login sin una sesión validada', async () => {
    setup(of(null));
    const result = await run(adminGuard);
    expect(TestBed.inject(Router).serializeUrl(result as UrlTree)).toBe('/admin/login');
  });
  it('distingue la API caída del rechazo de credenciales', async () => {
    setup(throwError(() => new Error('API no disponible')));
    const result = await run(adminGuard);
    expect(TestBed.inject(Router).serializeUrl(result as UrlTree)).toBe('/admin/login?motivo=conexion');
  });
  it('envía al administrador autenticado a productos desde el login', async () => {
    setup(of({ id: 1 }));
    const result = await run(guestGuard);
    expect(TestBed.inject(Router).serializeUrl(result as UrlTree)).toBe('/admin/productos');
  });
});
