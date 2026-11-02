import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { CompanyService } from '../../organizacion_empresarial/empresa/company.service';

export interface Promotion {
  id: number;
  empresa_id: number;
  nombre: string;
  tipo: 'PORCENTAJE' | 'PRECIO_FIJO';
  valor: string;
  inicio: string;
  fin: string;
  activo: boolean;
  estado: 'ACTIVA' | 'PROGRAMADA' | 'FINALIZADA' | 'INACTIVA';
  producto_ids: number[];
  creado_en: string;
  actualizado_en: string;
}

export interface PromotionInput {
  nombre: string;
  tipo: Promotion['tipo'];
  valor: string;
  inicio: string;
  fin: string;
  producto_ids: number[];
  activo?: boolean;
}

@Injectable({ providedIn: 'root' })
export class PromotionService {
  private readonly http = inject(HttpClient);
  private readonly companies = inject(CompanyService);
  private readonly endpoint = '/api/admin/promociones';

  list(): Observable<Promotion[]> {
    return this.companies.scoped(company => this.http.get<Promotion[]>(this.endpoint, {
      params: new HttpParams().set('estado', 'todas'),
      headers: { 'X-Empresa-Id': String(company.id) },
    }));
  }

  create(input: PromotionInput) {
    return this.companies.scoped(company => this.http.post<Promotion>(this.endpoint, input, {
      headers: { 'X-Empresa-Id': String(company.id) },
    }));
  }

  update(id: number, changes: Partial<PromotionInput>) {
    return this.companies.scoped(company => this.http.patch<Promotion>(`${this.endpoint}/${id}`, changes, {
      headers: { 'X-Empresa-Id': String(company.id) },
    }));
  }
}
