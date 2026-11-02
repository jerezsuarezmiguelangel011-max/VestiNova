import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { CompanyService } from '../empresa/company.service';

export type AuditEntity = 'usuario' | 'rol' | 'sucursal' | 'categoria' | 'producto' | 'variante';

export interface AuditEvent {
  id: number;
  empresa_id: number;
  actor_id: number;
  actor_nombre: string;
  actor_correo: string;
  accion: string;
  entidad: AuditEntity;
  entidad_id: string;
  detalles: Record<string, unknown>;
  creado_en: string;
}

export interface AuditList {
  items: AuditEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface AuditQuery {
  q?: string;
  accion?: string;
  entidad?: AuditEntity | '';
  desde?: string;
  hasta?: string;
  limit: number;
  offset: number;
}

@Injectable({ providedIn: 'root' })
export class AuditService {
  private readonly http = inject(HttpClient);
  private readonly companies = inject(CompanyService);

  list(query: AuditQuery): Observable<AuditList> {
    let params = new HttpParams().set('limit', query.limit).set('offset', query.offset);
    if (query.q) params = params.set('q', query.q);
    if (query.accion) params = params.set('accion', query.accion);
    if (query.entidad) params = params.set('entidad', query.entidad);
    if (query.desde) params = params.set('desde', query.desde);
    if (query.hasta) params = params.set('hasta', query.hasta);
    return this.companies.scoped(company => this.http.get<AuditList>('/api/admin/auditoria', {
      params,
      headers: { 'X-Empresa-Id': String(company.id) },
    }));
  }
}
