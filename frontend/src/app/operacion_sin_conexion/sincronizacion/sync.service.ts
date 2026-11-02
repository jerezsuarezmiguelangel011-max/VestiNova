import { Injectable, InjectionToken, inject, signal } from '@angular/core';
import { CatalogDataService } from '../../catalogo_publico/catalogo/catalog-data.service';
import { CatalogOfflineStoreService } from '../../catalogo_publico/catalogo/catalog-offline-store.service';
import { SyncStore } from './sync-store.service';
import { SyncOperation } from './sync.models';

export const SYNC_LOCKS = new InjectionToken<Pick<LockManager, 'request'> | undefined>('VestiNova sync locks', {
  providedIn: 'root', factory: () => globalThis.navigator?.locks,
});

@Injectable({ providedIn: 'root' })
export class SyncService {
  private readonly store = inject(SyncStore);
  private readonly catalogStore = inject(CatalogOfflineStoreService);
  private readonly catalog = inject(CatalogDataService);
  private readonly locks = inject(SYNC_LOCKS);
  readonly operations = signal<SyncOperation[]>([]);
  readonly processing = signal(false);
  readonly enqueuing = signal(false);
  readonly error = signal<string | null>(null);

  async refresh(): Promise<void> {
    this.error.set(null);
    try { await this.load(); } catch { this.error.set('No se pudo leer la cola local. Comprueba el almacenamiento del navegador.'); }
  }

  async enqueueCatalogUpdate(): Promise<void> {
    if (this.enqueuing()) return;
    this.enqueuing.set(true);
    this.error.set(null);
    try {
      const snapshot = await this.catalogStore.read();
      const now = new Date().toISOString();
      await this.store.add({
        id: crypto.randomUUID(), scope: 'public-catalog', type: 'ACTUALIZAR_CATALOGO',
        expectedDownloadedAt: snapshot?.downloadedAt ?? null, state: 'PENDIENTE',
        createdAt: now, updatedAt: now, message: null,
      });
      await this.load();
    } catch { this.error.set('No se pudo completar el registro de la operación local. Comprueba el almacenamiento y consulta la cola antes de reintentar.'); }
    finally { this.enqueuing.set(false); }
  }

  async processPending(): Promise<void> {
    if (this.processing()) return;
    this.processing.set(true);
    this.error.set(null);
    try {
      if (this.locks) {
        await this.locks.request('vestinova-public-catalog-sync', { mode: 'exclusive', ifAvailable: true }, async lock => {
          if (!lock) { this.error.set('Otra pestaña está procesando la cola. Espera a que termine.'); return; }
          await this.run(true);
        });
      } else {
        await this.run(false);
      }
    } catch { this.error.set('No se pudo completar el procesamiento. Las operaciones se conservan en la cola para su revisión.'); }
    finally {
      try { await this.load(); } catch { this.error.set('No se pudo leer el estado final. Vuelve a consultar la cola local.'); }
      this.processing.set(false);
    }
  }

  async retry(id: string): Promise<void> {
    this.error.set(null);
    try { await this.store.retry(id); await this.load(); }
    catch { this.error.set('Solo se pueden reintentar operaciones con error. Un conflicto requiere revisar los datos y registrar una nueva actualización.'); }
  }

  private async run(recoverInterrupted: boolean): Promise<void> {
    if (recoverInterrupted) await this.store.recoverProcessing();
    const pending = (await this.store.list()).filter(operation => operation.state === 'PENDIENTE');
    for (const operation of pending) {
      const claimed = await this.store.claim(operation.id);
      if (!claimed) continue;
      await this.load();
      let success = false;
      let failedUnexpectedly = false;
      try { success = await this.catalog.download(claimed.expectedDownloadedAt); }
      catch { failedUnexpectedly = true; }
      if (success) {
        await this.store.finish(operation.id, 'SINCRONIZADA', 'Catálogo público actualizado y conservado localmente.');
      } else if (!failedUnexpectedly && this.catalog.downloadConflict()) {
        await this.store.finish(operation.id, 'CONFLICTO', 'La copia cambió desde que se registró la operación. Revísala y registra una nueva actualización; no se sobrescribieron datos.');
      } else {
        await this.store.finish(operation.id, 'ERROR', 'No se pudo actualizar el catálogo. La copia anterior se conserva; puedes volver a poner esta operación en pendiente.');
      }
      await this.load();
    }
  }

  private async load(): Promise<void> { this.operations.set(await this.store.list()); }
}
