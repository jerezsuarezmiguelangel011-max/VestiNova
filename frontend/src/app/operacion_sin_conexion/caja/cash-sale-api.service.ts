import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { CompanyService } from '../../organizacion_empresarial/empresa/company.service';

export interface CashVariant {
  variante_id: number; producto_id: number; nombre: string;
  talla: string; color: string; precio_unitario: string;
}
export interface CashSnapshot {
  empresa_id: number; sucursal_id: number; descargado_en: string;
  items: CashVariant[];
}
export interface CashLine {
  variante_id: number; cantidad: number; precio_unitario: string;
}
export interface CashSaleInput {
  id: string; sucursal_id: number; cliente_id: number | null;
  lineas: CashLine[]; efectivo: string;
  origen: 'WEB_OFFLINE'; creada_local_en: string;
  efectivo_cobrado: boolean; entrega_local: boolean;
}
export interface CashSaleResult {
  id: string; codigo: string; estado: 'CONFIRMADA';
  empresa_id: number; sucursal_id: number; cliente_id: number | null;
  lineas: Array<CashLine & { nombre: string; subtotal: string; movimiento_id: string }>;
  total: string; efectivo: string; cambio: string; origen: string; confirmada_en: string;
}

@Injectable({ providedIn: 'root' })
export class CashSaleApi {
  private readonly http = inject(HttpClient);
  private readonly companies = inject(CompanyService);
  private readonly url = '/api/admin/caja';
  catalog(branchId: number) {
    return this.companies.scoped(company => this.http.get<CashSnapshot>(this.url + '/catalogo', {
      params: new HttpParams().set('sucursal_id', branchId).set('limit', 300),
      headers: { 'X-Empresa-Id': String(company.id), 'ngsw-bypass': 'true' },
    }));
  }
  create(payload: CashSaleInput) {
    return this.companies.scoped(company => this.http.post<CashSaleResult>(
      this.url + '/ventas', payload, {
        headers: { 'X-Empresa-Id': String(company.id), 'ngsw-bypass': 'true' },
      },
    ));
  }
  list(branchId?: number) {
    return this.companies.scoped(company => this.http.get<CashSaleResult[]>(
      this.url + '/ventas', {
        params: branchId ? new HttpParams().set('sucursal_id', branchId) : undefined,
        headers: { 'X-Empresa-Id': String(company.id), 'ngsw-bypass': 'true' },
      },
    ));
  }
}
