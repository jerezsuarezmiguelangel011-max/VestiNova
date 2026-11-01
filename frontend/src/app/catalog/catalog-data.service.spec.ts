import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { firstValueFrom } from 'rxjs';
import { CatalogDataService } from './catalog-data.service';
import { CatalogList, CatalogProduct, CatalogSnapshot } from './catalog.models';
import { CatalogOfflineStoreService } from './catalog-offline-store.service';

const ENDPOINT = '/api/catalogo/productos';
const PRODUCT: CatalogProduct = {
  id: 7, nombre: 'Camisa de lino', slug: 'camisa-de-lino', descripcion: 'Lino natural.',
  precio: '149.90', moneda: 'BOB', imagen_url: null, activo: true,
  creado_en: '2026-10-25T12:00:00Z', actualizado_en: '2026-10-25T12:00:00Z',
};
const PREVIOUS: CatalogSnapshot = {
  schemaVersion: 1, scope: 'public-catalog', downloadedAt: '2026-10-25T12:30:00.000Z',
  total: 1, products: [PRODUCT],
};

function products(count: number): CatalogProduct[] {
  return Array.from({ length: count }, (_, index) => {
    const id = count - index;
    return { ...PRODUCT, id, nombre: `Prenda ${id}`, slug: `prenda-${id}` };
  });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}

