import { Injectable, inject } from '@angular/core';
import { IDB_FACTORY } from '../catalog/catalog-offline-store.service';
import { SyncOperation, SyncState } from './sync.models';

const DATABASE = 'vestinova-public-sync';
const STORE = 'operations';
const STATES: readonly SyncState[] = ['PENDIENTE', 'PROCESANDO', 'SINCRONIZADA', 'CONFLICTO', 'ERROR'];
const TERMINAL: readonly SyncState[] = ['SINCRONIZADA', 'CONFLICTO', 'ERROR'];
type FinishedState = 'SINCRONIZADA' | 'CONFLICTO' | 'ERROR';

class InvalidOperation extends Error {}

function storageError(): Error {
  return new Error('No se pudo acceder a la cola de sincronización de este navegador.');
}

@Injectable({ providedIn: 'root' })
export class SyncStore {
  private readonly factory = inject(IDB_FACTORY);

  list(): Promise<SyncOperation[]> {
    return this.transact<SyncOperation[]>('readonly', (store, done, guard) => {
      const request = store.getAll();
      request.onsuccess = () => guard(() => {
        const operations = request.result.map(sanitize);
        operations.sort((left, right) => Date.parse(left.createdAt) - Date.parse(right.createdAt)
          || (left.id < right.id ? -1 : left.id > right.id ? 1 : 0));
        done(operations);
      });
    });
  }

  async add(operation: SyncOperation): Promise<SyncOperation> {
    const clean = sanitize(operation);
    return this.update(clean.id, (current, store) => {
      if (current) {
        if (current.scope !== clean.scope || current.type !== clean.type
          || current.expectedDownloadedAt !== clean.expectedDownloadedAt) {
          throw new InvalidOperation('Ese UUID ya identifica otra operación de sincronización.');
        }
        return current;
      }
      if (clean.state !== 'PENDIENTE') throw new InvalidOperation('Una operación nueva debe estar pendiente.');
      store.add(clean);
      return clean;
    });
  }

  claim(id: string): Promise<SyncOperation | null> {
    return this.update(id, (current, store) => {
      if (!current || current.state !== 'PENDIENTE') return null;
      const claimed: SyncOperation = { ...current, state: 'PROCESANDO', updatedAt: new Date().toISOString(), message: null };
      store.put(claimed);
      return claimed;
    });
  }

  async finish(id: string, state: FinishedState, message: string | null): Promise<void> {
    if (!TERMINAL.includes(state)) throw new InvalidOperation('El estado final de sincronización no es válido.');
    const cleanMessage = sanitizeMessage(message);
    await this.update(id, (current, store) => {
      if (!current || current.state !== 'PROCESANDO') throw new InvalidOperation('Solo puede finalizarse una operación en proceso.');
      store.put({ ...current, state, updatedAt: new Date().toISOString(), message: cleanMessage });
    });
  }

  async retry(id: string): Promise<void> {
    await this.update(id, (current, store) => {
      if (!current || current.state !== 'ERROR') throw new InvalidOperation('Solo puede reintentarse una operación con error.');
      store.put({ ...current, state: 'PENDIENTE', updatedAt: new Date().toISOString(), message: null });
    });
  }

  /** El coordinador debe poseer el Web Lock global antes de recuperar operaciones interrumpidas. */
  recoverProcessing(): Promise<void> {
    return this.transact<void>('readwrite', (store, done, guard) => {
      const request = store.getAll();
      request.onsuccess = () => guard(() => {
        const now = new Date().toISOString();
        for (const raw of request.result) {
          const operation = sanitize(raw);
          if (operation.state === 'PROCESANDO') {
            store.put({ ...operation, state: 'PENDIENTE', updatedAt: now, message: null });
          }
        }
        done(undefined);
      });
    });
  }

  private async update<T>(id: string, change: (current: SyncOperation | null, store: IDBObjectStore) => T): Promise<T> {
    const key = sanitizeId(id);
    return this.transact<T>('readwrite', (store, done, guard) => {
      const request = store.get(key);
      request.onsuccess = () => guard(() => {
        const current = request.result === undefined ? null : sanitize(request.result);
        if (current && current.id !== key) throw new InvalidOperation('La operación guardada no corresponde a su UUID.');
        done(change(current, store));
      });
    });
  }

