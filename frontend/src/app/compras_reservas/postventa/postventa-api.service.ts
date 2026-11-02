import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { CompanyService } from '../../organizacion_empresarial/empresa/company.service';
import { type AfterSaleRequest, type AfterSaleStatus } from '../compras/customer-purchases.service';

export interface StaffAfterSaleRequest extends AfterSaleRequest {
  cliente: { nombre: string; correo: string } | null;
  sucursal_id: number | string;
}

export interface StaffAfterSalePage {
  items: StaffAfterSaleRequest[];
  total: number;
  limit: number;
  offset: number;
}

@Injectable({ providedIn: 'root' })
export class PostventaApiService {
  private readonly http = inject(HttpClient);
  private readonly companies = inject(CompanyService);
  private readonly endpoint = '/api/admin/postventa/solicitudes';

  list(status: AfterSaleStatus | null, offset = 0): Observable<StaffAfterSalePage> {
    let params = new HttpParams().set('limit', 100).set('offset', offset);
    if (status) params = params.set('estado', status);
    return this.companies.scoped(company => this.http.get<StaffAfterSalePage>(this.endpoint, {
      params, headers: { 'X-Empresa-Id': String(company.id), 'ngsw-bypass': 'true' },
    }));
  }

  decide(id: string, estado: 'APROBADA' | 'RECHAZADA', respuesta: string): Observable<AfterSaleRequest> {
    return this.companies.scoped(company => this.http.patch<AfterSaleRequest>(`${this.endpoint}/${encodeURIComponent(id)}/decision`, {
      estado, respuesta: respuesta.trim() || null,
    }, { headers: { 'X-Empresa-Id': String(company.id), 'ngsw-bypass': 'true' } }));
  }

  complete(id: string): Observable<AfterSaleRequest> {
    return this.companies.scoped(company => this.http.post<AfterSaleRequest>(`${this.endpoint}/${encodeURIComponent(id)}/completar`, {}, {
      headers: { 'X-Empresa-Id': String(company.id), 'ngsw-bypass': 'true' },
    }));
  }
}
