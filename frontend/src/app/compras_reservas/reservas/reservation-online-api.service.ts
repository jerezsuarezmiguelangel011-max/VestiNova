import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { CustomerAuthService } from '../clientes/customer-auth.service';

export interface ReservationResult {
  id: string;
  codigo: string;
  estado: 'CONFIRMADA' | 'CANCELADA' | 'VENCIDA' | 'ATENDIDA';
  sucursal_id: number;
  cliente_id: number;
  lineas: { variante_id: number; cantidad: number }[];
  creada_en: string;
  vence_en: string;
  actualizada_en: string;
}

export interface ReservationRequest {
  id: string;
  sucursal_id: number;
  lineas: { variante_id: number; cantidad: number }[];
  solicitado_en?: string;
  origen?: 'EN_LINEA' | 'WEB_OFFLINE' | 'MOVIL_OFFLINE';
}

@Injectable({ providedIn: 'root' })
export class ReservationOnlineApiService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(CustomerAuthService);

  private base(slug: string): string {
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)) throw new Error('Tienda no válida.');
    return `/api/tiendas/${encodeURIComponent(slug)}/reservas`;
  }

  private headers(slug: string): HttpHeaders {
    const token = this.auth.token(slug);
    if (!token) throw new Error('Inicia sesión como cliente de esta tienda.');
    return new HttpHeaders({ Authorization: `Bearer ${token}` });
  }

  policy(slug: string): Observable<{ vigencia_horas: number; requiere_conexion: true }> {
    return this.http.get<{ vigencia_horas: number; requiere_conexion: true }>(
      this.base(slug) + '/politica', { headers: { 'ngsw-bypass': 'true' } },
    );
  }

  create(slug: string, body: ReservationRequest): Observable<ReservationResult> {
    return this.http.post<ReservationResult>(this.base(slug), body, { headers: this.headers(slug) });
  }

  list(slug: string): Observable<ReservationResult[]> {
    return this.http.get<ReservationResult[]>(this.base(slug), { headers: this.headers(slug) });
  }

  cancel(slug: string, id: string): Observable<ReservationResult> {
    if (!/^[0-9a-f-]{36}$/i.test(id)) throw new Error('Identificador inválido.');
    return this.http.post<ReservationResult>(
      `${this.base(slug)}/${encodeURIComponent(id)}/cancelar`, {},
      { headers: this.headers(slug) },
    );
  }
}
