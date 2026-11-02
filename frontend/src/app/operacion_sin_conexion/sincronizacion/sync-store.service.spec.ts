import { TestBed } from '@angular/core/testing';
import { IDBFactory as FakeIDBFactory, IDBObjectStore as FakeIDBObjectStore } from 'fake-indexeddb';
import { IDB_FACTORY } from '../../catalogo_publico/catalogo/catalog-offline-store.service';
import { SyncOperation } from './sync.models';
import { SyncStore } from './sync-store.service';

const OPERATION: SyncOperation = {
  id: 'a1111111-b111-4111-8111-111111111111', scope: 'public-catalog', type: 'ACTUALIZAR_CATALOGO',
  expectedDownloadedAt: '2026-10-25T12:00:00.000Z', state: 'PENDIENTE',
  createdAt: '2026-10-25T13:00:00.000Z', updatedAt: '2026-10-25T13:00:00.000Z', message: null,
};
const SECOND_ID = '22222222-2222-4222-8222-222222222222';

describe('Cola pública de sincronización en IndexedDB', () => {
  let factory: IDBFactory;
  let store: SyncStore;

  function configure(): SyncStore {
    TestBed.configureTestingModule({ providers: [{ provide: IDB_FACTORY, useValue: factory }] });
    return TestBed.inject(SyncStore);
  }

  beforeEach(() => { factory = new FakeIDBFactory(); store = configure(); });
  afterEach(() => { vi.restoreAllMocks(); });

  async function rawOperations(value?: unknown): Promise<unknown[]> {
    const database = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = factory.open('vestinova-public-sync', 1);
      request.onupgradeneeded = () => request.result.createObjectStore('operations', { keyPath: 'id' });
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    return new Promise((resolve, reject) => {
      const transaction = database.transaction('operations', value === undefined ? 'readonly' : 'readwrite');
      const objectStore = transaction.objectStore('operations');
      let result: unknown[] = [];
      if (value === undefined) {
        const request = objectStore.getAll();
        request.onsuccess = () => { result = request.result; };
      } else objectStore.put(value);
      transaction.oncomplete = () => { database.close(); resolve(result); };
      transaction.onabort = () => { database.close(); reject(transaction.error); };
    });
  }

  it('persiste operaciones al reabrir y ordena por fecha de creación y UUID', async () => {
    expect(await store.list()).toEqual([]);
    const later = { ...OPERATION, id: SECOND_ID, createdAt: '2026-10-25T15:00:00.000Z' };
    const tied = { ...OPERATION, id: '00000000-0000-4000-8000-000000000000' };
    await store.add(later);
    await store.add(OPERATION);
    await store.add(tied);
    TestBed.resetTestingModule();
    const reopened = configure();
    expect(await reopened.list()).toEqual([tied, OPERATION, later]);
  });

  it('deduplica el UUID con el mismo payload aunque cambien las fechas del reenvío', async () => {
    await store.add(OPERATION);
    const claimed = await store.claim(OPERATION.id);
    await store.finish(OPERATION.id, 'SINCRONIZADA', 'Catálogo actualizado.');
    const saved = (await store.list())[0];
    const replay = { ...OPERATION, id: OPERATION.id.toUpperCase(), createdAt: '2027-01-01T00:00:00Z' };
    expect(await store.add(replay)).toEqual(saved);
    expect(await store.list()).toHaveLength(1);
    expect(claimed?.state).toBe('PROCESANDO');
  });

  it('rechaza un payload diferente con el mismo UUID sin sustituir el original', async () => {
    await store.add(OPERATION);
    await expect(store.add({ ...OPERATION, expectedDownloadedAt: null })).rejects.toThrow('UUID');
    expect(await store.list()).toEqual([OPERATION]);
  });

  it('solo un procesador puede reclamar atómicamente una operación pendiente', async () => {
    await store.add(OPERATION);
    const other = TestBed.runInInjectionContext(() => new SyncStore());
    const claims = await Promise.all([store.claim(OPERATION.id), other.claim(OPERATION.id)]);
    expect(claims.filter(Boolean)).toHaveLength(1);
    expect(claims.filter(value => value === null)).toHaveLength(1);
    expect((await store.list())[0]).toMatchObject({ id: OPERATION.id, state: 'PROCESANDO', message: null });
    expect(await store.claim(SECOND_ID)).toBeNull();
  });

  it.each(['SINCRONIZADA', 'CONFLICTO', 'ERROR'] as const)('finaliza una operación en %s conservando identidad y payload', async state => {
    await store.add(OPERATION);
    const started = Date.now();
    await store.claim(OPERATION.id);
    await store.finish(OPERATION.id, state, 'Resultado controlado.');
    const saved = (await store.list())[0];
    expect(saved).toEqual({ ...OPERATION, state, updatedAt: expect.any(String), message: 'Resultado controlado.' });
    expect(Date.parse(saved.updatedAt)).toBeGreaterThanOrEqual(started);
    await expect(store.finish(OPERATION.id, 'ERROR', 'Otro resultado')).rejects.toThrow();
    expect((await store.list())[0]).toEqual(saved);
  });

  it('solo ERROR puede reintentarse y conserva el UUID y el payload para reclamar de nuevo', async () => {
    await store.add(OPERATION);
    await expect(store.retry(OPERATION.id)).rejects.toThrow();
    await expect(store.finish(OPERATION.id, 'ERROR', 'No estaba procesando')).rejects.toThrow();
    await store.claim(OPERATION.id);
    await expect(store.retry(OPERATION.id)).rejects.toThrow();
    await store.finish(OPERATION.id, 'ERROR', 'Sin conexión.');
    await store.retry(OPERATION.id);
    expect((await store.list())[0]).toEqual({ ...OPERATION, updatedAt: expect.any(String), message: null });
    expect((await store.claim(OPERATION.id))?.state).toBe('PROCESANDO');
    await expect(store.retry(SECOND_ID)).rejects.toThrow();
  });

  it.each(['SINCRONIZADA', 'CONFLICTO'] as const)('no reabre automáticamente una operación %s', async state => {
    await store.add(OPERATION);
    await store.claim(OPERATION.id);
    await store.finish(OPERATION.id, state, null);
    const before = await store.list();
    await expect(store.retry(OPERATION.id)).rejects.toThrow();
    expect(await store.claim(OPERATION.id)).toBeNull();
    expect(await store.list()).toEqual(before);
  });

  it('recupera solo PROCESANDO y conserva operaciones pendientes y terminales sin eliminarlas', async () => {
    const completed = { ...OPERATION, id: SECOND_ID };
    const waiting = { ...OPERATION, id: '33333333-3333-4333-8333-333333333333' };
    await store.add(OPERATION);
    await store.add(completed);
    await store.add(waiting);
    await store.claim(OPERATION.id);
    await store.claim(completed.id);
    await store.finish(completed.id, 'SINCRONIZADA', 'Guardada.');
    const before = await store.list();
    await store.recoverProcessing();
    const after = await store.list();
    expect(after).toHaveLength(3);
    expect(after.find(item => item.id === OPERATION.id)).toMatchObject({ state: 'PENDIENTE', message: null });
    expect(after.find(item => item.id === completed.id)).toEqual(before.find(item => item.id === completed.id));
    expect(after.find(item => item.id === waiting.id)).toEqual(waiting);
  });

  it('espera txcomplete y revierte el estado si la escritura exitosa se aborta antes de confirmar', async () => {
    await store.add(OPERATION);
    const originalPut = FakeIDBObjectStore.prototype.put;
    vi.spyOn(FakeIDBObjectStore.prototype, 'put').mockImplementationOnce(function (this: IDBObjectStore, value: unknown, key?: IDBValidKey) {
      const request = originalPut.call(this, value, key);
      request.addEventListener('success', () => this.transaction.abort());
      return request;
    });
    await expect(store.claim(OPERATION.id)).rejects.toThrow('cola de sincronización');
    expect(await store.list()).toEqual([OPERATION]);
  });

  it('revierte todas las recuperaciones si falla una escritura de la transacción', async () => {
    await store.add(OPERATION);
    await store.add({ ...OPERATION, id: SECOND_ID });
    await store.claim(OPERATION.id);
    await store.claim(SECOND_ID);
    const before = await store.list();
    const originalPut = FakeIDBObjectStore.prototype.put;
    let writes = 0;
    vi.spyOn(FakeIDBObjectStore.prototype, 'put').mockImplementation(function (this: IDBObjectStore, value: unknown, key?: IDBValidKey) {
      const request = originalPut.call(this, value, key);
      if (++writes === 2) request.addEventListener('success', () => this.transaction.abort());
      return request;
    });
    await expect(store.recoverProcessing()).rejects.toThrow();
    expect(await store.list()).toEqual(before);
  });

  it('solo almacena la lista blanca de metadatos sin tokens, cabeceras ni cuerpos privados', async () => {
    const contaminated = {
      ...OPERATION, token: 'privado', Authorization: 'Bearer privado', body: { compra: 'privada' },
      empresa_id: 'privada', usuario: { correo: 'privado' },
    };
    expect(await store.add(contaminated)).toEqual(OPERATION);
    expect(await rawOperations()).toEqual([OPERATION]);
    await rawOperations({ ...OPERATION, token: 'privado', body: { password: 'privado' } });
    expect(await store.list()).toEqual([OPERATION]);
    await store.claim(OPERATION.id);
    expect(JSON.stringify(await rawOperations())).not.toContain('privado');
  });

  it.each<[string, Record<string, unknown>]>([
    ['UUID inválido', { id: 'no-uuid' }], ['otro ámbito', { scope: 'empresa' }],
    ['operación no implementada', { type: 'REGISTRAR_COMPRA' }], ['estado desconocido', { state: 'LISTA' }],
    ['fecha de creación inválida', { createdAt: 'hoy' }], ['fecha inexistente', { createdAt: '2026-02-30T10:00:00Z' }],
    ['fecha sin zona horaria', { updatedAt: '2026-10-25T13:00:00' }],
    ['versión de catálogo inválida', { expectedDownloadedAt: 'sin fecha' }],
    ['cuerpo privado como mensaje', { message: { token: 'privado' } }],
  ])('rechaza %s sin modificar operaciones existentes', async (_, changes) => {
    await store.add(OPERATION);
    await expect(store.add({ ...OPERATION, id: SECOND_ID, ...changes } as SyncOperation)).rejects.toThrow();
    expect(await store.list()).toEqual([OPERATION]);
  });

  it('rechaza datos corruptos o tipos privados al leer una cola alterada fuera del servicio', async () => {
    await rawOperations({ ...OPERATION, type: 'REGISTRAR_COMPRA' });
    await expect(store.list()).rejects.toThrow();
    await expect(store.claim(OPERATION.id)).rejects.toThrow();
  });

  it('rechaza estados finales y mensajes inválidos sin cambiar una operación en proceso', async () => {
    await store.add(OPERATION);
    await store.claim(OPERATION.id);
    const before = await store.list();
    await expect(store.finish(OPERATION.id, 'PENDIENTE' as 'ERROR', null)).rejects.toThrow();
    await expect(store.finish(OPERATION.id, 'ERROR', { token: 'privado' } as unknown as string)).rejects.toThrow();
    expect(await store.list()).toEqual(before);
  });

  it('no permite insertar una operación nueva ya finalizada o en proceso', async () => {
    await expect(store.add({ ...OPERATION, state: 'SINCRONIZADA' })).rejects.toThrow();
    await expect(store.add({ ...OPERATION, state: 'PROCESANDO' })).rejects.toThrow();
    expect(await store.list()).toEqual([]);
  });

  it('informa un error controlado cuando IndexedDB no está disponible', async () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({ providers: [{ provide: IDB_FACTORY, useValue: undefined }] });
    const unavailable = TestBed.inject(SyncStore);
    await expect(unavailable.list()).rejects.toThrow('cola de sincronización');
    await expect(unavailable.add(OPERATION)).rejects.toThrow('cola de sincronización');
  });
});
