import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { CustomerAuthService } from '../../compras_reservas/clientes/customer-auth.service';
import type { RecommendationResult } from './recommendations-api.service';

/** Personalización voluntaria y aislada por sesión de cliente y tienda. */
@Injectable({ providedIn: 'root' })
export class CustomerRecommendationsService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(CustomerAuthService);

  private url(tienda: string) {
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(tienda)) throw new Error('Tienda no válida.');
    return `/api/tiendas/${encodeURIComponent(tienda)}/cuenta/recomendaciones`;
  }
  private headers(tienda: string) {
    const token = this.auth.token(tienda);
    if (!token) throw new Error('La sesión del cliente no está disponible.');
    return { headers: { Authorization: `Bearer ${token}`, 'ngsw-bypass': 'true' } };
  }

  activeSession(tienda: string): boolean {
    return !!this.auth.token(tienda);
  }
  preferences(tienda: string) {
    return this.http.get<{ habilitado: boolean }>(
      this.url(tienda) + '/preferencias', this.headers(tienda));
  }
  setPreferences(tienda: string, habilitado: boolean) {
    return this.http.put<{ habilitado: boolean; historial_borrado: boolean }>(
      this.url(tienda) + '/preferencias', { habilitado }, this.headers(tienda));
  }
  registerView(tienda: string, producto_slug: string) {
    return this.http.post<{ registrado: boolean }>(
      this.url(tienda) + '/visitas', { producto_slug }, this.headers(tienda));
  }
  recommendations(tienda: string, options: {
    talla?: string; color?: string; sucursal_id?: number | null;
  }) {
    let params = new HttpParams().set('limit', 12);
    if (options.talla) params = params.set('talla', options.talla);
    if (options.color) params = params.set('color', options.color);
    if (options.sucursal_id) params = params.set('sucursal_id', options.sucursal_id);
    return this.http.get<RecommendationResult>(
      this.url(tienda) + '/sugerencias', { ...this.headers(tienda), params });
  }
}
