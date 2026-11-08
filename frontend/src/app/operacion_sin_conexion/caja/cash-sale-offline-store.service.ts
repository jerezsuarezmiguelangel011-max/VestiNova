import { Injectable, inject } from '@angular/core';
import { IDB_FACTORY } from '../../catalogo_publico/catalogo/catalog-offline-store.service';
import type { CashSaleInput, CashSaleResult, CashSnapshot } from './cash-sale-api.service';

export type CashSyncState =
  'PENDIENTE' | 'ENVIANDO' | 'CONFIRMADA' | 'CONFLICTO' | 'RECHAZADA' |
  'ERROR' | 'REQUIERE_ACCESO';

export interface CashLocalSnapshot extends CashSnapshot {
  key: string;
  usuario_id: number;
}

export interface CashLocalSale {
  id: string;
  empresa_id: number;
  usuario_id: number;
  sucursal_id: number;
  creado_en: string;
  estado: CashSyncState;
  solicitud: CashSaleInput;
  total: string;
  cambio: string;
  motivo: string | null;
  incidencia_id: string | null;
  resultado: CashSaleResult | null;
  actualizado_en: string;
}

const DB_NAME = 'vestinova-caja-cu15';
const SNAPSHOTS = 'catalogos';
const SALES = 'ventas';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const positive = (value: number) => Number.isSafeInteger(value) && value > 0;
const error = () => new Error('No se pudo utilizar IndexedDB para las ventas de contado.');

@Injectable({ providedIn: 'root' })
export class CashSaleOfflineStore {
  private readonly factory = inject(IDB_FACTORY);
  static key(company: number, user: number, branch: number): string {
    if (![company, user, branch].every(positive)) throw error();
    return `${company}:${user}:${branch}`;
  }

  async saveCatalog(snapshot: CashSnapshot, user: number): Promise<void> {
    const key = CashSaleOfflineStore.key(snapshot.empresa_id, user, snapshot.sucursal_id);
    if (!Array.isArray(snapshot.items) || snapshot.items.length > 300 ||
        !Number.isFinite(Date.parse(snapshot.descargado_en)) ||
        snapshot.items.some(item => !positive(item.variante_id) || !positive(item.producto_id)
          || !/^(?:0|[1-9]\d{0,7})\.\d{2}$/.test(item.precio_unitario))) throw error();
    await this.run(SNAPSHOTS, 'readwrite', store => store.put({ ...snapshot, key, usuario_id: user }));
  }

  async catalogs(company: number, user: number): Promise<CashLocalSnapshot[]> {
    if (![company, user].every(positive)) return [];
    const values = await this.run<CashLocalSnapshot[]>(SNAPSHOTS, 'readonly', store => store.getAll());
    return values.filter(row => row.empresa_id === company && row.usuario_id === user);
  }

  async catalog(company: number, user: number, branch: number): Promise<CashLocalSnapshot | null> {
    const key = CashSaleOfflineStore.key(company, user, branch);
    const row = await this.run<CashLocalSnapshot | undefined>(
      SNAPSHOTS, 'readonly', store => store.get(key));
    return row?.key === key && row.empresa_id === company && row.usuario_id === user
      && row.sucursal_id === branch ? row : null;
  }

  async enqueue(row: CashLocalSale): Promise<void> {
    this.validate(row);
    await this.run(SALES, 'readwrite', store => store.add(row));
  }

  async list(company: number, user: number): Promise<CashLocalSale[]> {
    if (![company, user].every(positive)) return [];
    const rows = await this.run<CashLocalSale[]>(SALES, 'readonly', store => store.getAll());
    return rows.filter(row => {
      this.validate(row);
      return row.empresa_id === company && row.usuario_id === user;
    }).sort((a, b) => b.creado_en.localeCompare(a.creado_en));
  }

  async claim(id: string, company: number, user: number): Promise<CashLocalSale | null> {
    return this.mutate(id, (row, store) => {
      if (!row || row.empresa_id !== company || row.usuario_id !== user ||
          !['PENDIENTE', 'ERROR', 'REQUIERE_ACCESO'].includes(row.estado)) return null;
      const sent = { ...row, estado: 'ENVIANDO' as const, actualizado_en: new Date().toISOString() };
      store.put(sent);
      return sent;
    });
  }

