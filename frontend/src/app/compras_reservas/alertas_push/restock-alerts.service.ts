import { HttpClient, HttpHeaders } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { SwPush } from '@angular/service-worker';
import { firstValueFrom } from 'rxjs';
import { CustomerAuthService } from '../clientes/customer-auth.service';

export interface RestockAlert {
  id: number;
  variante_id: number;
  sucursal_id: number;
  estado: 'ACTIVA' | 'CANCELADA';
  creado_en: string;
  producto_nombre?: string | null;
  producto_slug?: string | null;
  talla?: string | null;
  color?: string | null;
  sucursal_nombre?: string | null;
}

@Injectable({ providedIn: 'root' })
export class RestockAlertsService {
  private readonly http = inject(HttpClient);
  private readonly swPush = inject(SwPush, { optional: true });
  private readonly auth = inject(CustomerAuthService);

  private base(slug: string): string {
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)) throw new Error('Tienda inválida.');
    return '/api/tiendas/' + encodeURIComponent(slug) + '/cuenta/alertas-push';
  }

  private headers(slug: string): HttpHeaders {
    const token = this.auth.token(slug);
    if (!token) throw new Error('Inicia sesión para gestionar avisos de reposición.');
    return new HttpHeaders({ Authorization: 'Bearer ' + token, 'ngsw-bypass': 'true' });
  }

  async status(slug: string): Promise<{ serverEnabled: boolean; browserEnabled: boolean }> {
    const settings = await firstValueFrom(this.http.get<{ habilitado: boolean }>(
      this.base(slug) + '/config', { headers: this.headers(slug) }));
    return { serverEnabled: settings.habilitado, browserEnabled: !!this.swPush?.isEnabled };
  }

  async list(slug: string): Promise<RestockAlert[]> {
    const result = await firstValueFrom(this.http.get<{ items: RestockAlert[] }>(
      this.base(slug) + '/avisos', { headers: this.headers(slug) }));
    return result.items;
  }

  async subscribe(slug: string, varianteId: number, sucursalId: number): Promise<void> {
    const base = this.base(slug);
    const headers = this.headers(slug);
    const settings = await firstValueFrom(this.http.get<{ habilitado: boolean; vapid_public_key: string | null }>(
      base + '/config', { headers }));
    if (!settings.habilitado || !settings.vapid_public_key) {
      throw new Error('Las notificaciones push todavía no están configuradas en el servidor.');
    }
    const swPush = this.swPush;
    if (!swPush || !swPush.isEnabled) {
      throw new Error('Abre la PWA instalada sobre HTTPS o localhost para activar notificaciones.');
    }
    const subscription = await swPush.requestSubscription({ serverPublicKey: settings.vapid_public_key });
    const details = subscription.toJSON();
    if (!details.endpoint || !details.keys?.['p256dh'] || !details.keys?.['auth']) {
      throw new Error('El navegador no entregó un canal Web Push válido.');
    }
    await firstValueFrom(this.http.post(base + '/canales',
      { endpoint: details.endpoint, keys: { p256dh: details.keys['p256dh'], auth: details.keys['auth'] } },
      { headers }));
    await firstValueFrom(this.http.post(base + '/avisos',
      { variante_id: varianteId, sucursal_id: sucursalId }, { headers }));
  }

  async cancel(slug: string, id: number): Promise<void> {
    await firstValueFrom(this.http.delete<void>(this.base(slug) + '/avisos/' + id, { headers: this.headers(slug) }));
  }
}
