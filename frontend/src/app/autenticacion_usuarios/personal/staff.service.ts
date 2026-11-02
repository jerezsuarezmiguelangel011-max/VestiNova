import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { CompanyService } from '../../organizacion_empresarial/empresa/company.service';

export interface StaffUser {
  id: number; empresa_id: number; nombre: string; correo: string; activo: boolean;
  rol_id: number | null; rol_nombre: string; rol_sistema: string | null; sucursal_ids: number[];
  rol_activo?: boolean; acceso_habilitado?: boolean;
}
export interface StaffInput { nombre: string; correo: string; password: string; activo: boolean; rol_id: number; sucursal_ids: number[]; }
export type StaffChanges = Partial<Pick<StaffInput, 'nombre' | 'activo' | 'rol_id' | 'sucursal_ids'>>;
export interface StaffQuery { q: string; estado: string; rol_id?: number; limit: number; offset: number; }
export interface StaffList { items: StaffUser[]; total: number; limit: number; offset: number; }
export interface CompanyRole {
  id: number; empresa_id: number; nombre: string; descripcion: string; codigo_sistema: string | null;
  protegido: boolean; activo: boolean; permisos: string[];
}
export interface RoleInput { nombre: string; descripcion: string; permisos: string[]; }
export interface Permission { codigo: string; nombre: string; descripcion: string; requiere: string[]; }
export interface StaffBranch { id: number; empresa_id: number; codigo: string; nombre: string; activo: boolean; }

@Injectable({ providedIn: 'root' })
export class StaffService {
  private readonly http = inject(HttpClient);
  private readonly companies = inject(CompanyService);
  private request<T>(method: string, path: string, body?: unknown, params?: HttpParams): Observable<T> {
    return this.companies.scoped(company => this.http.request<T>(method, `/api/admin/${path}`, { body, params, headers: { 'X-Empresa-Id': String(company.id) } }));
  }
  users(query: StaffQuery): Observable<StaffList> {
    let params = new HttpParams().set('q', query.q).set('estado', query.estado).set('limit', query.limit).set('offset', query.offset);
    if (query.rol_id) params = params.set('rol_id', query.rol_id);
    return this.request('GET', 'usuarios', undefined, params);
  }
  user(id: number): Observable<StaffUser> { return this.request('GET', `usuarios/${id}`); }
  createUser(input: StaffInput): Observable<StaffUser> { return this.request('POST', 'usuarios', input); }
  updateUser(id: number, input: StaffChanges): Observable<StaffUser> { return this.request('PATCH', `usuarios/${id}`, input); }
  roles(): Observable<CompanyRole[]> { return this.request('GET', 'roles'); }
  permissions(): Observable<Permission[]> { return this.request('GET', 'permisos'); }
  branches(): Observable<StaffBranch[]> { return this.request('GET', 'sucursales'); }
  createRole(input: RoleInput): Observable<CompanyRole> { return this.request('POST', 'roles', input); }
  updateRole(id: number, input: Partial<RoleInput> & { activo?: boolean }): Observable<CompanyRole> { return this.request('PATCH', `roles/${id}`, input); }
}

export function staffError(error: unknown): string {
  if (!(error instanceof HttpErrorResponse)) return 'No pudimos completar la operación. Intenta nuevamente.';
  if (error.status === 0) return 'No hay conexión con el servidor. Revisa la conexión e intenta nuevamente.';
  if (error.status === 401) return 'La sesión terminó. Vuelve a iniciar sesión.';
  if (error.status === 403) return 'Tus permisos cambiaron o no autorizan esta operación. Actualiza tus accesos.';
  if (error.status === 404) return 'El registro no está disponible en esta empresa.';
  if (error.status === 409) {
    const detail = String(error.error?.detail ?? '');
    if (/último|ultimo|administrador activo/i.test(detail)) return 'La empresa debe conservar al menos un administrador activo. Asigna otro antes de realizar este cambio.';
    if (/proteg|sistema/i.test(detail)) return 'Los roles del sistema están protegidos y no se pueden modificar.';
    return 'Ya existe un registro con esos datos o el cambio entra en conflicto. Revisa el nombre o correo y vuelve a intentarlo.';
  }
  if (error.status === 422) return 'Revisa los campos indicados antes de guardar.';
  return 'No pudimos completar la operación. Intenta nuevamente.';
}

export function validationFields(error: unknown): Record<string, string> {
  const fields: Record<string, string> = {};
  if (!(error instanceof HttpErrorResponse) || error.status !== 422 || !Array.isArray(error.error?.detail)) return fields;
  for (const issue of error.error.detail) {
    const field = issue.loc?.[1];
    if (typeof field === 'string') fields[field] = ({ nombre: 'Escribe un nombre válido.', correo: 'Escribe un correo válido.', password: 'La contraseña no cumple la política indicada.', rol_id: 'Selecciona un rol activo de esta empresa.', sucursal_ids: 'Selecciona sucursales autorizadas de esta empresa.', permisos: 'Revisa los permisos y sus dependencias.', descripcion: 'Revisa la longitud de la descripción.' } as Record<string, string>)[field] ?? 'Revisa este campo.';
  }
  return fields;
}
