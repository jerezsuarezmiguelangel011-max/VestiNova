import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';

export interface PlatformCompany {
  id: number; nombre: string; slug: string; nit: string | null; correo_contacto: string | null;
  telefono_contacto: string | null; activo: boolean; creado_en: string; administradores_activos: number;
}
export interface AdministratorOption { id: number; nombre: string; correo: string; }
export interface CompanyCreateInput {
  nombre: string; slug: string; administrador_id: number; nit: string | null;
  correo_contacto: string | null; telefono_contacto: string | null;
}
export type CompanyUpdateInput = Partial<Pick<CompanyCreateInput, 'nombre' | 'nit' | 'correo_contacto' | 'telefono_contacto'>>;

@Injectable({ providedIn: 'root' })
export class PlatformCompanyService {
  private readonly http = inject(HttpClient);
  private readonly endpoint = '/api/plataforma';

  companies(q = '') {
    let params = new HttpParams().set('estado', 'todas');
    if (q.trim()) params = params.set('q', q.trim());
    return this.http.get<PlatformCompany[]>(`${this.endpoint}/empresas`, { params });
  }
  administrators() { return this.http.get<AdministratorOption[]>(`${this.endpoint}/administradores`); }
  create(input: CompanyCreateInput) { return this.http.post<PlatformCompany>(`${this.endpoint}/empresas`, input); }
  update(id: number, input: CompanyUpdateInput) { return this.http.patch<PlatformCompany>(`${this.endpoint}/empresas/${id}`, input); }
  setActive(id: number, activo: boolean) { return this.http.patch<PlatformCompany>(`${this.endpoint}/empresas/${id}/estado`, { activo }); }
}
