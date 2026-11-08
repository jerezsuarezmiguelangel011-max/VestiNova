import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { CompanyService } from '../../organizacion_empresarial/empresa/company.service';
import type { ReservationResult, ReservationRequest } from './reservation-online-api.service';

export interface StaffReservationInput extends ReservationRequest { cliente_id: number; }
export interface StaffBranch { id: number; nombre: string; }
export interface StaffVariant { id: number; producto_slug: string; talla: string; color: string; }

@Injectable({ providedIn: 'root' })
export class ReservationStaffApiService {
  private readonly http = inject(HttpClient);
  private readonly company = inject(CompanyService);
  private readonly endpoint = '/api/admin/reservas';

  policy(): Observable<{ vigencia_horas: number; requiere_conexion: true }> {
    return this.company.scoped(company => this.http.get<{ vigencia_horas: number; requiere_conexion: true }>(
      `/api/tiendas/${encodeURIComponent(company.slug)}/reservas/politica`,
      { headers: { 'ngsw-bypass': 'true' } },
    ));
  }

  list(): Observable<ReservationResult[]> {
    return this.company.scoped(company => this.http.get<ReservationResult[]>(this.endpoint, {
      headers: { 'X-Empresa-Id': String(company.id), 'ngsw-bypass': 'true' },
    }));
  }

  create(input: StaffReservationInput): Observable<ReservationResult> {
    return this.company.scoped(company => this.http.post<ReservationResult>(this.endpoint, input, {
      headers: { 'X-Empresa-Id': String(company.id), 'ngsw-bypass': 'true' },
    }));
  }

  cancel(id: string): Observable<ReservationResult> {
    return this.company.scoped(company => this.http.post<ReservationResult>(
      `${this.endpoint}/${encodeURIComponent(id)}/cancelar`, {}, {
        headers: { 'X-Empresa-Id': String(company.id), 'ngsw-bypass': 'true' },
      }));
  }

  branches(): Observable<StaffBranch[]> {
    return this.company.scoped(company => this.http.get<StaffBranch[]>('/api/admin/sucursales', {
      headers: { 'X-Empresa-Id': String(company.id), 'ngsw-bypass': 'true' },
    }));
  }

  variants(): Observable<{ items: StaffVariant[]; total: number }> {
    return this.company.scoped(company => this.http.get<{ items: StaffVariant[]; total: number }>(
      '/api/catalogo/variantes', {
        params: { tienda: company.slug, limit: '100', offset: '0' },
        headers: { 'ngsw-bypass': 'true' },
      },
    ));
  }
}
