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

  read(scope = SCOPE): Promise<CatalogSnapshot | null> {
    return this.transact('readonly', store => {
      let stored: unknown;
      const request = store.get(scope);
      request.onsuccess = () => { stored = request.result; };
      return () => stored === undefined ? null : sanitizeSnapshot(stored, scope);
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

function sanitizeSnapshot(value: unknown, expectedScope?: string): CatalogSnapshot {
  const invalid = () => new Error('La copia del catálogo no es válida.');
  if (!value || typeof value !== 'object') throw invalid();
  const snapshot = value as Record<string, unknown>;
  const downloadedAt = snapshot['downloadedAt'];
  const total = snapshot['total'];
  const values = snapshot['products'];
  if (snapshot['schemaVersion'] !== 1 || typeof snapshot['scope'] !== 'string'
    || !/^public-catalog(?::[a-z0-9]+(?:-[a-z0-9]+)*)?$/.test(snapshot['scope'])
    || (expectedScope !== undefined && snapshot['scope'] !== expectedScope)
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
  const storedVariants = snapshot['variants'];
  if (storedVariants !== undefined && (!Array.isArray(storedVariants) || storedVariants.length > 100000)) {
    throw invalid();
  }
  const variants = storedVariants === undefined ? undefined : (storedVariants as unknown[]).map(item => {
    if (!item || typeof item !== 'object') throw invalid();
    const variant = item as Record<string, unknown>;
    if (!Number.isSafeInteger(variant['id']) || (variant['id'] as number) < 1
      || typeof variant['producto_slug'] !== 'string' || !slugs.has(variant['producto_slug'])
      || typeof variant['talla'] !== 'string' || variant['talla'].length < 1 || variant['talla'].length > 30
      || typeof variant['color'] !== 'string' || variant['color'].length < 1 || variant['color'].length > 60) {
      throw invalid();
    }
    return {
      id: variant['id'] as number,
      producto_slug: variant['producto_slug'] as string,
      talla: variant['talla'] as string,
      color: variant['color'] as string,
    };
  });
  if (variants && new Set(variants.map(v => v.id)).size !== variants.length) throw invalid();
  const storedBranches = snapshot['branches'];
  if (storedBranches !== undefined && (!Array.isArray(storedBranches) || storedBranches.length > 1000)) throw invalid();
  const branches = storedBranches === undefined ? undefined : (storedBranches as unknown[]).map(item => {
    if (!item || typeof item !== 'object') throw invalid();
    const branch = item as Record<string, unknown>;
    if (!Number.isSafeInteger(branch['id']) || (branch['id'] as number) < 1
      || typeof branch['nombre'] !== 'string' || !branch['nombre'].trim() || branch['nombre'].length > 120) throw invalid();
    return { id: branch['id'] as number, nombre: branch['nombre'] as string };
  });
  if (branches && new Set(branches.map(b => b.id)).size !== branches.length) throw invalid();
  return { schemaVersion: 1, scope: snapshot['scope'] as string, downloadedAt,
    total: total as number, products,
    ...(variants === undefined ? {} : { variants }),
    ...(branches === undefined ? {} : { branches }) };
}