describe('Descarga y consulta del catálogo público', () => {
  let http: HttpTestingController;
  let data: CatalogDataService;
  let persisted: CatalogSnapshot | null;
  const local = {
    read: vi.fn<() => Promise<CatalogSnapshot | null>>(),
    replace: vi.fn<(snapshot: CatalogSnapshot) => Promise<void>>(),
  };

  beforeEach(() => {
    persisted = structuredClone(PREVIOUS);
    local.read.mockReset().mockImplementation(async () => persisted);
    local.replace.mockReset().mockImplementation(async snapshot => { persisted = structuredClone(snapshot); });
    TestBed.configureTestingModule({ providers: [
      provideHttpClient(), provideHttpClientTesting(),
      { provide: CatalogOfflineStoreService, useValue: local },
    ] });
    http = TestBed.inject(HttpTestingController);
    data = TestBed.inject(CatalogDataService);
  });
  afterEach(() => { http.verify(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  function downloadRequest(offset: number) {
    const request = http.expectOne(request => request.url === ENDPOINT);
    expect(request.request.method).toBe('GET');
    expect(request.request.params.get('limit')).toBe('100');
    expect(request.request.params.get('offset')).toBe(String(offset));
    expect(request.request.params.has('q')).toBe(false);
    expect(request.request.headers.has('Authorization')).toBe(false);
    return request;
  }

  async function flushPage(items: CatalogProduct[], total: number, offset: number): Promise<void> {
    downloadRequest(offset).flush({ items, total, limit: 100, offset });
    // The next page starts after firstValueFrom resolves, without timers or another subscription.
    await Promise.resolve();
  }

  function listRequest() {
    return http.expectOne(request => request.url === ENDPOINT);
  }

  it('detecta una copia modificada desde el registro sin descargar ni sobrescribirla', async () => {
    expect(await data.download(null)).toBe(false);
    expect(data.downloadConflict()).toBe(true);
    expect(data.downloadError()).toContain('cambió');
    expect(local.replace).not.toHaveBeenCalled();
    expect(persisted).toEqual(PREVIOUS);
    http.expectNone(request => request.url === ENDPOINT);
  });

  it('actualiza cuando coincide la fecha base y limpia un conflicto previo', async () => {
    expect(await data.download(null)).toBe(false);
    const pending = data.download(PREVIOUS.downloadedAt);
    await Promise.resolve();
    await flushPage([PRODUCT], 1, 0);
    expect(await pending).toBe(true);
    expect(data.downloadConflict()).toBe(false);
    expect(local.replace).toHaveBeenCalledTimes(1);
    expect(persisted?.products).toEqual([PRODUCT]);
  });

  it('comprueba la fecha base dentro del bloqueo de descarga compartido con CU14', async () => {
    const request = vi.fn(async (
      _name: string, _options: unknown, callback: (lock: object | null) => Promise<boolean>,
    ) => {
      persisted = { ...PREVIOUS, downloadedAt: '2026-10-25T13:00:00.000Z' };
      return callback({});
    });
    vi.stubGlobal('navigator', { locks: { request } });
    expect(await data.download(PREVIOUS.downloadedAt)).toBe(false);
    expect(request).toHaveBeenCalledWith(
      'vestinova-public-catalog-download', { mode: 'exclusive', ifAvailable: true }, expect.any(Function),
    );
    expect(data.downloadConflict()).toBe(true);
    expect(local.replace).not.toHaveBeenCalled();
    http.expectNone(request => request.url === ENDPOINT);
  });

  it('descarga 205 prendas en tres páginas sin filtros y solo guarda al completar el recorrido', async () => {
    const all = products(205);
    const started = Date.now();
    const pending = data.download();
    expect(data.downloading()).toBe(true);
    await flushPage(all.slice(0, 100), 205, 0);
    expect(data.progress()).toEqual({ received: 100, total: 205 });
    expect(local.replace).not.toHaveBeenCalled();
    await flushPage(all.slice(100, 200), 205, 100);
    expect(data.progress()).toEqual({ received: 200, total: 205 });
    expect(local.replace).not.toHaveBeenCalled();
    await flushPage(all.slice(200), 205, 200);
    expect(await pending).toBe(true);
    expect(local.replace).toHaveBeenCalledTimes(1);
    const snapshot = local.replace.mock.calls[0][0];
    expect(snapshot).toEqual({
      schemaVersion: 1, scope: 'public-catalog', downloadedAt: expect.any(String), total: 205, products: all,
    });
    expect(Date.parse(snapshot.downloadedAt)).toBeGreaterThanOrEqual(started);
    expect(Date.parse(snapshot.downloadedAt)).toBeLessThanOrEqual(Date.now());
    expect(data.saved()).toEqual({
      schemaVersion: 1, scope: 'public-catalog', downloadedAt: snapshot.downloadedAt, total: 205,
    });
    expect(data.downloading()).toBe(false);
    expect(data.progress()).toEqual({ received: 205, total: 205 });
    expect(data.revision()).toBe(1);
    expect(data.downloadError()).toBeNull();
    expect(data.downloadNotice()).toContain('205');
    expect(local.read).not.toHaveBeenCalled();
  });

  it('ignora un segundo clic mientras sigue pendiente la descarga original', async () => {
    const first = data.download();
    expect(await data.download()).toBe(false);
    const request = downloadRequest(0);
    http.expectNone(request => request.url === ENDPOINT);
    expect(data.downloading()).toBe(true);
    expect(local.replace).not.toHaveBeenCalled();
    request.flush({ items: [PRODUCT], total: 1, limit: 100, offset: 0 });
    expect(await first).toBe(true);
    expect(local.replace).toHaveBeenCalledTimes(1);
    expect(data.downloading()).toBe(false);
  });

  it('no inicia HTTP si otra pestaña mantiene el bloqueo compartido de descarga', async () => {
    const request = vi.fn(async (
      _name: string, _options: unknown, callback: (lock: object | null) => Promise<boolean>,
    ) => callback(null));
    vi.stubGlobal('navigator', { locks: { request } });
    expect(await data.download()).toBe(false);
    expect(request).toHaveBeenCalledWith(
      'vestinova-public-catalog-download', { mode: 'exclusive', ifAvailable: true }, expect.any(Function),
    );
    expect(data.downloadError()).toContain('pestaña');
    expect(data.downloading()).toBe(false);
    expect(local.replace).not.toHaveBeenCalled();
    http.expectNone(request => request.url === ENDPOINT);
  });

  it('mantiene el bloqueo entre instancias durante HTTP y hasta confirmar la escritura', async () => {
    let held = false;
    const request = vi.fn(async (
      name: string, _options: unknown, callback: (lock: object | null) => Promise<boolean>,
    ) => {
      if (held) return callback(null);
      held = true;
      try { return await callback({ name, mode: 'exclusive' }); }
      finally { held = false; }
    });
    vi.stubGlobal('navigator', { locks: { request } });
    const commit = deferred<void>();
    local.replace.mockImplementationOnce(async snapshot => {
      expect(held).toBe(true);
      await commit.promise;
      persisted = structuredClone(snapshot);
    });
    const pending = data.download();
    expect(held).toBe(true);
    await flushPage([PRODUCT], 1, 0);
    expect(local.replace).toHaveBeenCalledTimes(1);
    expect(held).toBe(true);
    const otherTab = TestBed.runInInjectionContext(() => new CatalogDataService());
    expect(await otherTab.download()).toBe(false);
    expect(otherTab.downloadError()).toContain('pestaña');
    http.expectNone(request => request.url === ENDPOINT);
    expect(held).toBe(true);
    commit.resolve(undefined);
    expect(await pending).toBe(true);
    expect(held).toBe(false);
    expect(request).toHaveBeenCalledTimes(2);
  });

  it.each([0, 401, 403, 503])('conserva la copia anterior si la segunda página falla con estado %s', async status => {
    await data.refreshSavedStatus();
    const saved = data.saved();
    local.read.mockClear();
    const all = products(205);
    const pending = data.download();
    await flushPage(all.slice(0, 100), 205, 0);
    const second = downloadRequest(100);
    if (status === 0) second.error(new ProgressEvent('error'));
    else second.flush({ detail: 'Información interna que no debe mostrarse' }, { status, statusText: 'Error' });
    expect(await pending).toBe(false);
    expect(local.replace).not.toHaveBeenCalled();
    expect(local.read).not.toHaveBeenCalled();
    expect(persisted).toEqual(PREVIOUS);
    expect(data.saved()).toEqual(saved);
    expect(data.revision()).toBe(0);
    expect(data.downloading()).toBe(false);
    expect(data.downloadNotice()).toBeNull();
    expect(data.downloadError()).toContain('copia anterior se conserva');
    expect(data.downloadError()).not.toContain('Información interna');
  });

  it.each<[string, Record<string, unknown>]>([
    ['total negativo', { items: [], total: -1, limit: 100, offset: 0 }],
    ['total no entero', { items: [], total: 0.5, limit: 100, offset: 0 }],
    ['página incompleta', { items: products(99), total: 205, limit: 100, offset: 0 }],
    ['IDs repetidos', { items: [products(2)[0], { ...products(2)[1], id: 2 }], total: 2, limit: 100, offset: 0 }],
    ['slugs repetidos', { items: [products(2)[0], { ...products(2)[1], slug: 'prenda-2' }], total: 2, limit: 100, offset: 0 }],
    ['orden distinto del contrato', { items: products(2).reverse(), total: 2, limit: 100, offset: 0 }],
    ['producto sin publicar', { items: [{ ...PRODUCT, activo: false }], total: 1, limit: 100, offset: 0 }],
    ['precio numérico en vez de decimal exacto', { items: [{ ...PRODUCT, precio: 149.9 }], total: 1, limit: 100, offset: 0 }],
  ])('rechaza una descarga con %s sin escribir una copia parcial', async (_, body) => {
    const pending = data.download();
    downloadRequest(0).flush(body);
    expect(await pending).toBe(false);
    expect(local.replace).not.toHaveBeenCalled();
    expect(persisted).toEqual(PREVIOUS);
    expect(data.downloadError()).toContain('verificar el catálogo completo');
    expect(data.downloading()).toBe(false);
    http.expectNone(request => request.url === ENDPOINT);
  });

  it('descarta las páginas recibidas si cambia el total a mitad de la descarga', async () => {
    const all = products(205);
    const pending = data.download();
    await flushPage(all.slice(0, 100), 205, 0);
    downloadRequest(100).flush({ items: all.slice(100, 200), total: 206, limit: 100, offset: 100 });
    expect(await pending).toBe(false);
    expect(local.replace).not.toHaveBeenCalled();
    expect(persisted).toEqual(PREVIOUS);
    expect(data.downloadError()).toContain('cambiado durante la descarga');
    http.expectNone(request => request.url === ENDPOINT);
  });

  it('conserva copia y metadatos previos si falla el almacenamiento después de descargar', async () => {
    await data.refreshSavedStatus();
    const saved = data.saved();
    local.replace.mockRejectedValueOnce(new DOMException('Sin espacio', 'QuotaExceededError'));
    const pending = data.download();
    await flushPage([PRODUCT], 1, 0);
    expect(await pending).toBe(false);
    expect(persisted).toEqual(PREVIOUS);
    expect(data.saved()).toEqual(saved);
    expect(data.revision()).toBe(0);
    expect(data.downloadNotice()).toBeNull();
    expect(data.downloadError()).toContain('almacenamiento');
    expect(data.downloading()).toBe(false);
  });

  it('guarda únicamente campos públicos y conserva el precio como cadena exacta', async () => {
    const pending = data.download();
    downloadRequest(0).flush({
      items: [{ ...PRODUCT, precio: '99999999.99', token: 'secreto', password_hash: 'secreto', administrador: { correo: 'privado' } }],
      total: 1, limit: 100, offset: 0, access_token: 'secreto', headers: { Authorization: 'Bearer secreto' },
    });
    expect(await pending).toBe(true);
    const snapshot = local.replace.mock.calls[0][0];
    expect(Object.keys(snapshot).sort()).toEqual(['downloadedAt', 'products', 'schemaVersion', 'scope', 'total']);
    expect(snapshot.products).toEqual([{ ...PRODUCT, precio: '99999999.99' }]);
    expect(JSON.stringify(snapshot)).not.toContain('secreto');
  });

  it('acepta un catálogo vacío descargado y lo distingue de la ausencia de copia al consultar offline', async () => {
    const pending = data.download();
    await flushPage([], 0, 0);
    expect(await pending).toBe(true);
    expect(persisted).toMatchObject({ total: 0, products: [] });
    expect(data.saved()?.total).toBe(0);
    const offline = firstValueFrom(data.list({ limit: 20, offset: 0 }));
    listRequest().error(new ProgressEvent('error'));
    expect(await offline).toEqual({
      data: { items: [], total: 0, limit: 20, offset: 0 }, source: 'local', downloadedAt: data.saved()?.downloadedAt,
    });
  });

  it('consulta listado y detalle online sin leer ni actualizar la copia local', async () => {
    const page: CatalogList = { items: [PRODUCT], total: 1, limit: 20, offset: 0 };
    const listing = firstValueFrom(data.list({ q: 'lino', limit: 20, offset: 0 }));
    listRequest().flush(page);
    expect(await listing).toEqual({ data: page, source: 'network', downloadedAt: null });
    const detail = firstValueFrom(data.get(PRODUCT.slug));
    http.expectOne(`${ENDPOINT}/${PRODUCT.slug}`).flush(PRODUCT);
    expect(await detail).toEqual({ data: PRODUCT, source: 'network', downloadedAt: null });
    expect(local.read).not.toHaveBeenCalled();
    expect(local.replace).not.toHaveBeenCalled();
    expect(persisted).toEqual(PREVIOUS);
  });

  it('busca y pagina la copia offline por nombre, ordenando por ID descendente y mostrando su fecha', async () => {
    const matching = [
      { ...PRODUCT, id: 2, slug: 'camisa-lino', nombre: 'Camisa de lino' },
      { ...PRODUCT, id: 9, slug: 'lino-azul', nombre: 'LINO azul' },
      { ...PRODUCT, id: 4, slug: 'camisa-algodon', nombre: 'Camisa de algodón' },
      { ...PRODUCT, id: 1, slug: 'falda-lino', nombre: 'Falda de lino' },
    ];
    persisted = { ...PREVIOUS, total: matching.length, products: matching };
    const pending = firstValueFrom(data.list({ q: '  LiNo ', limit: 1, offset: 1 }));
    listRequest().error(new ProgressEvent('error'));
    expect(await pending).toEqual({
      data: { items: [matching[0]], total: 3, limit: 1, offset: 1 },
      source: 'local', downloadedAt: PREVIOUS.downloadedAt,
    });
    expect(local.read).toHaveBeenCalledTimes(1);
    expect(local.replace).not.toHaveBeenCalled();
    expect(data.saved()).toEqual({
      schemaVersion: 1, scope: 'public-catalog', downloadedAt: PREVIOUS.downloadedAt, total: 4,
    });
  });

  it('obtiene el detalle offline de la copia y conserva su procedencia y fecha', async () => {
    local.read.mockRejectedValueOnce(new Error('Fallo temporal de almacenamiento'));
    await data.refreshSavedStatus();
    expect(data.storageError()).not.toBeNull();
    local.read.mockClear();
    const pending = firstValueFrom(data.get(PRODUCT.slug));
    http.expectOne(`${ENDPOINT}/${PRODUCT.slug}`).error(new ProgressEvent('error'));
    expect(await pending).toEqual({ data: PRODUCT, source: 'local', downloadedAt: PREVIOUS.downloadedAt });
    expect(local.read).toHaveBeenCalledTimes(1);
    expect(local.replace).not.toHaveBeenCalled();
    expect(data.storageError()).toBeNull();
  });

  it.each([401, 403, 404, 500, 503])('propaga estado HTTP %s en listado y detalle sin leer ni usar datos offline', async status => {
    const listing = firstValueFrom(data.list({ limit: 20, offset: 0 }));
    const listingRejection = expect(listing).rejects.toMatchObject({ status });
    listRequest().flush({ detail: 'Error del servidor' }, { status, statusText: 'Error' });
    await listingRejection;
    const detail = firstValueFrom(data.get(PRODUCT.slug));
    const detailRejection = expect(detail).rejects.toMatchObject({ status });
    http.expectOne(`${ENDPOINT}/${PRODUCT.slug}`).flush({ detail: 'Error del servidor' }, { status, statusText: 'Error' });
    await detailRejection;
    expect(local.read).not.toHaveBeenCalled();
    expect(local.replace).not.toHaveBeenCalled();
  });

  it.each([401, 403])('no permite eludir una denegación %s pasando después a modo sin conexión', async status => {
    const denied = firstValueFrom(data.get(PRODUCT.slug));
    const denial = expect(denied).rejects.toMatchObject({ status });
    http.expectOne(`${ENDPOINT}/${PRODUCT.slug}`).flush({}, { status, statusText: 'Denied' });
    await denial;
    const offline = firstValueFrom(data.list({ limit: 20, offset: 0 }));
    const blocked = expect(offline).rejects.toMatchObject({ status });
    listRequest().error(new ProgressEvent('error'));
    await blocked;
    expect(local.read).not.toHaveBeenCalled();

    // A successful response proves that the public endpoint is available again.
    const restored = firstValueFrom(data.get(PRODUCT.slug));
    http.expectOne(`${ENDPOINT}/${PRODUCT.slug}`).flush(PRODUCT);
    await restored;
    const laterOffline = firstValueFrom(data.get(PRODUCT.slug));
    http.expectOne(`${ENDPOINT}/${PRODUCT.slug}`).error(new ProgressEvent('error'));
    expect((await laterOffline).source).toBe('local');
    expect(local.read).toHaveBeenCalledTimes(1);
  });

  it('rechaza una copia local cuya lectura termina después de una denegación concurrente', async () => {
    const reading = deferred<CatalogSnapshot | null>();
    local.read.mockReturnValueOnce(reading.promise);
    const offline = firstValueFrom(data.list({ limit: 20, offset: 0 }));
    const blocked = expect(offline).rejects.toMatchObject({ status: 403 });
    listRequest().error(new ProgressEvent('error'));
    expect(local.read).toHaveBeenCalledTimes(1);
    const denied = firstValueFrom(data.get(PRODUCT.slug));
    const denial = expect(denied).rejects.toMatchObject({ status: 403 });
    http.expectOne(`${ENDPOINT}/${PRODUCT.slug}`).flush({}, { status: 403, statusText: 'Denied' });
    await denial;
    reading.resolve(PREVIOUS);
    await blocked;
    expect(data.saved()).toBeNull();
    expect(local.replace).not.toHaveBeenCalled();
  });

  it('no deja que un 200 antiguo borre una denegación nueva y captura la revisión al suscribirse', async () => {
    const old = firstValueFrom(data.get(PRODUCT.slug));
    const oldBlocked = expect(old).rejects.toMatchObject({ status: 401 });
    const oldRequest = http.expectOne(`${ENDPOINT}/${PRODUCT.slug}`);
    const preparedBeforeDenial = data.get(PRODUCT.slug);
    const denied = firstValueFrom(data.list({ limit: 20, offset: 0 }));
    const denial = expect(denied).rejects.toMatchObject({ status: 401 });
    listRequest().flush({}, { status: 401, statusText: 'Denied' });
    await denial;
    oldRequest.flush(PRODUCT);
    await oldBlocked;
    const offline = firstValueFrom(data.get(PRODUCT.slug));
    const stillBlocked = expect(offline).rejects.toMatchObject({ status: 401 });
    http.expectOne(`${ENDPOINT}/${PRODUCT.slug}`).error(new ProgressEvent('error'));
    await stillBlocked;
    expect(local.read).not.toHaveBeenCalled();

    const authorized = firstValueFrom(preparedBeforeDenial);
    http.expectOne(`${ENDPOINT}/${PRODUCT.slug}`).flush(PRODUCT);
    expect((await authorized).source).toBe('network');
    const restored = firstValueFrom(data.get(PRODUCT.slug));
    http.expectOne(`${ENDPOINT}/${PRODUCT.slug}`).error(new ProgressEvent('error'));
    expect((await restored).source).toBe('local');
  });

  it('no guarda una descarga si otra consulta deniega acceso antes de comenzar la escritura', async () => {
    const pending = data.download();
    const page = downloadRequest(0);
    const denied = firstValueFrom(data.get(PRODUCT.slug));
    const denial = expect(denied).rejects.toMatchObject({ status: 403 });
    http.expectOne(`${ENDPOINT}/${PRODUCT.slug}`).flush({}, { status: 403, statusText: 'Denied' });
    await denial;
    page.flush({ items: [PRODUCT], total: 1, limit: 100, offset: 0 });
    expect(await pending).toBe(false);
    expect(local.replace).not.toHaveBeenCalled();
    expect(persisted).toEqual(PREVIOUS);
    expect(data.downloadError()).toContain('autorización');
  });

  it('conserva una denegación recibida durante el guardado sin fingir que una escritura confirmada se revirtió', async () => {
    const commit = deferred<void>();
    local.replace.mockImplementationOnce(async snapshot => {
      await commit.promise;
      persisted = structuredClone(snapshot);
    });
    const pending = data.download();
    await flushPage([PRODUCT], 1, 0);
    expect(local.replace).toHaveBeenCalledTimes(1);
    const denied = firstValueFrom(data.get(PRODUCT.slug));
    const denial = expect(denied).rejects.toMatchObject({ status: 403 });
    http.expectOne(`${ENDPOINT}/${PRODUCT.slug}`).flush({}, { status: 403, statusText: 'Denied' });
    await denial;
    commit.resolve(undefined);
    expect(await pending).toBe(true);
    expect(data.saved()?.downloadedAt).toBe(persisted?.downloadedAt);
    expect(data.revision()).toBe(1);
    expect(data.downloadError()).toBeNull();
    const offline = firstValueFrom(data.list({ limit: 20, offset: 0 }));
    const blocked = expect(offline).rejects.toMatchObject({ status: 403 });
    listRequest().error(new ProgressEvent('error'));
    await blocked;
    expect(local.read).not.toHaveBeenCalled();
  });

  it('explica que no existe una copia cuando se pierde la conexión antes de descargar', async () => {
    persisted = null;
    const pending = firstValueFrom(data.list({ limit: 20, offset: 0 }));
    const failure = expect(pending).rejects.toMatchObject({ name: 'CatalogLocalError', reason: 'no-copy', downloadedAt: null });
    listRequest().error(new ProgressEvent('error'));
    await failure;
    expect(local.replace).not.toHaveBeenCalled();
  });

  it('distingue una prenda ausente de la copia de un 404 del servidor e incluye la fecha guardada', async () => {
    const pending = firstValueFrom(data.get('prenda-no-descargada'));
    const failure = expect(pending).rejects.toMatchObject({
      name: 'CatalogLocalError', reason: 'missing-product', downloadedAt: PREVIOUS.downloadedAt,
    });
    http.expectOne(`${ENDPOINT}/prenda-no-descargada`).error(new ProgressEvent('error'));
    await failure;
    expect(local.read).toHaveBeenCalledTimes(1);
  });

  it('convierte un fallo de IndexedDB en un error local controlado sin confundirlo con copia vacía', async () => {
    local.read.mockRejectedValueOnce(new DOMException('Bloqueado', 'SecurityError'));
    const pending = firstValueFrom(data.list({ limit: 20, offset: 0 }));
    const failure = expect(pending).rejects.toMatchObject({ name: 'CatalogLocalError', reason: 'storage' });
    listRequest().error(new ProgressEvent('error'));
    await failure;
    expect(local.replace).not.toHaveBeenCalled();
  });

  it('refresca solo metadatos, informa un fallo de lectura y elimina el aviso al recuperarse', async () => {
    await data.refreshSavedStatus();
    const metadata = {
      schemaVersion: 1, scope: 'public-catalog', downloadedAt: PREVIOUS.downloadedAt, total: 1,
    };
    expect(data.saved()).toEqual(metadata);
    expect(data.storageError()).toBeNull();
    local.read.mockRejectedValueOnce(new Error('Fallo interno'));
    await data.refreshSavedStatus();
    expect(data.saved()).toEqual(metadata);
    expect(data.storageError()).toContain('almacenamiento');
    expect(data.storageError()).not.toContain('Fallo interno');
    persisted = null;
    await data.refreshSavedStatus();
    expect(data.saved()).toBeNull();
    expect(data.storageError()).toBeNull();
    expect(local.replace).not.toHaveBeenCalled();
    http.expectNone(request => request.url === ENDPOINT);
  });
});
