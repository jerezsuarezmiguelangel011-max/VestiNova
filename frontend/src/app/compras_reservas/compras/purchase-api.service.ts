import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Injectable, InjectionToken, inject } from '@angular/core';
import { Observable, map } from 'rxjs';

export interface PurchaseCapabilities { habilitado: boolean; detail: string; }
export interface PurchaseItemInput { producto_id: number; cantidad: number; }
export interface PurchaseCommand { id: string; items: PurchaseItemInput[]; }
export interface PurchaseReceipt {
  readonly id: string;
  readonly estado: 'CONFIRMADA';
  readonly moneda: 'BOB';
  readonly total: string;
  readonly creado_en: string;
  readonly items: readonly {
    readonly producto_id: number;
    readonly nombre: string;
    readonly cantidad: number;
    readonly precio_unitario: string;
    readonly subtotal: string;
  }[];
}

/** Un adaptador futuro puede proporcionar acceso de cliente; no se reutiliza la sesión administrativa. */
export const PURCHASE_ACCESS_TOKEN = new InjectionToken<() => string | null>('VestiNova customer purchase access', {
  providedIn: 'root', factory: () => () => null,
});

@Injectable({ providedIn: 'root' })
export class PurchaseApiService {
  private readonly http = inject(HttpClient);
  private readonly accessToken = inject(PURCHASE_ACCESS_TOKEN);
  private readonly endpoint = '/api/compras';

  capabilities(): Observable<PurchaseCapabilities> {
    return this.http.get<PurchaseCapabilities>(`${this.endpoint}/capacidades`, { headers: this.headers() });
  }

  create(command: PurchaseCommand): Observable<PurchaseReceipt> {
    const body: PurchaseCommand = {
      id: command.id,
      items: command.items.map(item => ({ producto_id: item.producto_id, cantidad: item.cantidad })),
    };
    return this.http.post<unknown>(this.endpoint, body, { headers: this.headers() }).pipe(
      map(value => receipt(value, command.id, body.items)),
    );
  }

  get(id: string): Observable<PurchaseReceipt> {
    return this.http.get<unknown>(`${this.endpoint}/${encodeURIComponent(id)}`, { headers: this.headers() }).pipe(
      map(value => receipt(value, id)),
    );
  }

  private headers(): HttpHeaders {
    let headers = new HttpHeaders({ 'ngsw-bypass': 'true' });
    const token = this.accessToken();
    if (token) headers = headers.set('Authorization', `Bearer ${token}`);
    return headers;
  }
}

function receipt(value: unknown, id: string, expectedItems?: PurchaseItemInput[]): PurchaseReceipt {
  const invalid = () => new Error('No se pudo verificar la confirmación de compra.');
  if (!value || typeof value !== 'object') throw invalid();
  const result = value as Record<string, unknown>;
  const money = (amount: unknown): amount is string => typeof amount === 'string' && /^\d+\.\d{2}$/.test(amount);
  if (result['id'] !== id || result['estado'] !== 'CONFIRMADA' || result['moneda'] !== 'BOB' || !money(result['total'])
    || typeof result['creado_en'] !== 'string' || !Number.isFinite(Date.parse(result['creado_en']))
    || !Array.isArray(result['items']) || !result['items'].length) throw invalid();
  const items = result['items'] as Record<string, unknown>[];
  const ids = new Set<number>();
  for (const item of items) {
    if (!item || typeof item !== 'object' || !Number.isSafeInteger(item['producto_id']) || (item['producto_id'] as number) < 1
      || ids.has(item['producto_id'] as number) || !Number.isSafeInteger(item['cantidad']) || (item['cantidad'] as number) < 1
      || typeof item['nombre'] !== 'string' || !item['nombre'].trim()
      || !money(item['precio_unitario']) || !money(item['subtotal'])) throw invalid();
    ids.add(item['producto_id'] as number);
  }
  if (expectedItems && (items.length !== expectedItems.length || expectedItems.some(expected =>
    !items.some(item => item['producto_id'] === expected.producto_id && item['cantidad'] === expected.cantidad)))) throw invalid();
  return value as PurchaseReceipt;
}
