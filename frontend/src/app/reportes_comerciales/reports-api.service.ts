import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { CompanyService } from '../organizacion_empresarial/empresa/company.service';

export type ReportType = 'resumen' | 'ventas' | 'reservas' | 'inventario';

export interface ReportRow {
  sucursal_id: number;
  sucursal: string;
  ventas_confirmadas: number;
  ingresos_confirmados: string;
  ventas_digitales: number;
  ventas_efectivo: number;
  reservas_confirmadas: number;
  reservas_atendidas: number;
  reservas_canceladas: number;
  reservas_vencidas: number;
  stock_fisico_actual: number;
  stock_comprometido_actual: number;
  stock_disponible_actual: number;
}

export interface CommercialReport {
  tipo: ReportType;
  desde: string;
  hasta: string;
  zona_horaria: string;
  nota: string;
  por_sucursal: ReportRow[];
  totales: Omit<ReportRow, 'sucursal_id' | 'sucursal'>;
}

@Injectable({ providedIn: 'root' })
export class ReportsApi {
  private readonly http = inject(HttpClient);
  private readonly companies = inject(CompanyService);

  load(filters: { tipo: ReportType; desde: string; hasta: string; sucursal_id?: number | null }) {
    let params = new HttpParams().set('tipo', filters.tipo)
      .set('desde', filters.desde).set('hasta', filters.hasta);
    if (filters.sucursal_id) params = params.set('sucursal_id', filters.sucursal_id);
    return this.companies.scoped(company => this.http.get<CommercialReport>(
      '/api/admin/reportes-comerciales', {
        params,
        headers: { 'X-Empresa-Id': String(company.id), 'ngsw-bypass': 'true' },
      }));
  }
}
