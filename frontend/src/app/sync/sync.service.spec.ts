import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { IDBFactory as FakeIDBFactory } from 'fake-indexeddb';
import { CatalogDataService } from '../catalog/catalog-data.service';
import type { CatalogSnapshot } from '../catalog/catalog.models';
import { CatalogOfflineStoreService, IDB_FACTORY } from '../catalog/catalog-offline-store.service';
import type { SyncOperation } from './sync.models';
import { SyncService, SYNC_LOCKS } from './sync.service';
import { SyncStore } from './sync-store.service';

const FIRST_ID = '10000000-0000-4000-8000-000000000001';
const SECOND_ID = '10000000-0000-4000-8000-000000000002';
const SNAPSHOT: CatalogSnapshot = {
  schemaVersion: 1, scope: 'public-catalog', downloadedAt: '2026-10-25T12:00:00.000Z', total: 0, products: [],
};

function operation(id = FIRST_ID): SyncOperation {
  return {
    id, scope: 'public-catalog', type: 'ACTUALIZAR_CATALOGO', expectedDownloadedAt: SNAPSHOT.downloadedAt,
    state: 'PENDIENTE', createdAt: '2026-10-25T13:00:00.000Z', updatedAt: '2026-10-25T13:00:00.000Z', message: null,
  };
}

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  const promise = new Promise<T>(accept => { resolve = accept; });
  return { promise, resolve };
}

function webLocks(available: boolean) {
  const request = vi.fn(async (name: string, options: LockOptions, callback: LockGrantedCallback<void>) =>
    callback(available ? { name, mode: options.mode ?? 'exclusive' } as Lock : null));
  return { request, manager: { request: request as unknown as LockManager['request'] } };
}

