import { inject } from '@angular/core';
import { CanActivateFn, CanDeactivateFn, Router } from '@angular/router';
import { catchError, map, of, switchMap } from 'rxjs';
import { AuthService } from '../auth/auth.service';
import { CompanyService } from '../company/company.service';

export const staffPermissionGuard: CanActivateFn = route => {
  const auth = inject(AuthService);
  const companies = inject(CompanyService);
  const router = inject(Router);
  return auth.ensureSession().pipe(switchMap(user => {
    if (!user) return of(router.createUrlTree(['/admin/login']));
    return companies.ensureForUser(user.id).pipe(switchMap(() => {
      if (!companies.active()) return of(router.createUrlTree(['/admin/empresa']));
      return companies.refreshAccess().pipe(map(() => companies.hasPermission(route.data['permission']) ? true : router.createUrlTree(['/admin/acceso'], { queryParams: { motivo: 'permiso' } })));
    }));
  }), catchError(() => of(router.createUrlTree(['/admin/empresa'], { queryParams: { motivo: 'acceso' } }))));
};

export const staffLeaveGuard: CanDeactivateFn<{ canLeave(): boolean }> = component => component.canLeave();
