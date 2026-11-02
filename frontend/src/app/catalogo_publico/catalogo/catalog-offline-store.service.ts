import { Injectable, InjectionToken, inject } from '@angular/core';
import { CatalogLocalError, CatalogSnapshot, copyPublicProduct } from './catalog.models';

export const IDB_FACTORY = new InjectionToken<IDBFactory | undefined>('VestiNova public catalog IndexedDB', {
  providedIn: 'root',
  factory: () => {
    try { return globalThis.indexedDB; } catch { return undefined; }
  },
});

const DATABASE = 'vestinova-public-catalog';
const STORE = 'snapshots';
const SCOPE = 'public-catalog';

/** A single record keeps the public products and their metadata in the same transaction. */
@Injectable({ providedIn: 'root' })
export class CatalogOfflineStoreService {
  private readonly factory = inject(IDB_FACTORY);

  read(): Promise<CatalogSnapshot | null> {
    return this.transact('readonly', store => {
      let stored: unknown;
      const request = store.get(SCOPE);
      request.onsuccess = () => { stored = request.result; };
      return () => stored === undefined ? null : sanitizeSnapshot(stored);
    });
  }

  async replace(snapshot: CatalogSnapshot): Promise<void> {
    // Validate and copy before starting the write, leaving the previous copy untouched on failure.
    const sanitized = sanitizeSnapshot(snapshot);
    await this.transact('readwrite', store => {
      store.put(sanitized);
      return () => undefined;
    });
  }

  private async transact<T>(mode: IDBTransactionMode, prepare: (store: IDBObjectStore) => () => T): Promise<T> {
    const database = await this.open();
    return new Promise<T>((resolve, reject) => {
      let transaction: IDBTransaction | undefined;
      const fail = () => {
        database.close();
        reject(new CatalogLocalError('storage'));
      };
      try {
        transaction = database.transaction(STORE, mode);
        transaction.onabort = fail;
        const result = prepare(transaction.objectStore(STORE));
        transaction.oncomplete = () => {
          database.close();
          try { resolve(result()); } catch { reject(new CatalogLocalError('storage')); }
        };
      } catch {
        // Even a synchronous request failure must roll back a write already queued in this transaction.
        if (transaction) {
          try { transaction.abort(); } catch { fail(); }
        } else fail();
      }
    });
  }

  private open(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      if (!this.factory) {
        reject(new CatalogLocalError('storage'));
        return;
      }
      let failed = false;
      const fail = () => {
        failed = true;
        reject(new CatalogLocalError('storage'));
      };
      try {
        const request = this.factory.open(DATABASE, 1);
        request.onupgradeneeded = () => {
          if (failed) {
            request.transaction?.abort();
          } else if (!request.result.objectStoreNames.contains(STORE)) {
            request.result.createObjectStore(STORE, { keyPath: 'scope' });
          }
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

function sanitizeSnapshot(value: unknown): CatalogSnapshot {
  const invalid = () => new Error('La copia del catálogo no es válida.');
  if (!value || typeof value !== 'object') throw invalid();
  const snapshot = value as Record<string, unknown>;
  const downloadedAt = snapshot['downloadedAt'];
  const total = snapshot['total'];
  const values = snapshot['products'];
  if (snapshot['schemaVersion'] !== 1 || snapshot['scope'] !== SCOPE
    || typeof downloadedAt !== 'string' || downloadedAt.length > 64
    || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$/.test(downloadedAt)
    || !Number.isFinite(Date.parse(downloadedAt))
    || !Number.isSafeInteger(total) || (total as number) < 0
    || !Array.isArray(values) || values.length !== total) {
    throw invalid();
  }
  const products = values.map(copyPublicProduct);
  const ids = new Set(products.map(product => product.id));
  const slugs = new Set(products.map(product => product.slug));
  if (ids.size !== products.length || slugs.size !== products.length) throw invalid();
  return { schemaVersion: 1, scope: SCOPE, downloadedAt, total: total as number, products };
}
