import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';
import { AuthService } from './auth.service';

export const adminGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  return auth.ensureSession().pipe(
    map(user => user ? true : router.createUrlTree(['/admin/login'])),
    catchError(() => of(router.createUrlTree(['/admin/login'], { queryParams: { motivo: 'conexion' } }))),
  );
};

export const guestGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  return auth.ensureSession().pipe(
    map(user => user ? router.createUrlTree([user.es_superadministrador ? '/admin/plataforma' : '/admin/productos']) : true),
    catchError(() => of(true)),
  );
};

export const platformGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const router = inject(Router);
  return auth.ensureSession().pipe(
    map(user => user?.es_superadministrador === true ? true : router.createUrlTree([user ? '/admin/empresa' : '/admin/login'])),
    catchError(() => of(router.createUrlTree(['/admin/login'], { queryParams: { motivo: 'conexion' } }))),
  );
};
