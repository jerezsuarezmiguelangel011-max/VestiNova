import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';
import { CustomerAuthService } from './customer-auth.service';

export const customerGuard: CanActivateFn = route => {
  const auth = inject(CustomerAuthService);
  const router = inject(Router);
  const slug = route.paramMap.get('tienda') ?? '';
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)) return router.createUrlTree(['/no-encontrado']);
  return auth.ensureSession(slug).pipe(
    map(customer => customer ? true : router.createUrlTree(['/tienda', slug, 'acceso'], { queryParams: { motivo: 'sesion' } })),
    catchError(() => of(router.createUrlTree(['/tienda', slug, 'acceso'], { queryParams: { motivo: 'conexion' } }))),
  );
};
