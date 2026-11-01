import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';
import { AuthService } from './auth.service';
import { CompanyService } from '../company/company.service';

export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  const companies = inject(CompanyService);
  const path = request.url.split('?')[0];
  const companyApi = path.startsWith('/api/admin/') || path.startsWith('/api/movil/') || path === '/api/auth/contexto';
  const privateApi = companyApi || path === '/api/empresas' || path.startsWith('/api/plataforma/') || ['/api/auth/me', '/api/auth/logout'].includes(path);
  const token = auth.token();
  const selected = companies.active();
  const authorized = privateApi && token
    ? request.clone({ setHeaders: { Authorization: `Bearer ${token}`, ...(companyApi && selected ? { 'X-Empresa-Id': String(selected.id) } : {}) } })
    : request;
  return next(authorized).pipe(catchError((error: unknown) => {
    if (error instanceof HttpErrorResponse && error.status === 401 && privateApi && token !== null && token === auth.token()) {
      auth.invalidate();
      void router.navigate(['/admin/login'], { queryParams: { motivo: 'sesion' } });
    }
    return throwError(() => error);
  }));
};