describe('Coordinación de sincronización con cola real IndexedDB', () => {
  function setup(options: { locks?: Pick<LockManager, 'request'>; factory?: IDBFactory | null } = {}) {
    const factory = options.factory === null ? undefined : options.factory ?? new FakeIDBFactory();
    const catalog = {
      download: vi.fn<(expectedDownloadedAt?: string | null) => Promise<boolean>>().mockResolvedValue(true),
      downloadConflict: signal(false),
    };
    const catalogStore = { read: vi.fn<() => Promise<CatalogSnapshot | null>>().mockResolvedValue(SNAPSHOT) };
    TestBed.configureTestingModule({ providers: [
      { provide: IDB_FACTORY, useValue: factory },
      { provide: SYNC_LOCKS, useValue: options.locks },
      { provide: CatalogDataService, useValue: catalog },
      { provide: CatalogOfflineStoreService, useValue: catalogStore },
    ] });
    return { service: TestBed.inject(SyncService), store: TestBed.inject(SyncStore), catalog, catalogStore };
  }

  afterEach(() => { vi.restoreAllMocks(); });

  it('registra offline una operación pública persistida sin descargar ni procesar el catálogo', async () => {
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false);
    const { service, store, catalog, catalogStore } = setup();
    await service.enqueueCatalogUpdate();
    const saved = await store.list();
    expect(saved).toHaveLength(1);
    expect(saved[0]).toEqual({
      id: expect.any(String), scope: 'public-catalog', type: 'ACTUALIZAR_CATALOGO',
      expectedDownloadedAt: SNAPSHOT.downloadedAt, state: 'PENDIENTE',
      createdAt: expect.any(String), updatedAt: saved[0].createdAt, message: null,
    });
    expect(saved[0].id).toMatch(/^[0-9a-f-]{36}$/);
    expect(service.operations()).toEqual(saved);
    expect(service.enqueuing()).toBe(false);
    expect(service.error()).toBeNull();
    expect(catalogStore.read).toHaveBeenCalledExactlyOnceWith();
    expect(catalog.download).not.toHaveBeenCalled();
  });

  it('registra la ausencia de copia previa sin inventar una fecha de catálogo', async () => {
    const { service, store, catalogStore } = setup();
    catalogStore.read.mockResolvedValue(null);
    await service.enqueueCatalogUpdate();
    expect((await store.list())[0]).toMatchObject({ expectedDownloadedAt: null, state: 'PENDIENTE' });
  });

  it('ignora otro registro mientras sigue pendiente la lectura inicial de la copia', async () => {
    const { service, store, catalogStore } = setup();
    const read = deferred<CatalogSnapshot | null>();
    catalogStore.read.mockReturnValue(read.promise);
    const first = service.enqueueCatalogUpdate();
    expect(service.enqueuing()).toBe(true);
    await service.enqueueCatalogUpdate();
    expect(catalogStore.read).toHaveBeenCalledTimes(1);
    read.resolve(SNAPSHOT);
    await first;
    expect(await store.list()).toHaveLength(1);
    expect(service.enqueuing()).toBe(false);
  });

  it('procesa cada pendiente una sola vez y conserva las operaciones sincronizadas', async () => {
    const { service, store, catalog } = setup();
    await store.add(operation());
    await store.add(operation(SECOND_ID));
    await service.processPending();
    const completed = await store.list();
    expect(completed.map(item => item.state)).toEqual(['SINCRONIZADA', 'SINCRONIZADA']);
    expect(completed.map(item => item.id)).toEqual([FIRST_ID, SECOND_ID]);
    expect(catalog.download).toHaveBeenCalledTimes(2);
    expect(catalog.download).toHaveBeenNthCalledWith(1, SNAPSHOT.downloadedAt);
    expect(catalog.download).toHaveBeenNthCalledWith(2, SNAPSHOT.downloadedAt);
    await service.processPending();
    expect(catalog.download).toHaveBeenCalledTimes(2);
    expect(await store.list()).toEqual(completed);
    expect(service.operations()).toEqual(completed);
    expect(service.processing()).toBe(false);
  });

  it('devuelve un error a pendiente con el mismo UUID y procesa el reintento solo bajo petición', async () => {
    const { service, store, catalog } = setup();
    const original = operation();
    await store.add(original);
    catalog.download.mockResolvedValueOnce(false).mockResolvedValueOnce(true);
    await service.processPending();
    expect((await store.list())[0]).toMatchObject({ id: FIRST_ID, state: 'ERROR', expectedDownloadedAt: SNAPSHOT.downloadedAt });
    await service.retry(FIRST_ID);
    expect((await store.list())[0]).toEqual({ ...original, updatedAt: expect.any(String) });
    expect(catalog.download).toHaveBeenCalledTimes(1);
    await service.processPending();
    expect((await store.list())[0]).toMatchObject({ id: FIRST_ID, state: 'SINCRONIZADA', expectedDownloadedAt: SNAPSHOT.downloadedAt });
    expect(catalog.download).toHaveBeenCalledTimes(2);
  });

  it('conserva un conflicto sin forzar el reintento y exige registrar una nueva operación', async () => {
    const { service, store, catalog, catalogStore } = setup();
    await store.add(operation());
    catalog.downloadConflict.set(true);
    catalog.download.mockResolvedValue(false);
    await service.processPending();
    const conflicted = (await store.list())[0];
    expect(conflicted).toMatchObject({ id: FIRST_ID, state: 'CONFLICTO', expectedDownloadedAt: SNAPSHOT.downloadedAt });
    expect(conflicted.message).toContain('no se sobrescribieron datos');
    await service.retry(FIRST_ID);
    expect(service.error()).toContain('Un conflicto requiere revisar');
    await service.processPending();
    expect(catalog.download).toHaveBeenCalledTimes(1);
    expect(await store.list()).toEqual([conflicted]);

    const latest = { ...SNAPSHOT, downloadedAt: '2026-10-25T15:00:00.000Z' };
    catalogStore.read.mockResolvedValue(latest);
    await service.enqueueCatalogUpdate();
    const pending = (await store.list()).find(item => item.state === 'PENDIENTE');
    expect(pending).toMatchObject({ expectedDownloadedAt: latest.downloadedAt });
    expect(pending?.id).not.toBe(FIRST_ID);
    expect((await store.list()).find(item => item.id === FIRST_ID)).toEqual(conflicted);
    expect(catalog.download).toHaveBeenCalledTimes(1);
  });

  it('no duplica una descarga ante otro clic o un segundo coordinador sin Web Locks', async () => {
    const { service, store, catalog } = setup();
    await store.add(operation());
    const started = deferred<void>();
    const download = deferred<boolean>();
    catalog.download.mockImplementation(() => {
      started.resolve(undefined);
      return download.promise;
    });
    const first = service.processPending();
    await started.promise;
    expect(service.processing()).toBe(true);
    await service.processPending();
    const other = TestBed.runInInjectionContext(() => new SyncService());
    await other.processPending();
    expect(catalog.download).toHaveBeenCalledTimes(1);
    expect((await store.list())[0].state).toBe('PROCESANDO');
    download.resolve(true);
    await first;
    expect(service.processing()).toBe(false);
    expect((await store.list())[0].state).toBe('SINCRONIZADA');
  });

  it('no recupera una operación PROCESANDO sin tener un Web Lock exclusivo', async () => {
    const { service, store, catalog } = setup();
    await store.add(operation());
    await store.claim(FIRST_ID);
    const previous = await store.list();
    const recover = vi.spyOn(store, 'recoverProcessing');
    await service.processPending();
    expect(recover).not.toHaveBeenCalled();
    expect(catalog.download).not.toHaveBeenCalled();
    expect(await store.list()).toEqual(previous);
  });

  it('respeta un Web Lock ocupado sin recuperar operaciones ni iniciar descargas', async () => {
    const locks = webLocks(false);
    const { service, store, catalog } = setup({ locks: locks.manager });
    await store.add(operation());
    await store.claim(FIRST_ID);
    const previous = await store.list();
    const recover = vi.spyOn(store, 'recoverProcessing');
    await service.processPending();
    expect(locks.request).toHaveBeenCalledExactlyOnceWith('vestinova-public-catalog-sync', { mode: 'exclusive', ifAvailable: true }, expect.any(Function));
    expect(service.error()).toContain('Otra pestaña está procesando');
    expect(service.processing()).toBe(false);
    expect(recover).not.toHaveBeenCalled();
    expect(catalog.download).not.toHaveBeenCalled();
    expect(await store.list()).toEqual(previous);
  });

  it('recupera y procesa una operación interrumpida únicamente con el Web Lock concedido', async () => {
    const locks = webLocks(true);
    const { service, store, catalog } = setup({ locks: locks.manager });
    await store.add(operation());
    await store.claim(FIRST_ID);
    const recover = vi.spyOn(store, 'recoverProcessing');
    await service.processPending();
    expect(recover).toHaveBeenCalledExactlyOnceWith();
    expect(catalog.download).toHaveBeenCalledExactlyOnceWith(SNAPSHOT.downloadedAt);
    expect((await store.list())[0]).toMatchObject({ id: FIRST_ID, state: 'SINCRONIZADA' });
    expect(service.error()).toBeNull();
  });

  it('sanitiza fallos inesperados de descarga y no reutiliza una señal de conflicto anterior', async () => {
    const { service, store, catalog } = setup();
    await store.add(operation());
    catalog.downloadConflict.set(true);
    catalog.download.mockRejectedValue(new Error('SQL interno; Authorization: Bearer secreto'));
    await service.processPending();
    const saved = (await store.list())[0];
    expect(saved.state).toBe('ERROR');
    expect(saved.message).toContain('La copia anterior se conserva');
    expect(JSON.stringify(service.operations())).not.toContain('SQL interno');
    expect(JSON.stringify(service.operations())).not.toContain('secreto');
    expect(service.processing()).toBe(false);
  });

  it('conserva la cola y muestra un error controlado si falla la lectura previa al registro', async () => {
    const { service, store, catalog, catalogStore } = setup();
    await store.add(operation());
    catalogStore.read.mockRejectedValue(new Error('Detalle interno de IndexedDB con token privado'));
    await service.enqueueCatalogUpdate();
    expect(await store.list()).toEqual([operation()]);
    expect(service.error()).toContain('Comprueba el almacenamiento');
    expect(service.error()).not.toContain('token privado');
    expect(service.enqueuing()).toBe(false);
    expect(catalog.download).not.toHaveBeenCalled();
  });

  it('controla la ausencia de IndexedDB sin prometer registros o procesamiento exitosos', async () => {
    const { service, catalog } = setup({ factory: null });
    await service.refresh();
    expect(service.error()).toContain('No se pudo leer la cola local');
    await service.enqueueCatalogUpdate();
    expect(service.error()).toContain('No se pudo completar el registro');
    expect(service.operations()).toEqual([]);
    expect(service.enqueuing()).toBe(false);
    await service.processPending();
    expect(service.error()).toContain('No se pudo leer el estado final');
    expect(service.processing()).toBe(false);
    expect(catalog.download).not.toHaveBeenCalled();
  });
});
