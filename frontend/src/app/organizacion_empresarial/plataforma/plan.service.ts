import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { CompanyService } from '../empresa/company.service';

export interface SaaSPlan {
  id: number; codigo: string; nombre: string; descripcion: string; precio_mensual: string | null;
  max_sucursales: number; max_productos: number | null; max_usuarios: number | null;
  prestaciones: string[]; activo: boolean;
}
export interface SaaSPlanInput {
  codigo: string; nombre: string; descripcion: string; precio_mensual: string | null;
  max_sucursales: number; max_productos: number | null; max_usuarios: number | null;
  prestaciones: string[]; activo: boolean;
}
export interface SubscriptionView {
  empresa_id: number; empresa_nombre: string; empresa_slug: string; empresa_activa: boolean;
  estado: 'ACTIVA' | 'SUSPENDIDA' | 'VENCIDA' | 'CANCELADA' | 'PROGRAMADA'; inicia_en: string; renueva_en: string | null; plan: SaaSPlan;
}
export interface SubscriptionInput { plan_id: number; estado: Exclude<SubscriptionView['estado'], 'PROGRAMADA'>; inicia_en: string; renueva_en: string | null; }
export interface MyPlan {
  empresa_id: number; empresa_nombre: string; estado: SubscriptionView['estado']; plan: SaaSPlan; inicia_en: string; renueva_en: string | null;
}

@Injectable({ providedIn: 'root' })
export class PlatformPlanService {
  private readonly http = inject(HttpClient);
  private readonly companies = inject(CompanyService);
  private readonly platform = '/api/plataforma';

  plans() { return this.http.get<SaaSPlan[]>(`${this.platform}/planes`); }
  subscriptions(q = '') {
    let params = new HttpParams(); if (q.trim()) params = params.set('q', q.trim());
    return this.http.get<SubscriptionView[]>(`${this.platform}/suscripciones`, { params });
  }
  createPlan(input: SaaSPlanInput) { return this.http.post<SaaSPlan>(`${this.platform}/planes`, input); }
  updatePlan(id: number, input: Partial<SaaSPlanInput>) { return this.http.patch<SaaSPlan>(`${this.platform}/planes/${id}`, input); }
  assign(companyId: number, input: SubscriptionInput) { return this.http.put<SubscriptionView>(`${this.platform}/empresas/${companyId}/suscripcion`, input); }
  myPlan() {
    return this.companies.scoped(company => this.http.get<MyPlan>('/api/admin/plan', { headers: { 'X-Empresa-Id': String(company.id) } }));
  }
}
