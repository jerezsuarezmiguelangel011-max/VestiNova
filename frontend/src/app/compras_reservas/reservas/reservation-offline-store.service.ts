import { Injectable, inject } from '@angular/core';
import { IDB_FACTORY } from '../../catalogo_publico/catalogo/catalog-offline-store.service';
import type { CatalogProduct } from '../../catalogo_publico/catalogo/catalog.models';
import type { CatalogAvailability } from '../../catalogo_publico/catalogo/catalog-api.service';
import type { ReservationResult } from './reservation-online-api.service';
import type { ReservationDraft } from './reservation-draft';

export type OfflineReservationState =
  'BORRADOR_LOCAL' | 'PENDIENTE' | 'ENVIANDO' | 'CONFIRMADA' |
  'RECHAZADA' | 'CONFLICTO' | 'ERROR' | 'REQUIERE_ACCESO' |
  'CANCELADA' | 'VENCIDA' | 'ATENDIDA';

export interface OfflineReservation {
  id: string;
  tienda: string;
  cliente_id: number | null;
  draft: ReservationDraft;
  estado: OfflineReservationState;
  creado_en: string;
  actualizado_en: string;
  mensaje: string | null;
  resultado: ReservationResult | null;
}

export interface ReservationCatalogCopy {
  key: string;
  tienda: string;
  slug: string;
  guardado_en: string;
  vigencia_horas: number;
  producto: CatalogProduct;
  disponibilidad: CatalogAvailability;
}

const DATABASE = 'vestinova-reservas-offline';
const OPERATIONS = 'reservas';
const CATALOG = 'catalogo';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

function failure(): Error { return new Error('No se pudo usar IndexedDB. Revisa el almacenamiento del navegador.'); }
function validId(value: number): boolean { return Number.isSafeInteger(value) && value > 0; }

function validate(record: OfflineReservation): OfflineReservation {
  if (!UUID.test(record.id) || !SLUG.test(record.tienda) ||
      (record.cliente_id !== null && !validId(record.cliente_id)) ||
      record.draft.id !== record.id || record.draft.tienda !== record.tienda ||
      !validId(record.draft.sucursal_id) || !validId(record.draft.variante_id) ||
      !validId(record.draft.cantidad) || record.draft.cantidad > 100 ||
      (record.draft.lineas !== undefined &&
        (!Array.isArray(record.draft.lineas) || record.draft.lineas.length < 1 ||
         record.draft.lineas.length > 30 ||
         new Set(record.draft.lineas.map(line => line.variante_id)).size !== record.draft.lineas.length ||
         record.draft.lineas.some(line => !validId(line.variante_id) || !validId(line.cantidad) ||
           line.cantidad > 100 || line.sucursal_id !== record.draft.sucursal_id))) ||
      !Number.isFinite(Date.parse(record.creado_en)) ||
      !Number.isFinite(Date.parse(record.actualizado_en))) throw failure();
  return record;
}

@Injectable({ providedIn: 'root' })
export class ReservationOfflineStore {
  private readonly factory = inject(IDB_FACTORY);

  async remember(tienda: string, slug: string, producto: CatalogProduct, disponibilidad: CatalogAvailability, vigenciaHoras: number): Promise<void> {
    if (!SLUG.test(tienda) || !SLUG.test(slug) || slug !== producto.slug ||
        producto.id !== disponibilidad.producto_id || !Number.isSafeInteger(vigenciaHoras) ||
        vigenciaHoras < 1 || vigenciaHoras > 720) throw failure();
    const copy: ReservationCatalogCopy = {
      key: `${tienda}:${slug}`, tienda, slug,
      guardado_en: new Date().toISOString(), producto, disponibilidad, vigencia_horas: vigenciaHoras,
    };
    await this.request(CATALOG, 'readwrite', store => store.put(copy));
  }

  async cached(tienda: string, slug: string): Promise<ReservationCatalogCopy | null> {
    if (!SLUG.test(tienda) || !SLUG.test(slug)) return null;
    const stored = await this.request<ReservationCatalogCopy | undefined>(
      CATALOG, 'readonly', store => store.get(`${tienda}:${slug}`));
    return stored?.tienda === tienda && stored.slug === slug ? stored : null;
  }

  async list(tienda: string, clienteId: number | null): Promise<OfflineReservation[]> {
    if (!SLUG.test(tienda)) return [];
    const all = await this.request<OfflineReservation[]>(OPERATIONS, 'readonly', store => store.getAll());
    return all.map(validate).filter(op => op.tienda === tienda &&
      (clienteId === null ? op.cliente_id === null : op.cliente_id === clienteId))
      .sort((a, b) => b.creado_en.localeCompare(a.creado_en));
  }

  async get(id: string): Promise<OfflineReservation | null> {
    if (!UUID.test(id)) throw failure();
    const row = await this.request<OfflineReservation | undefined>(
      OPERATIONS, 'readonly', store => store.get(id));
    return row ? validate(row) : null;
  }

  async saveDraft(draft: ReservationDraft, clienteId: number | null): Promise<OfflineReservation> {
    if (!UUID.test(draft.id) || !SLUG.test(draft.tienda) ||
        (clienteId !== null && !validId(clienteId))) throw failure();
    const now = new Date().toISOString();
    return this.mutate(draft.id, (previous, store) => {
      if (previous) {
        if (JSON.stringify(previous.draft) !== JSON.stringify(draft) ||
            previous.cliente_id !== clienteId) {
          throw new Error('El UUID ya pertenece a otra reserva. No se sobrescribió.');
        }
        return previous;
      }
      const row = validate({
        id: draft.id, tienda: draft.tienda, cliente_id: clienteId, draft,
        estado: clienteId === null ? 'BORRADOR_LOCAL' : 'PENDIENTE',
        creado_en: draft.creado_en, actualizado_en: now, mensaje: null, resultado: null,
      });
      store.add(row);
      return row;
    });
  }

