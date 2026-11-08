import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { CompanyService } from '../../organizacion_empresarial/empresa/company.service';

export interface SyncConflict {
  id: string;
  operacion_id: string;
  tipo: 'VENTA_CONTADO' | 'RESERVA';
  estado: 'CONFLICTO' | 'RESUELTO';
  motivo: string;
  sucursal_id: number;
  creada_en: string;
  decision: string | null;
  observacion: string | null;
  responsable_id: number | null;
  resuelta_en: string | null;
}
export interface SyncConflictDetail extends SyncConflict {
  datos_originales: Record<string, unknown>;
}
export interface ResolveConflictInput {
  decision: 'DEVOLUCION_DOCUMENTADA' | 'ENTREGA_ALTERNATIVA_DOCUMENTADA' | 'ACUERDO_DOCUMENTADO';
  observacion: string; referencia_constancia: string;
}

@Injectable({ providedIn: 'root' })
export class ReconciliationApi {
  private readonly http = inject(HttpClient);
  private readonly companies = inject(CompanyService);
  private readonly base = '/api/admin/conciliacion';

  list(branchId?: number, state?: 'CONFLICTO' | 'RESUELTO') {
    let params = new HttpParams();
    if (branchId) params = params.set('sucursal_id', branchId);
    if (state) params = params.set('estado', state);
    return this.companies.scoped(company => this.http.get<SyncConflict[]>(this.base, {
      params, headers: { 'X-Empresa-Id': String(company.id), 'ngsw-bypass': 'true' },
    }));
  }
  detail(id: string) {
    return this.companies.scoped(company => this.http.get<SyncConflictDetail>(
      `${this.base}/${encodeURIComponent(id)}`,
      { headers: { 'X-Empresa-Id': String(company.id), 'ngsw-bypass': 'true' } },
    ));
  }
  resolve(id: string, input: ResolveConflictInput) {
    return this.companies.scoped(company => this.http.post<SyncConflict>(
      `${this.base}/${encodeURIComponent(id)}/resolver`, input,
      { headers: { 'X-Empresa-Id': String(company.id), 'ngsw-bypass': 'true' } },
    ));
  }
}
