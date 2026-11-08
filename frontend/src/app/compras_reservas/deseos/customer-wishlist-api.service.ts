import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { CustomerAuthService } from '../clientes/customer-auth.service';

export interface WishlistItem {
  variante_id: number;
  producto_id: number;
  slug: string | null;
  nombre: string;
  talla: string;
  color: string;
  imagen_url: string | null;
  precio_vigente: string | null;
  moneda: 'BOB';
  publicada: boolean;
  disponibilidad: 'NO_VERIFICADA' | 'DISPONIBLE_REFERENCIAL' | 'AGOTADA' | 'DESPUBLICADA';
  creado_en: string;
}

@Injectable({ providedIn: 'root' })
export class CustomerWishlistApi {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(CustomerAuthService);

  private url(tienda: string): string {
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(tienda)) throw new Error('Tienda no válida.');
    return `/api/tiendas/${encodeURIComponent(tienda)}/cuenta/deseos`;
  }

  private options(tienda: string) {
    const token = this.auth.token(tienda);
    if (!token) throw new Error('Inicia sesión como cliente para gestionar tus deseos.');
    return { headers: { Authorization: `Bearer ${token}`, 'ngsw-bypass': 'true' } };
  }

  list(tienda: string) {
    return this.http.get<{ items: WishlistItem[]; total: number }>(
      this.url(tienda), this.options(tienda));
  }

  add(tienda: string, variante_id: number) {
    return this.http.post<{ variante_id: number; agregado: boolean }>(
      this.url(tienda), { variante_id }, this.options(tienda));
  }

  remove(tienda: string, variante_id: number) {
    return this.http.delete<void>(
      `${this.url(tienda)}/${encodeURIComponent(variante_id)}`, this.options(tienda));
  }
}
