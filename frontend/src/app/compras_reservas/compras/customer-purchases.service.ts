import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { CustomerAuthService } from '../clientes/customer-auth.service';

export interface PurchaseHistoryLine {
  producto_id: number;
  variante_id: number | string;
  nombre: string;
  cantidad: number;
  precio_unitario: string;
  subtotal: string;
}

export interface ProductReview {
  id: number;
  compra_id: string;
  producto_id: number;
  puntuacion: number;
  comentario: string | null;
  compra_verificada: boolean;
  creado_en: string;
  actualizado_en: string;
}

export interface PurchaseHistoryItem {
  id: string;
  estado: 'CONFIRMADA';
  seguimiento_entrega: 'NO_DISPONIBLE' | 'ENTREGADA';
  entregada_en?: string | null;
  moneda: 'BOB';
  importe_total: string;
  creado_en: string;
  sucursal_id: number | string;
  items: PurchaseHistoryLine[];
}

export interface PurchaseHistoryPage {
  items: PurchaseHistoryItem[];
  total: number;
  limit: number;
  offset: number;
}

export type AfterSaleType = 'CAMBIO' | 'DEVOLUCION';
export type AfterSaleStatus = 'PENDIENTE' | 'APROBADA' | 'RECHAZADA' | 'COMPLETADA';

export interface AfterSaleItem {
  producto_id: number;
  nombre: string;
  variante_id: number | string;
  cantidad: number;
  precio_unitario: string;
}

export interface AfterSaleRequest {
  id: string;
  compra_id: string;
  tipo: AfterSaleType;
  estado: AfterSaleStatus;
  motivo: string;
  respuesta: string | null;
  referencia_reposicion: string | null;
  creado_en: string;
  actualizado_en: string;
  resuelto_en: string | null;
  completado_en: string | null;
  items: AfterSaleItem[];
}

export interface CreateAfterSaleRequest {
  id: string;
  compra_id: string;
  tipo: AfterSaleType;
  motivo: string;
  items: Array<{ producto_id: number; cantidad: number }>;
}

@Injectable({ providedIn: 'root' })
export class CustomerPurchasesService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(CustomerAuthService);

  history(slug: string, offset = 0): Observable<PurchaseHistoryPage> {
    const params = new HttpParams().set('limit', 20).set('offset', offset);
    return this.http.get<PurchaseHistoryPage>(`${this.base(slug)}/compras`, { headers: this.headers(slug), params });
  }

  afterSales(slug: string): Observable<{ items: AfterSaleRequest[]; total: number; limit: number; offset: number }> {
    return this.http.get<{ items: AfterSaleRequest[]; total: number; limit: number; offset: number }>(
      `${this.base(slug)}/postventa`, { headers: this.headers(slug), params: new HttpParams().set('limit', 100) },
    );
  }

  requestAfterSale(slug: string, request: CreateAfterSaleRequest): Observable<AfterSaleRequest> {
    return this.http.post<AfterSaleRequest>(`${this.base(slug)}/postventa`, request, { headers: this.headers(slug) });
  }

  reviews(slug: string): Observable<{ items: ProductReview[] }> {
    return this.http.get<{ items: ProductReview[] }>(`${this.base(slug)}/valoraciones`, { headers: this.headers(slug) });
  }

  createReview(slug: string, value: { compra_id: string; producto_id: number; puntuacion: number; comentario: string }): Observable<ProductReview> {
    return this.http.post<ProductReview>(`${this.base(slug)}/valoraciones`, value, { headers: this.headers(slug) });
  }

  editReview(slug: string, id: number, value: { puntuacion: number; comentario: string }): Observable<ProductReview> {
    return this.http.patch<ProductReview>(`${this.base(slug)}/valoraciones/${id}`, value, { headers: this.headers(slug) });
  }

  private base(slug: string): string { return `/api/tiendas/${encodeURIComponent(slug)}/cuenta`; }

  private headers(slug: string): HttpHeaders {
    let headers = new HttpHeaders({ 'ngsw-bypass': 'true' });
    const token = this.auth.token(slug);
    if (token) headers = headers.set('Authorization', `Bearer ${token}`);
    return headers;
  }
}
