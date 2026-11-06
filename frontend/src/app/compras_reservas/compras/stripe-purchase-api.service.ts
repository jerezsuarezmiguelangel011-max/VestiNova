import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { CustomerAuthService } from '../clientes/customer-auth.service';

export interface StripeCheckoutItem {
  producto_id: number;
  variante_id: number;
  cantidad: number;
}
export interface StripeCheckoutInput {
  id: string;
  sucursal_id: number;
  entrega: 'RETIRO' | 'DOMICILIO';
  direccion: string;
  items: StripeCheckoutItem[];
}
export interface StripeReceipt {
  numero: string;
  estado: 'CONFIRMADA';
  entrega: 'PENDIENTE';
  total: string;
  moneda: 'BOB';
  creado_en: string;
  items: Array<{ nombre: string; variante_id: number; cantidad: number; precio_unitario: string }>;
}
export interface StripeCheckoutState {
  id: string;
  estado: 'PENDIENTE' | 'PAGO_PENDIENTE' | 'CONFIRMADA' | 'INCIDENCIA' | 'RECHAZADA' | 'EXPIRADA';
  moneda: 'BOB';
  total: string;
  checkout_url: string | null;
  detalle: string | null;
  comprobante?: StripeReceipt;
}
export interface StripeCapabilities { habilitado: boolean; pasarela: 'STRIPE_TEST'; detail: string; }

/** Solo se envía la sesión del cliente de ESTA tienda, nunca la sesión administrativa. */
@Injectable({ providedIn: 'root' })
export class StripePurchaseApiService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(CustomerAuthService);

  private url(slug: string): string {
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)) throw new Error('Tienda no válida.');
    return '/api/tiendas/' + encodeURIComponent(slug) + '/compras';
  }
  private headers(slug: string): HttpHeaders {
    let headers = new HttpHeaders({ 'ngsw-bypass': 'true' });
    const token = this.auth.token(slug);
    if (token) headers = headers.set('Authorization', 'Bearer ' + token);
    return headers;
  }
  capabilities(slug: string): Observable<StripeCapabilities> {
    return this.http.get<StripeCapabilities>(this.url(slug) + '/capacidades', { headers: this.headers(slug) });
  }
  checkout(slug: string, payload: StripeCheckoutInput): Observable<StripeCheckoutState> {
    return this.http.post<StripeCheckoutState>(this.url(slug) + '/checkout', payload, { headers: this.headers(slug) });
  }
  status(slug: string, id: string): Observable<StripeCheckoutState> {
    return this.http.get<StripeCheckoutState>(
      this.url(slug) + '/' + encodeURIComponent(id) + '/estado', { headers: this.headers(slug) },
    );
  }
}
