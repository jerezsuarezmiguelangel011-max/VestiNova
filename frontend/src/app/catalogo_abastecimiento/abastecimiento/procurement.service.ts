import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { CompanyService } from '../../organizacion_empresarial/empresa/company.service';

export interface Supplier {
  id: number; empresa_id: number; codigo: string; nombre: string;
  contacto: string; correo: string; telefono: string; activo: boolean;
}
export interface SupplierInput { codigo: string; nombre: string; contacto: string; correo: string; telefono: string; }
export interface ProcurementVariant { id: number; producto_id: number; producto: string; talla: string; color: string; precio: string; }
export interface OrderLineInput { variante_id: number; cantidad: number; costo_unitario: string; }
export interface OrderInput { proveedor_id: number; sucursal_id: number; observaciones: string; lineas: OrderLineInput[]; }
export interface OrderLine { id: number; producto_id: number; producto: string; talla: string; color: string; cantidad_solicitada: number; cantidad_recibida: number; costo_unitario: string; }
export interface ProcurementOrder {
  id: number; empresa_id: number; sucursal_id: number; sucursal: string; proveedor_id: number;
  proveedor: string; usuario_id: number; estado: 'PENDIENTE' | 'PARCIAL' | 'RECIBIDA' | 'CANCELADA';
  observaciones: string; creado_en: string; actualizado_en: string; total: string; lineas: OrderLine[];
}
export interface OrderList { items: ProcurementOrder[]; total: number; limit: number; offset: number; }

@Injectable({ providedIn: 'root' })
export class ProcurementService {
  private readonly http = inject(HttpClient);
  private readonly companies = inject(CompanyService);
  private readonly endpoint = '/api/admin/abastecimiento';

  suppliers() {
    return this.companies.scoped(company => this.http.get<Supplier[]>(`${this.endpoint}/proveedores`, {
      params: new HttpParams().set('estado', 'todos'), headers: { 'X-Empresa-Id': String(company.id) },
    }));
  }
  variants() {
    return this.companies.scoped(company => this.http.get<ProcurementVariant[]>(`${this.endpoint}/variantes`, {
      headers: { 'X-Empresa-Id': String(company.id) },
    }));
  }
  orders() {
    return this.companies.scoped(company => this.http.get<OrderList>(`${this.endpoint}/ordenes`, {
      params: new HttpParams().set('estado', 'todas').set('limit', 100).set('offset', 0),
      headers: { 'X-Empresa-Id': String(company.id) },
    }));
  }
  createSupplier(input: SupplierInput) {
    return this.companies.scoped(company => this.http.post<Supplier>(`${this.endpoint}/proveedores`, input, {
      headers: { 'X-Empresa-Id': String(company.id) },
    }));
  }
  updateSupplier(id: number, changes: Partial<SupplierInput> & { activo?: boolean }) {
    return this.companies.scoped(company => this.http.patch<Supplier>(`${this.endpoint}/proveedores/${id}`, changes, {
      headers: { 'X-Empresa-Id': String(company.id) },
    }));
  }
  createOrder(input: OrderInput) {
    return this.companies.scoped(company => this.http.post<ProcurementOrder>(`${this.endpoint}/ordenes`, input, {
      headers: { 'X-Empresa-Id': String(company.id) },
    }));
  }
  receive(orderId: number, input: { id: string; lineas: { linea_id: number; cantidad: number }[] }) {
    return this.companies.scoped(company => this.http.post<ProcurementOrder>(`${this.endpoint}/ordenes/${orderId}/recepciones`, input, {
      headers: { 'X-Empresa-Id': String(company.id) },
    }));
  }
  cancel(orderId: number) {
    return this.companies.scoped(company => this.http.post<ProcurementOrder>(`${this.endpoint}/ordenes/${orderId}/cancelar`, {}, {
      headers: { 'X-Empresa-Id': String(company.id) },
    }));
  }
}
