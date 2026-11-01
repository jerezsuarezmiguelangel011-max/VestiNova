import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of, switchMap } from 'rxjs';
import { AuthService } from '../auth/auth.service';
import { CompanyService } from './company.service';

export const companyGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const companies = inject(CompanyService);
  const router = inject(Router);
  return auth.ensureSession().pipe(
    switchMap(user => user ? companies.ensureForUser(user.id).pipe(map(() => companies.active() ? true : router.createUrlTree(['/admin/empresa']))) : of(router.createUrlTree(['/admin/login']))),
    catchError(() => of(router.createUrlTree(['/admin/empresa']))),
  );
};

export const companyAdminGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const companies = inject(CompanyService);
  const router = inject(Router);
  return auth.ensureSession().pipe(
    switchMap(user => user ? companies.ensureForUser(user.id).pipe(map(() => {
      if (!companies.active()) return router.createUrlTree(['/admin/empresa']);
      return companies.canManage() ? true : router.createUrlTree([companies.canViewProducts() ? '/admin/productos' : '/admin/acceso'], { queryParams: { motivo: 'permiso' } });
    })) : of(router.createUrlTree(['/admin/login']))),
    catchError(() => of(router.createUrlTree(['/admin/empresa']))),
  );
};

export const productsGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const companies = inject(CompanyService);
  const router = inject(Router);
  return auth.ensureSession().pipe(
    switchMap(user => user ? companies.ensureForUser(user.id).pipe(map(() => {
      if (!companies.active()) return router.createUrlTree(['/admin/empresa']);
      return companies.canViewProducts() ? true : router.createUrlTree(['/admin/acceso']);
    })) : of(router.createUrlTree(['/admin/login']))),
    catchError(() => of(router.createUrlTree(['/admin/empresa']))),
  );
};
