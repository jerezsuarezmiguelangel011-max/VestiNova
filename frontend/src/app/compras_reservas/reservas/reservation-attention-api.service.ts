import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { CompanyService } from '../../organizacion_empresarial/empresa/company.service';
import type { ReservationResult } from './reservation-online-api.service';

export interface AttentionEvent {
  estado: string;
  actor: string;
  en: string;
  comprobacion?: string;
  motivo?: string;
  movimientos?: string[];
}
export type AttentionState = ReservationResult['estado'];
export type AttentionFilter = AttentionState | 'TODAS';
export interface AttentionResult extends ReservationResult {
  cliente_nombre?: string | null;
  sucursal_nombre?: string | null;
  lineas: Array<ReservationResult['lineas'][number] & {
    producto_nombre?: string; talla?: string; color?: string;
  }>;
  eventos?: AttentionEvent[];
}

@Injectable({ providedIn: 'root' })
export class ReservationAttentionApi {
  private readonly http = inject(HttpClient);
  private readonly companies = inject(CompanyService);
  private readonly base = '/api/admin/atencion-reservas';
  list(filters: { sucursal_id?: number; codigo?: string; cliente_id?: number; estado?: AttentionFilter } = {}) {
    let params = new HttpParams();
    if (filters.sucursal_id) params = params.set('sucursal_id', filters.sucursal_id);
    if (filters.codigo) params = params.set('codigo', filters.codigo);
    if (filters.cliente_id) params = params.set('cliente_id', filters.cliente_id);
    params = params.set('estado', filters.estado ?? 'CONFIRMADA');
    return this.companies.scoped(company => this.http.get<AttentionResult[]>(this.base, {
      params, headers: { 'X-Empresa-Id': String(company.id), 'ngsw-bypass': 'true' },
    }));
  }
  detail(id: string) {
    return this.companies.scoped(company => this.http.get<AttentionResult>(
      `${this.base}/${encodeURIComponent(id)}`,
      { headers: { 'X-Empresa-Id': String(company.id), 'ngsw-bypass': 'true' } },
    ));
  }
  deliver(id: string, comprobacion: string) {
    return this.companies.scoped(company => this.http.post<AttentionResult>(
      `${this.base}/${encodeURIComponent(id)}/entregar`,
      { identidad_verificada: true, comprobacion },
      { headers: { 'X-Empresa-Id': String(company.id), 'ngsw-bypass': 'true' } },
    ));
  }
  cancel(id: string, motivo: string) {
    return this.companies.scoped(company => this.http.post<AttentionResult>(
      `${this.base}/${encodeURIComponent(id)}/cancelar`, { motivo },
      { headers: { 'X-Empresa-Id': String(company.id), 'ngsw-bypass': 'true' } },
    ));
  }
}