  async discardDraft(id: string, tienda: string): Promise<void> {
    await this.mutate(id, (previous, store) => {
      if (!previous || previous.tienda !== tienda ||
          previous.estado !== 'BORRADOR_LOCAL' || previous.cliente_id !== null) {
        throw new Error('Solo se pueden descartar borradores sin enviar.');
      }
      store.delete(id);
    });
  }

  async assign(id: string, tienda: string, clienteId: number): Promise<OfflineReservation> {
    if (!validId(clienteId)) throw failure();
    return this.mutate(id, (previous, store) => {
      if (!previous || previous.tienda !== tienda || previous.estado !== 'BORRADOR_LOCAL' ||
          previous.cliente_id !== null) throw new Error('No se puede asociar este borrador.');
      const assigned: OfflineReservation = {
        ...previous, cliente_id: clienteId, estado: 'PENDIENTE',
        actualizado_en: new Date().toISOString(), mensaje: null,
      };
      store.put(assigned);
      return assigned;
    });
  }

  async claim(id: string, tienda: string, clienteId: number): Promise<OfflineReservation | null> {
    return this.mutate(id, (previous, store) => {
      if (!previous || previous.tienda !== tienda || previous.cliente_id !== clienteId ||
          !['PENDIENTE', 'ERROR', 'REQUIERE_ACCESO'].includes(previous.estado)) return null;
      const claimed: OfflineReservation = { ...previous, estado: 'ENVIANDO',
        actualizado_en: new Date().toISOString(), mensaje: null };
      store.put(claimed);
      return claimed;
    });
  }

  async finish(id: string, state: Exclude<OfflineReservationState, 'BORRADOR_LOCAL' | 'PENDIENTE' | 'ENVIANDO'>,
               message: string | null, result: ReservationResult | null = null): Promise<void> {
    await this.mutate(id, (previous, store) => {
      if (!previous || previous.estado !== 'ENVIANDO') throw failure();
      store.put({ ...previous, estado: state, mensaje: message?.slice(0, 350) ?? null,
        actualizado_en: new Date().toISOString(), resultado: result });
    });
  }

  async retry(id: string, tienda: string, clienteId: number): Promise<void> {
    await this.mutate(id, (previous, store) => {
      if (!previous || previous.tienda !== tienda || previous.cliente_id !== clienteId ||
          !['ERROR', 'REQUIERE_ACCESO'].includes(previous.estado)) throw failure();
      store.put({ ...previous, estado: 'PENDIENTE', mensaje: null,
        actualizado_en: new Date().toISOString() });
    });
  }

  async recoverSending(tienda: string, clienteId: number): Promise<void> {
    await this.transact<void>(OPERATIONS, 'readwrite', (store, ready, guard) => {
      const request = store.getAll();
      request.onsuccess = () => guard(() => {
        for (const row of request.result as OfflineReservation[]) {
          validate(row);
          if (row.tienda === tienda && row.cliente_id === clienteId && row.estado === 'ENVIANDO') {
            store.put({ ...row, estado: 'PENDIENTE', actualizado_en: new Date().toISOString(),
              mensaje: 'Reintento recuperado tras una interrupción. UUID conservado.' });
          }
        }
        ready(undefined);
      });
    });
  }

  // Los registros históricos nunca se eliminan al intentar sincronizar.
  private async mutate<T>(id: string,
    action: (current: OfflineReservation | null, store: IDBObjectStore) => T): Promise<T> {
    if (!UUID.test(id)) throw failure();
    return this.transact(OPERATIONS, 'readwrite', (store, ready, guard) => {
      const request = store.get(id);
      request.onsuccess = () => guard(() =>
        ready(action(request.result ? validate(request.result as OfflineReservation) : null, store)));
    });
  }

  private async request<T>(name: string, mode: IDBTransactionMode,
                           action: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
    return this.transact<T>(name, mode, (store, ready, guard) => {
      const request = action(store);
      request.onsuccess = () => guard(() => ready(request.result));
    });
  }

  private async transact<T>(name: string, mode: IDBTransactionMode,
    start: (store: IDBObjectStore, ready: (result: T) => void, guard: (callback: () => void) => void) => void): Promise<T> {
    const db = await this.open();
    return new Promise<T>((resolve, reject) => {
      let transaction: IDBTransaction;
      let value!: T;
      let hasValue = false;
      let error: unknown = null;
      try {
        transaction = db.transaction(name, mode);
        const guard = (callback: () => void) => {
          try { callback(); } catch (cause) {
            error = cause;
            try { transaction.abort(); } catch { db.close(); reject(cause); }
          }
        };
        transaction.oncomplete = () => {
          db.close();
          hasValue ? resolve(value) : reject(failure());
        };
        transaction.onerror = () => { /* onabort rechaza sin confirmar escritura */ };
        transaction.onabort = () => { db.close(); reject(error ?? failure()); };
        start(transaction.objectStore(name), next => { value = next; hasValue = true; }, guard);
      } catch (cause) { db.close(); reject(cause); }
    });
  }

  private open(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      if (!this.factory) { reject(failure()); return; }
      const request = this.factory.open(DATABASE, 1);
      request.onerror = () => reject(failure());
      request.onblocked = () => reject(failure());
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains(OPERATIONS)) db.createObjectStore(OPERATIONS, { keyPath: 'id' });
        if (!db.objectStoreNames.contains(CATALOG)) db.createObjectStore(CATALOG, { keyPath: 'key' });
      };
      request.onsuccess = () => {
        const db = request.result;
        db.onversionchange = () => db.close();
        resolve(db);
      };
    });
  }
}