  private async transact<T>(
    mode: IDBTransactionMode,
    start: (store: IDBObjectStore, done: (result: T) => void, guard: (action: () => void) => void) => void,
  ): Promise<T> {
    const database = await this.open();
    return new Promise<T>((resolve, reject) => {
      let transaction: IDBTransaction | undefined;
      let result: T;
      let ready = false;
      let failure: Error | undefined;
      const fail = () => { database.close(); reject(failure ?? storageError()); };
      const guard = (action: () => void) => {
        try { action(); } catch (error: unknown) {
          failure = error instanceof InvalidOperation ? error : storageError();
          if (transaction) {
            try { transaction.abort(); } catch { fail(); }
          } else fail();
        }
      };
      guard(() => {
        transaction = database.transaction(STORE, mode);
        transaction.onabort = fail;
        transaction.oncomplete = () => {
          database.close();
          if (ready) resolve(result);
          else reject(storageError());
        };
        start(transaction.objectStore(STORE), value => { result = value; ready = true; }, guard);
      });
    });
  }

  private open(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      if (!this.factory) { reject(storageError()); return; }
      let failed = false;
      const fail = () => { failed = true; reject(storageError()); };
      try {
        const request = this.factory.open(DATABASE, 1);
        request.onupgradeneeded = () => {
          if (failed) request.transaction?.abort();
          else if (!request.result.objectStoreNames.contains(STORE)) request.result.createObjectStore(STORE, { keyPath: 'id' });
        };
        request.onerror = fail;
        request.onblocked = fail;
        request.onsuccess = () => {
          const database = request.result;
          database.onversionchange = () => database.close();
          if (failed) database.close();
          else resolve(database);
        };
      } catch { fail(); }
    });
  }
}

function sanitizeId(value: unknown): string {
  if (typeof value !== 'string' || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)) {
    throw new InvalidOperation('La operación debe identificarse mediante un UUID válido.');
  }
  return value.toLowerCase();
}

function timestamp(value: unknown): value is string {
  if (typeof value !== 'string' || value.length > 64) return false;
  const parts = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$/.exec(value);
  if (!parts || !Number.isFinite(Date.parse(value))) return false;
  const year = Number(parts[1]);
  const month = Number(parts[2]);
  const day = Number(parts[3]);
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return month >= 1 && month <= 12 && day >= 1 && day <= days[month - 1]
    && Number(parts[4]) <= 23 && Number(parts[5]) <= 59 && Number(parts[6]) <= 59;
}

function sanitizeMessage(value: unknown): string | null {
  if (value !== null && (typeof value !== 'string' || value.length > 2000)) {
    throw new InvalidOperation('El mensaje de sincronización no es válido.');
  }
  return value as string | null;
}

function sanitize(value: unknown): SyncOperation {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new InvalidOperation('La operación de sincronización no es válida.');
  const raw = value as Record<string, unknown>;
  const id = sanitizeId(raw['id']);
  const expectedDownloadedAt = raw['expectedDownloadedAt'];
  const state = raw['state'];
  const createdAt = raw['createdAt'];
  const updatedAt = raw['updatedAt'];
  if (raw['scope'] !== 'public-catalog' || raw['type'] !== 'ACTUALIZAR_CATALOGO'
    || (expectedDownloadedAt !== null && !timestamp(expectedDownloadedAt))
    || !STATES.includes(state as SyncState) || !timestamp(createdAt) || !timestamp(updatedAt)) {
    throw new InvalidOperation('La operación de sincronización no corresponde a un catálogo público válido.');
  }
  return {
    id, scope: 'public-catalog', type: 'ACTUALIZAR_CATALOGO', expectedDownloadedAt,
    state: state as SyncState, createdAt, updatedAt, message: sanitizeMessage(raw['message']),
  };
}
