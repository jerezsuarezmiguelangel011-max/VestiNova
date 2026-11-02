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
  actualizado_en: string;
}

export interface InventoryMovement {
  id: string;
  empresa_id: number;
  sucursal_id: number;
  variante_id: number;
  usuario_id: number;
  tipo: 'ENTRADA' | 'SALIDA';
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

  balances(branchId: number, offset = 0) {
    return this.companies.scoped(company =>
      this.http.get<InventoryPageResult<InventoryBalance>>('/api/admin/inventario/existencias', {
        headers: { 'X-Empresa-Id': String(company.id) },
        params: new HttpParams().set('sucursal_id', branchId).set('limit', 100).set('offset', offset),
      }),
    );
  }

  movements(branchId: number, offset = 0) {
    return this.companies.scoped(company =>
      this.http.get<InventoryPageResult<InventoryMovement>>('/api/admin/inventario/movimientos', {
        headers: { 'X-Empresa-Id': String(company.id) },
        params: new HttpParams().set('sucursal_id', branchId).set('limit', 100).set('offset', offset),
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
