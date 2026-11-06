import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { CompanyService } from '../organizacion_empresarial/empresa/company.service';

export interface InventoryBranch {
  id: number;
  empresa_id: number;
  codigo: string;
  nombre: string;
  activo: boolean;
}

export interface InventoryBalance {
  empresa_id: number;
  sucursal_id: number;
  variante_id: number;
  cantidad: number;
  cantidad_comprometida: number;
  cantidad_disponible: number;
  actualizado_en: string;
  producto_id?: number | null;
  producto_nombre?: string | null;
  categoria_id?: number | null;
  talla?: string | null;
  color?: string | null;
}

export interface InventoryMovement {
  id: string;
  empresa_id: number;
  sucursal_id: number;
  variante_id: number;
  usuario_id: number;
  tipo: 'ENTRADA' | 'SALIDA';
  clase: 'MOVIMIENTO' | 'AJUSTE' | 'REINGRESO';
  origen_tipo?: string | null;
  origen_id?: string | null;
  delta: number;
  saldo_resultante: number;
  motivo: string;
  creado_en: string;
}

export interface InventoryPageResult<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface InventoryFilters {
  producto_id?: number;
  categoria_id?: number;
  variante_id?: number;
  q?: string;
}

export interface InventoryAdjustmentInput {
  id: string;
  sucursal_id: number;
  variante_id: number;
  tipo: 'INCREMENTO' | 'DISMINUCION';
  cantidad: number;
  motivo: string;
}

export interface InventoryReturnInput {
  id: string;
  solicitud_id: string;
  sucursal_id: number;
  variante_id: number;
  cantidad: number;
  motivo: string;
  apta_para_venta: true;
}

export interface InventoryMovementInput {
  id: string;
  sucursal_id: number;
  variante_id: number;
  tipo: 'ENTRADA' | 'SALIDA';
  cantidad: number;
  motivo: string;
}

@Injectable({ providedIn: 'root' })
export class InventoryApiService {
  private readonly http = inject(HttpClient);
  private readonly companies = inject(CompanyService);

  branches() {
    return this.companies.scoped(company =>
      this.http.get<InventoryBranch[]>('/api/admin/sucursales', {
        headers: { 'X-Empresa-Id': String(company.id) },
      }),
    );
  }

  balances(branchId: number, offset = 0, filters: InventoryFilters = {}) {
    let params = new HttpParams().set('sucursal_id', branchId).set('limit', 100).set('offset', offset);
    if (filters.producto_id !== undefined) params = params.set('producto_id', filters.producto_id);
    if (filters.categoria_id !== undefined) params = params.set('categoria_id', filters.categoria_id);
    if (filters.variante_id !== undefined) params = params.set('variante_id', filters.variante_id);
    if (filters.q) params = params.set('q', filters.q);
    return this.companies.scoped(company =>
      this.http.get<InventoryPageResult<InventoryBalance>>('/api/admin/inventario/existencias', {
        headers: { 'X-Empresa-Id': String(company.id) },
        params,
      }),
    );
  }

  movements(branchId: number, offset = 0, variantId: number | null = null) {
    let params = new HttpParams().set('sucursal_id', branchId).set('limit', 100).set('offset', offset);
    if (variantId !== null) params = params.set('variante_id', variantId);
    return this.companies.scoped(company =>
      this.http.get<InventoryPageResult<InventoryMovement>>('/api/admin/inventario/movimientos', {
        headers: { 'X-Empresa-Id': String(company.id) },
        params,
      }),
    );
  }

  adjust(input: InventoryAdjustmentInput) {
    return this.companies.scoped(company =>
      this.http.post<InventoryMovement>('/api/admin/inventario/ajustes', input, {
        headers: { 'X-Empresa-Id': String(company.id) },
      }),
    );
  }

  reenter(input: InventoryReturnInput) {
    return this.companies.scoped(company =>
      this.http.post<InventoryMovement>('/api/admin/inventario/reingresos', input, {
        headers: { 'X-Empresa-Id': String(company.id) },
      }),
    );
  }

  register(input: InventoryMovementInput) {
    return this.companies.scoped(company =>
      this.http.post<InventoryMovement>('/api/admin/inventario/movimientos', input, {
        headers: { 'X-Empresa-Id': String(company.id) },
      }),
    );
  }
}