  async finish(id: string, state: Exclude<CashSyncState, 'PENDIENTE'|'ENVIANDO'>,
    message: string | null, result: CashSaleResult | null = null, incident: string | null = null): Promise<void> {
    await this.mutate(id, (row, store) => {
      if (!row || row.estado !== 'ENVIANDO') throw error();
      store.put({ ...row, estado: state, motivo: message?.slice(0, 350) ?? null,
        resultado: result, incidencia_id: incident,
        actualizado_en: new Date().toISOString() });
    });
  }

  async retry(id: string, company: number, user: number): Promise<void> {
    await this.mutate(id, (row, store) => {
      if (!row || row.empresa_id !== company || row.usuario_id !== user ||
          !['ERROR', 'REQUIERE_ACCESO'].includes(row.estado)) throw error();
      store.put({ ...row, estado: 'PENDIENTE', motivo: null,
        actualizado_en: new Date().toISOString() });
    });
  }

  async recover(company: number, user: number): Promise<void> {
    const rows = await this.list(company, user);
    for (const row of rows.filter(item => item.estado === 'ENVIANDO')) {
      await this.mutate(row.id, (current, store) => {
        if (current && current.estado === 'ENVIANDO' &&
            current.empresa_id === company && current.usuario_id === user) {
          store.put({ ...current, estado: 'PENDIENTE', motivo: 'Envío interrumpido: conserva el UUID.',
            actualizado_en: new Date().toISOString() });
        }
      });
    }
  }

  private validate(row: CashLocalSale): void {
    if (!UUID.test(row.id) || row.solicitud.id !== row.id ||
        ![row.empresa_id, row.usuario_id, row.sucursal_id].every(positive) ||
        row.solicitud.sucursal_id !== row.sucursal_id ||
        row.solicitud.origen !== 'WEB_OFFLINE' || !row.solicitud.efectivo_cobrado ||
        !Number.isFinite(Date.parse(row.creado_en)) ||
        !Array.isArray(row.solicitud.lineas) ||
        row.solicitud.lineas.length < 1 || row.solicitud.lineas.length > 30 ||
        !['PENDIENTE', 'ENVIANDO', 'CONFIRMADA', 'CONFLICTO', 'RECHAZADA', 'ERROR', 'REQUIERE_ACCESO'].includes(row.estado)) {
      throw error();
    }
  }

  private async mutate<T>(id: string, callback: (row: CashLocalSale | null,
    store: IDBObjectStore) => T): Promise<T> {
    if (!UUID.test(id)) throw error();
    return this.transaction(SALES, 'readwrite', (store, finish, guard) => {
      const request = store.get(id);
      request.onsuccess = () => guard(() =>
        finish(callback(request.result as CashLocalSale | undefined ?? null, store)));
    });
  }

  private run<T>(name: string, mode: IDBTransactionMode,
    action: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
    return this.transaction(name, mode, (store, finish, guard) => {
      const request = action(store);
      request.onsuccess = () => guard(() => finish(request.result));
    });
  }

  private async transaction<T>(name: string, mode: IDBTransactionMode,
    start: (store: IDBObjectStore, finish: (value: T) => void,
      guard: (callback: () => void) => void) => void): Promise<T> {
    const db = await this.open();
    return new Promise<T>((resolve, reject) => {
      let tx: IDBTransaction;
      let value!: T;
      let finished = false;
      let failure: unknown;
      try {
        tx = db.transaction(name, mode);
        const guard = (callback: () => void) => {
          try { callback(); } catch (cause) {
            failure = cause;
            try { tx.abort(); } catch { db.close(); reject(cause); }
          }
        };
        tx.oncomplete = () => { db.close(); finished ? resolve(value) : reject(error()); };
        tx.onabort = () => { db.close(); reject(failure ?? error()); };
        start(tx.objectStore(name), result => { value = result; finished = true; }, guard);
      } catch (cause) { db.close(); reject(cause); }
    });
  }

  private open(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      if (!this.factory) { reject(error()); return; }
      const request = this.factory.open(DB_NAME, 1);
      request.onblocked = request.onerror = () => reject(error());
      request.onupgradeneeded = () => {
        if (!request.result.objectStoreNames.contains(SALES))
          request.result.createObjectStore(SALES, { keyPath: 'id' });
        if (!request.result.objectStoreNames.contains(SNAPSHOTS))
          request.result.createObjectStore(SNAPSHOTS, { keyPath: 'key' });
      };
      request.onsuccess = () => { request.result.onversionchange = () => request.result.close(); resolve(request.result); };
    });
  }
}
