import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { CatalogList, CatalogProduct, CatalogQuery, CatalogVariant } from './catalog.models';
import { CatalogShopService } from './catalog-shop.service';

export interface CatalogAvailabilityItem {
  sucursal_id: number;
  sucursal: string;
  variante_id: number;
  talla: string;
  color: string;
  hay_existencias_fisicas: boolean;
  saldo_registrado: boolean;
  hay_disponibilidad?: boolean;
  actualizado_en?: string | null;
}

export interface CatalogAvailability {
  producto_id: number;
  alcance: 'STOCK_FISICO_REFERENCIAL';
  consultado_en: string;
  items: CatalogAvailabilityItem[];
}

@Injectable({ providedIn: 'root' })
export class CatalogApiService {
  private readonly http = inject(HttpClient);
  private readonly shop = inject(CatalogShopService);
  private readonly endpoint = '/api/catalogo/productos';
  // La API pública usa IndexedDB explícitamente. Sin este bypass, el worker puede
  // convertir una pérdida de red en 504 y ocultar la causa real al repositorio.
  private readonly headers = { 'ngsw-bypass': 'true' };

  private scoped(params: HttpParams = new HttpParams()): HttpParams {
    const tienda = this.shop.tienda();
    return tienda ? params.set('tienda', tienda) : params;
  }

  tiendas(): Observable<Array<{ slug: string; nombre: string }>> {
    return this.http.get<Array<{ slug: string; nombre: string }>>('/api/catalogo/tiendas', { headers: this.headers });
  }

  sucursales(): Observable<Array<{ id: number; nombre: string }>> {
    return this.http.get<Array<{ id: number; nombre: string }>>('/api/catalogo/sucursales', {
      params: this.scoped(), headers: this.headers,
    });
  }

  categorias(): Observable<Array<{ id: number; nombre: string }>> {
    return this.http.get<Array<{ id: number; nombre: string }>>('/api/catalogo/categorias', {
      params: this.scoped(), headers: this.headers,
    });
  }

  variantesTienda(limit = 100, offset = 0): Observable<{ items: CatalogVariant[]; total: number; limit: number; offset: number }> {
    return this.http.get<{ items: CatalogVariant[]; total: number; limit: number; offset: number }>(
      '/api/catalogo/variantes', {
        params: this.scoped(new HttpParams().set('limit', limit).set('offset', offset)),
        headers: this.headers,
      },
    );
  }

  variantes(slug: string): Observable<Array<{ id: number; talla: string; color: string }>> {
    return this.http.get<Array<{ id: number; talla: string; color: string }>>(
      `${this.endpoint}/${encodeURIComponent(slug)}/variantes`,
      { params: this.scoped(), headers: this.headers },
    );
  }

  list(query: CatalogQuery): Observable<CatalogList> {
    let params = this.scoped(new HttpParams().set('limit', query.limit).set('offset', query.offset));
    if (query.categoria_id !== undefined) params = params.set('categoria_id', query.categoria_id);
    if (query.talla) params = params.set('talla', query.talla);
    if (query.color) params = params.set('color', query.color);
    if (query.temporada) params = params.set('temporada', query.temporada);
    if (query.precio_min !== undefined) params = params.set('precio_min', query.precio_min);
    if (query.precio_max !== undefined) params = params.set('precio_max', query.precio_max);
    const name = query.q?.trim();
    if (name) params = params.set('q', name);
    return this.http.get<CatalogList>(this.endpoint, { params, headers: this.headers });
  }

  availability(slug: string, sucursalId?: number | null, varianteId?: number | null): Observable<CatalogAvailability> {
    let params = this.scoped();
    if (sucursalId) params = params.set('sucursal_id', sucursalId);
    if (varianteId) params = params.set('variante_id', varianteId);
    return this.http.get<CatalogAvailability>(
      `${this.endpoint}/${encodeURIComponent(slug)}/disponibilidad`,
      { headers: this.headers, params },
    );
  }

  get(slug: string): Observable<CatalogProduct> {
    return this.http.get<CatalogProduct>(`${this.endpoint}/${encodeURIComponent(slug)}`, { headers: this.headers, params: this.scoped() });
  }
}
