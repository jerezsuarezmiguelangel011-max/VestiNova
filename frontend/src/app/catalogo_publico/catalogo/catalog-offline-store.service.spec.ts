import { TestBed } from '@angular/core/testing';
import { IDBFactory as FakeIDBFactory, IDBObjectStore as FakeIDBObjectStore } from 'fake-indexeddb';
import { CatalogProduct, CatalogSnapshot } from './catalog.models';
import { CatalogOfflineStoreService, IDB_FACTORY } from './catalog-offline-store.service';

const PRODUCT: CatalogProduct = {
  id: 7, nombre: 'Camisa de lino', slug: 'camisa-de-lino', descripcion: 'Lino natural.',
  precio: '149.90', moneda: 'BOB', imagen_url: null, activo: true,
  creado_en: '2026-10-25T12:00:00Z', actualizado_en: '2026-10-25T12:00:00Z',
};
const SNAPSHOT: CatalogSnapshot = {
  schemaVersion: 1, scope: 'public-catalog', downloadedAt: '2026-10-25T12:30:00.000Z',
  total: 1, products: [PRODUCT],
};

describe('Copia pública del catálogo en IndexedDB', () => {
  let factory: IDBFactory;
  let store: CatalogOfflineStoreService;

  function configure(value: IDBFactory | undefined = factory): CatalogOfflineStoreService {
    TestBed.configureTestingModule({ providers: [{ provide: IDB_FACTORY, useValue: value }] });
    return TestBed.inject(CatalogOfflineStoreService);
  }

  beforeEach(() => {
    factory = new FakeIDBFactory();
    store = configure();
  });
  afterEach(() => { vi.restoreAllMocks(); });

  async function rawRecord(value?: unknown): Promise<unknown> {
    const database = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = factory.open('vestinova-public-catalog', 1);
      request.onupgradeneeded = () => request.result.createObjectStore('snapshots', { keyPath: 'scope' });
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    return new Promise((resolve, reject) => {
      const transaction = database.transaction('snapshots', value === undefined ? 'readonly' : 'readwrite');
      const objectStore = transaction.objectStore('snapshots');
      let result: unknown;
      if (value === undefined) {
        const request = objectStore.get('public-catalog');
        request.onsuccess = () => { result = request.result; };
      } else objectStore.put(value);
      transaction.oncomplete = () => { database.close(); resolve(result); };
      transaction.onabort = () => { database.close(); reject(transaction.error); };
    });
  }

  it('distingue un navegador sin copia de un catálogo descargado vacío', async () => {
    expect(await store.read()).toBeNull();
    const empty: CatalogSnapshot = { ...SNAPSHOT, total: 0, products: [] };
    await store.replace(empty);
    expect(await store.read()).toEqual(empty);
  });

  it('persiste todos los datos y permite leerlos después de reabrir el servicio y la base', async () => {
    await store.replace(SNAPSHOT);
    TestBed.resetTestingModule();
    const reopened = configure();
    expect(await reopened.read()).toEqual(SNAPSHOT);
    expect(await rawRecord()).toEqual(SNAPSHOT);
  });

  it('reemplaza productos y metadatos completos sin mezclar la copia anterior', async () => {
    await store.replace(SNAPSHOT);
    const replacement: CatalogSnapshot = {
      ...SNAPSHOT, downloadedAt: '2026-10-25T15:00:00.000Z',
      products: [{ ...PRODUCT, id: 9, nombre: 'Falda plisada', slug: 'falda-plisada', precio: '180.00' }],
    };
    await store.replace(replacement);
    expect(await store.read()).toEqual(replacement);
    const empty: CatalogSnapshot = { ...replacement, total: 0, products: [], downloadedAt: '2026-10-25T16:00:00.000Z' };
    await store.replace(empty);
    expect(await store.read()).toEqual(empty);
    expect(await rawRecord()).toEqual(empty);
  });

  it.each<[string, unknown]>([
    ['versión desconocida', { ...SNAPSHOT, schemaVersion: 2 }],
    ['otro ámbito', { ...SNAPSHOT, scope: 'admin' }],
    ['fecha inválida', { ...SNAPSHOT, downloadedAt: 'fecha desconocida' }],
    ['fecha sin zona horaria', { ...SNAPSHOT, downloadedAt: '2026-10-25T12:30:00' }],
    ['total negativo', { ...SNAPSHOT, total: -1 }],
    ['total diferente de la cantidad', { ...SNAPSHOT, total: 2 }],
    ['productos ausentes', { ...SNAPSHOT, products: null }],
    ['IDs repetidos', { ...SNAPSHOT, total: 2, products: [PRODUCT, { ...PRODUCT, slug: 'otra-camisa' }] }],
    ['slugs repetidos', { ...SNAPSHOT, total: 2, products: [PRODUCT, { ...PRODUCT, id: 8 }] }],
    ['producto no publicado', { ...SNAPSHOT, products: [{ ...PRODUCT, activo: false }] }],
    ['moneda no admitida', { ...SNAPSHOT, products: [{ ...PRODUCT, moneda: 'USD' }] }],
    ['precio inválido', { ...SNAPSHOT, products: [{ ...PRODUCT, precio: '0.00' }] }],
    ['imagen con credenciales', { ...SNAPSHOT, products: [{ ...PRODUCT, imagen_url: 'https://usuario:clave@example.test/prenda.jpg' }] }],
  ])('rechaza %s antes de escribir y conserva la última copia', async (_, value) => {
    await store.replace(SNAPSHOT);
    await expect(store.replace(value as CatalogSnapshot)).rejects.toThrow();
    expect(await store.read()).toEqual(SNAPSHOT);
  });

  it('persiste exclusivamente la lista blanca pública y elimina campos de token o administrador', async () => {
    const contaminated = {
      ...SNAPSHOT, token: 'no-guardar', access_token: 'no-guardar', administrador: { correo: 'privado' },
      products: [{ ...PRODUCT, password_hash: 'no-guardar', token: 'no-guardar', empresa_secreta: 'no-guardar' }],
    };
    await store.replace(contaminated);
    expect(await rawRecord()).toEqual(SNAPSHOT);
    expect(await store.read()).toEqual(SNAPSHOT);
  });

  it('valida y limpia también los datos leídos directamente desde IndexedDB', async () => {
    await rawRecord({ ...SNAPSHOT, token: 'no-guardar', products: [{ ...PRODUCT, password_hash: 'no-guardar' }] });
    expect(await store.read()).toEqual(SNAPSHOT);
    await rawRecord({ ...SNAPSHOT, total: 2 });
    await expect(store.read()).rejects.toMatchObject({ reason: 'storage' });
    await rawRecord({ ...SNAPSHOT, products: [{ ...PRODUCT, activo: false }] });
    await expect(store.read()).rejects.toMatchObject({ reason: 'storage' });
  });

  it('espera la confirmación de la transacción y revierte una escritura exitosa si después se aborta', async () => {
    await store.replace(SNAPSHOT);
    const originalPut = FakeIDBObjectStore.prototype.put;
    vi.spyOn(FakeIDBObjectStore.prototype, 'put').mockImplementationOnce(function (this: IDBObjectStore, value: unknown, key?: IDBValidKey) {
      const request = originalPut.call(this, value, key);
      request.addEventListener('success', () => this.transaction.abort());
      return request;
    });
    await expect(store.replace({ ...SNAPSHOT, total: 0, products: [] })).rejects.toMatchObject({ reason: 'storage' });
    expect(await store.read()).toEqual(SNAPSHOT);
    expect(await rawRecord()).toEqual(SNAPSHOT);
  });

  it('devuelve un error controlado si IndexedDB no está disponible', async () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({ providers: [{ provide: IDB_FACTORY, useValue: undefined }] });
    const unavailable = TestBed.inject(CatalogOfflineStoreService);
    await expect(unavailable.read()).rejects.toMatchObject({ reason: 'storage' });
    await expect(unavailable.replace(SNAPSHOT)).rejects.toMatchObject({ reason: 'storage' });
  });

  it('controla un navegador que bloquea abrir IndexedDB y conserva los datos existentes', async () => {
    await store.replace(SNAPSHOT);
    const blocked = vi.spyOn(factory, 'open').mockImplementationOnce(() => {
      throw new DOMException('Almacenamiento bloqueado', 'SecurityError');
    });
    await expect(store.read()).rejects.toMatchObject({ reason: 'storage' });
    blocked.mockRestore();
    expect(await store.read()).toEqual(SNAPSHOT);
  });
});
