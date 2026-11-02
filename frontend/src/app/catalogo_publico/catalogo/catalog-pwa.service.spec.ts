import { TestBed } from '@angular/core/testing';
import { SwUpdate, type VersionEvent } from '@angular/service-worker';
import { Subject } from 'rxjs';
import { CATALOG_PWA_ENV, CatalogPwaService, type CatalogPwaEnvironment } from './catalog-pwa.service';

const ORIGIN = 'https://vestinova.test';
const URLS = ['/index.html', '/main.js', '/chunk-detail.js', '/styles.css', '/icons/vn.svg', '/manifest.webmanifest'];
const MANIFEST = { index: '/index.html', assetGroups: [{ installMode: 'prefetch', urls: URLS }] };

describe('Preparación comprobada del shell público PWA', () => {
  function setup(options: { disabled?: boolean; noWorkerProvider?: boolean; environment?: Partial<CatalogPwaEnvironment> } = {}) {
    let time = 0;
    const match = vi.fn<CacheStorage['match']>().mockResolvedValue(undefined);
    const fetch = vi.fn<(url: string, options: RequestInit) => Promise<Response>>()
      .mockResolvedValue(new Response(JSON.stringify(MANIFEST)));
    const wait = vi.fn(async (milliseconds: number) => { time += milliseconds; });
    const environment: CatalogPwaEnvironment = {
      origin: ORIGIN, fetch, caches: { match }, worker: { controller: null },
      online: () => true, now: () => time, wait, timeoutMs: 200,
      ...options.environment,
    };
    const versionUpdates = new Subject<VersionEvent>();
    const unrecoverable = new Subject<{ reason: string }>();
    const updates = {
      isEnabled: !options.disabled,
      checkForUpdate: vi.fn<() => Promise<boolean>>().mockResolvedValue(false),
      versionUpdates, unrecoverable,
    };
    TestBed.configureTestingModule({ providers: [
      { provide: CATALOG_PWA_ENV, useValue: environment },
      ...(options.noWorkerProvider ? [] : [{ provide: SwUpdate, useValue: updates }]),
    ] });
    return { service: TestBed.inject(CatalogPwaService), environment, match, fetch, wait, updates };
  }

  it('no confirma preparación cuando checkForUpdate devuelve false y falta un recurso precargado', async () => {
    const { service, match, environment, updates } = setup();
    match.mockImplementation(async request => String(request).endsWith('/chunk-detail.js') ? undefined : new Response('shell'));
    expect(await service.prepare()).toBe('error');
    expect(updates.checkForUpdate).toHaveBeenCalledExactlyOnceWith();
    expect(match).toHaveBeenCalledWith(`${ORIGIN}/chunk-detail.js`);
    expect(environment.now()).toBe(200);
  });

  it('confirma preparación únicamente cuando índice y todos los recursos prefetch ya están guardados', async () => {
    const { service, match, fetch } = setup();
    match.mockImplementation(async () => new Response('shell'));
    expect(await service.prepare()).toBe('ready');
    expect(fetch).toHaveBeenCalledExactlyOnceWith(`${ORIGIN}/ngsw.json`, {
      cache: 'no-store', headers: { 'ngsw-bypass': 'true' },
    });
    expect(match.mock.calls.map(call => call[0])).toEqual(URLS.map(url => `${ORIGIN}${url}`));
  });

  it('espera la precarga dentro del plazo sin usar un bucle de espera real en la prueba', async () => {
    const { service, match, wait, environment } = setup();
    match.mockImplementation(async () => environment.now() >= 100 ? new Response('shell') : undefined);
    expect(await service.prepare()).toBe('ready');
    expect(wait).toHaveBeenCalledExactlyOnceWith(100);
  });

  it('no confirma preparación si falla la consulta de manifest aunque el worker responda false', async () => {
    const { service, fetch, match } = setup();
    fetch.mockRejectedValue(new TypeError('Fallo de conexión'));
    expect(await service.prepare()).toBe('error');
    expect(match).not.toHaveBeenCalled();
  });

  it('no confirma preparación si el manifest responde con error HTTP', async () => {
    const { service, fetch, match } = setup();
    fetch.mockResolvedValue(new Response('', { status: 503 }));
    expect(await service.prepare()).toBe('error');
    expect(match).not.toHaveBeenCalled();
  });

  it('respeta un fallo de instalación aunque existan respuestas antiguas en caché', async () => {
    const { service, updates, match } = setup();
    match.mockImplementation(async () => new Response('shell'));
    updates.checkForUpdate.mockImplementation(async () => {
      updates.versionUpdates.next({ type: 'VERSION_INSTALLATION_FAILED', version: { hash: 'fallida' }, error: 'Bundle ausente' });
      return false;
    });
    expect(await service.prepare()).toBe('error');
    expect(match).not.toHaveBeenCalled();
  });

  it.each(['https://otro.test/chunk.js', '/api/catalogo/productos', '/admin/login'])('rechaza un recurso fuera del shell permitido: %s', async resource => {
    const { service, fetch, match } = setup();
    fetch.mockResolvedValue(new Response(JSON.stringify({
      ...MANIFEST, assetGroups: [{ installMode: 'prefetch', urls: [...URLS, resource] }],
    })));
    expect(await service.prepare()).toBe('error');
    expect(match).not.toHaveBeenCalled();
  });

  it('exige que el índice también pertenezca a los recursos prefetch', async () => {
    const { service, fetch, match } = setup();
    fetch.mockResolvedValue(new Response(JSON.stringify({
      ...MANIFEST, assetGroups: [{ installMode: 'prefetch', urls: URLS.filter(url => url !== '/index.html') }],
    })));
    expect(await service.prepare()).toBe('error');
    expect(match).not.toHaveBeenCalled();
  });

  it('informa estado no disponible cuando el worker está deshabilitado', async () => {
    const { service, updates, fetch } = setup({ disabled: true });
    expect(await service.prepare()).toBe('unavailable');
    expect(updates.checkForUpdate).not.toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('admite que no exista proveedor de SwUpdate', async () => {
    const { service, fetch } = setup({ noWorkerProvider: true });
    expect(await service.prepare()).toBe('unavailable');
    expect(fetch).not.toHaveBeenCalled();
  });

  it.each(['fetch', 'caches', 'worker'] as const)('informa estado no disponible si el navegador carece de %s', async missing => {
    const { service, updates } = setup({ environment: { [missing]: undefined } });
    expect(await service.prepare()).toBe('unavailable');
    expect(updates.checkForUpdate).not.toHaveBeenCalled();
  });

  it('distingue una aplicación controlada ya abierta offline de una nueva preparación', async () => {
    const { service, updates, fetch, match } = setup({ environment: {
      online: () => false, worker: { controller: {} as ServiceWorker },
    } });
    expect(await service.prepare()).toBe('offline');
    expect(updates.checkForUpdate).not.toHaveBeenCalled();
    expect(fetch).not.toHaveBeenCalled();
    expect(match).not.toHaveBeenCalled();
  });

  it('no promete apertura offline si está desconectada y no tiene worker controlador', async () => {
    const { service } = setup({ environment: { online: () => false } });
    expect(await service.prepare()).toBe('error');
  });
});
