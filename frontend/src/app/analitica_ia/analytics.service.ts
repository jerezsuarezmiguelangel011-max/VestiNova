import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { CompanyService } from '../organizacion_empresarial/empresa/company.service';

export interface ReportFilters { desde?: string; hasta?: string; sucursal_id?: number; categoria_id?: number; producto_id?: number; }
export interface ReportOptions { profesional_vigente: boolean; ia_configurada: boolean; tipos: { codigo: string; nombre: string }[]; sucursales: Choice[]; categorias: Choice[]; productos: Choice[]; formatos: string[]; }
export interface Choice { id: number; nombre: string; }
export interface DataOrigin { demostracion: boolean; compras_demo: number; compras_operativas: number; }
export interface Report { tipo: string; titulo: string; empresa: Choice; generado_en: string; filtros: ReportFilters; columnas: string[]; filas: Record<string, string | number | boolean>[]; total_filas: number; truncado: boolean; totales: Record<string, string | number>; notas: string[]; sin_datos: boolean; origen_datos?: DataOrigin; }
export interface ReportResult { estado: 'generado' | 'aclaracion' | 'no_admitido'; mensaje?: string; reporte?: Report; }
export interface Prediction { producto_id: number; producto: string; unidades_reales_7d: number; unidades_reales_previas_7d: number; stock_disponible_real: number; precio_real_bob: string; demanda_estimada_7d: number | null; agrupacion_estimada: string | null; }
export interface EvaluationModel {
  version: string; dataset: string; origen: string; muestras: number; entrenamiento: number; evaluacion: number;
  division: string; preprocesamiento: string; features: string[]; semilla?: number; scikit_learn?: string;
  metricas: { mae: number; rmse: number; r2: number; silhouette: number };
  ejemplos_sinteticos: { entrada: number[]; objetivo_sintetico: number; estimacion: number }[];
  limitaciones: string[]; supervisado: {nombre: string; objetivo: string}; no_supervisado: {nombre: string; grupos: number; etiquetas?: string[]};
}
export interface PredictiveDashboard { empresa: Choice; analisis: string; filtros: ReportFilters; estado: string; mensaje: string; filas: Prediction[]; omitidos: { producto: string; motivo: string }[]; modelo: EvaluationModel; origen_datos?: DataOrigin; }

@Injectable({ providedIn: 'root' })
export class AnalyticsService {
  private readonly http = inject(HttpClient);
  private readonly companies = inject(CompanyService);
  private headers(id: number) { return { 'X-Empresa-Id': String(id), 'ngsw-bypass': 'true' }; }
  options() { return this.companies.scoped(company => this.http.get<ReportOptions>('/api/admin/reportes-ia/opciones', { headers: this.headers(company.id) })); }
  generate(consulta: string, filtros: ReportFilters) { return this.companies.scoped(company => this.http.post<ReportResult>('/api/admin/reportes-ia/generar', { consulta, filtros }, { headers: this.headers(company.id) })); }
  export(report: Report, formato: string) { return this.companies.scoped(company => this.http.post('/api/admin/reportes-ia/exportar', { tipo: report.tipo, filtros: report.filtros, formato }, { headers: this.headers(company.id), responseType: 'blob' })); }
  dashboard(filtros: ReportFilters, analisis: string) { return this.companies.scoped(company => this.http.post<PredictiveDashboard>('/api/admin/dashboard-predictivo', { filtros, analisis }, { headers: this.headers(company.id) })); }
}

export function analyticsError(error: unknown): string {
  if (error instanceof HttpErrorResponse) {
    if (typeof error.error?.detail === 'string') return error.error.detail;
    if (error.status === 0) return 'Necesitas conexión con el servidor para consultar información actualizada.';
    if (error.status === 401) return 'Tu sesión ya no está disponible. Vuelve a iniciar sesión.';
    if (error.status === 403) return 'Tu acceso o suscripción no permite esta consulta. Actualiza tus accesos.';
    if (error.status === 422) return 'Revisa las fechas, la solicitud y los filtros seleccionados.';
  }
  return 'No pudimos completar la consulta. Inténtalo de nuevo.';
}

export function formFilters(value: { desde: string; hasta: string; sucursal_id: string; categoria_id: string; producto_id: string }): ReportFilters {
  return { ...(value.desde ? { desde: value.desde } : {}), ...(value.hasta ? { hasta: value.hasta } : {}), ...(value.sucursal_id ? { sucursal_id: Number(value.sucursal_id) } : {}), ...(value.categoria_id ? { categoria_id: Number(value.categoria_id) } : {}), ...(value.producto_id ? { producto_id: Number(value.producto_id) } : {}) };
}
