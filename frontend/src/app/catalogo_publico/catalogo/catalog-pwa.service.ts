import { Injectable, InjectionToken, inject } from '@angular/core';
import { SwUpdate } from '@angular/service-worker';

export type CatalogPwaState = 'ready' | 'offline' | 'error' | 'unavailable';

export interface CatalogPwaEnvironment {
  origin: string;
  fetch?: (url: string, options: RequestInit) => Promise<Response>;
  caches?: Pick<CacheStorage, 'match'>;
  worker?: Pick<ServiceWorkerContainer, 'controller'>;
  online: () => boolean;
  now: () => number;
  wait: (milliseconds: number) => Promise<void>;
  timeoutMs: number;
}

export const CATALOG_PWA_ENV = new InjectionToken<CatalogPwaEnvironment>('VestiNova PWA environment', {
  providedIn: 'root',
  factory: () => {
    const clock = {
      now: () => Date.now(),
      wait: (milliseconds: number) => new Promise<void>(resolve => setTimeout(resolve, milliseconds)),
      timeoutMs: 8000,
    };
    try {
      return {
        ...clock,
        origin: globalThis.location?.origin ?? '',
        fetch: typeof globalThis.fetch === 'function' ? (url: string, options: RequestInit) => globalThis.fetch(url, options) : undefined,
        caches: globalThis.caches,
        worker: globalThis.navigator?.serviceWorker,
        online: () => globalThis.navigator?.onLine !== false,
      };
    } catch {
      return { ...clock, origin: '', online: () => true };
    }
  },
});

/** Confirma los recursos guardados; comprobar actualizaciones no prueba que el shell esté completo. */
@Injectable({ providedIn: 'root' })
export class CatalogPwaService {
  private readonly updates = inject(SwUpdate, { optional: true });
  private readonly environment = inject(CATALOG_PWA_ENV);

  async prepare(): Promise<CatalogPwaState> {
    const environment = this.environment;
    if (!this.updates?.isEnabled || !environment.fetch || !environment.caches || !environment.worker || !environment.origin) {
      return 'unavailable';
    }
    if (!environment.online()) return this.offlineState();
    let installationFailed = false;
    const subscription = this.updates.versionUpdates?.subscribe(event => {
      if (event.type === 'VERSION_INSTALLATION_FAILED') installationFailed = true;
    });
    const unrecoverable = this.updates.unrecoverable?.subscribe(() => { installationFailed = true; });
    try {
      await this.updates.checkForUpdate();
      if (installationFailed) return 'error';
      if (!environment.online()) return this.offlineState();
      const manifestUrl = new URL('/ngsw.json', environment.origin).href;
      const response = await environment.fetch(manifestUrl, {
        cache: 'no-store', headers: { 'ngsw-bypass': 'true' },
      });
      if (!environment.online()) return this.offlineState();
      if (!response.ok) return 'error';
      const urls = prefetchedUrls(await response.json(), environment.origin);
      return await this.waitForResources(urls, () => installationFailed);
    } catch {
      return environment.online() ? 'error' : this.offlineState();
    } finally {
      subscription?.unsubscribe();
      unrecoverable?.unsubscribe();
    }
  }

  private offlineState(): CatalogPwaState {
    return this.environment.worker?.controller ? 'offline' : 'error';
  }

  private async waitForResources(urls: string[], installationFailed: () => boolean): Promise<CatalogPwaState> {
    const environment = this.environment;
    const duration = Math.min(10000, Math.max(0, environment.timeoutMs));
    const deadline = environment.now() + duration;
    let expired = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const timeout = new Promise<CatalogPwaState>(resolve => {
      timer = setTimeout(() => { expired = true; resolve('error'); }, duration);
    });
    const poll = async (): Promise<CatalogPwaState> => {
      do {
        if (expired || installationFailed()) return 'error';
        if (!environment.online()) return this.offlineState();
        const resources = await Promise.all(urls.map(url => environment.caches!.match(url)));
        if (expired || installationFailed()) return 'error';
        if (!environment.online()) return this.offlineState();
        if (resources.every(resource => resource?.ok)) return 'ready';
        const remaining = deadline - environment.now();
        if (remaining <= 0) return 'error';
        await environment.wait(Math.min(100, remaining));
      } while (!expired && environment.now() <= deadline);
      return 'error';
    };
    try {
      return await Promise.race([poll(), timeout]);
    } finally {
      expired = true;
      clearTimeout(timer);
    }
  }
}

function prefetchedUrls(value: unknown, origin: string): string[] {
  const invalid = () => new Error('No se pudo verificar el shell de la aplicación.');
  if (!value || typeof value !== 'object') throw invalid();
  const manifest = value as Record<string, unknown>;
  const assetUrl = (path: unknown): string => {
    if (typeof path !== 'string' || !path) throw invalid();
    const url = new URL(path, origin);
    const pathname = decodeURIComponent(url.pathname);
    if (url.origin !== origin || !['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.hash
      || /^\/(?:api|admin)(?:\/|$)/i.test(pathname)) throw invalid();
    return url.href;
  };
  const index = assetUrl(manifest['index']);
  const groups = manifest['assetGroups'];
  if (!Array.isArray(groups)) throw invalid();
  const urls = new Set<string>();
  for (const value of groups) {
    if (!value || typeof value !== 'object') throw invalid();
    const group = value as Record<string, unknown>;
    if (group['installMode'] !== 'prefetch') continue;
    if (!Array.isArray(group['urls'])) throw invalid();
    for (const path of group['urls']) urls.add(assetUrl(path));
  }
  if (!urls.has(index)) throw invalid();
  return [...urls];
}
