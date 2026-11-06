import { HttpErrorResponse } from '@angular/common/http';
import { inject, Injectable, signal } from '@angular/core';
import { Observable, catchError, defer, firstValueFrom, map, tap, throwError } from 'rxjs';
import { CatalogApiService } from './catalog-api.service';
import { CatalogOfflineStoreService } from './catalog-offline-store.service';
import { CatalogShopService } from './catalog-shop.service';
import {
  CatalogList, CatalogLocalError, CatalogProduct, CatalogQuery, CatalogResult,
  CatalogBranch, CatalogSnapshot, CatalogSnapshotMetadata, CatalogVariant, copyPublicProduct,
} from './catalog.models';

class IncompleteDownloadError extends Error {}
class CatalogCopyConflict extends Error {}

@Injectable({ providedIn: 'root' })
export class CatalogDataService {
  private readonly api = inject(CatalogApiService);
  private readonly store = inject(CatalogOfflineStoreService);
  readonly shop = inject(CatalogShopService);
  private accessDenial: HttpErrorResponse | null = null;
  private accessRevision = 0;
  readonly saved = signal<CatalogSnapshotMetadata | null>(null);
  readonly downloading = signal(false);
  readonly progress = signal<{ received: number; total: number } | null>(null);
  readonly downloadError = signal<string | null>(null);
  readonly downloadConflict = signal(false);
  readonly downloadNotice = signal<string | null>(null);
  readonly storageError = signal<string | null>(null);
  readonly revision = signal(0);

  setShop(slug: string | null): void {
    if (!this.shop.setTienda(slug)) return;
    this.accessRevision++;
    this.accessDenial = null;
    this.saved.set(null);
    this.downloadError.set(null);
    this.downloadNotice.set(null);
    this.revision.update(n => n + 1);
    void this.refreshSavedStatus();
  }

  private readCurrent(): Promise<CatalogSnapshot | null> {
    const scope = this.shop.scope();
    return scope === 'public-catalog' ? this.store.read() : this.store.read(scope);
  }

  async refreshSavedStatus(): Promise<void> {
    const expectedScope = this.shop.scope();
    try {
      const snapshot = await this.readCurrent();
      if (expectedScope !== this.shop.scope()) return;
      this.saved.set(snapshot ? this.metadata(snapshot) : null);
      this.storageError.set(null);
    } catch {
      if (expectedScope === this.shop.scope()) this.storageError.set(new CatalogLocalError('storage').message);
    }
  }

  list(query: CatalogQuery): Observable<CatalogResult<CatalogList>> {
    return defer(() => {
      const revision = this.accessRevision;
      return this.api.list(query).pipe(
        tap(() => this.acceptResponse(revision)),
        map(data => ({ data, source: 'network' as const, downloadedAt: null })),
        catchError((error: unknown) => this.fallback(error, async () => {
          const snapshot = await this.localSnapshot();
          const name = query.q?.trim().toLowerCase();
          if ((query.talla || query.color) && snapshot.variants === undefined) {
            throw new CatalogLocalError('unavailable-filter', snapshot.downloadedAt);
          }
          const matches = snapshot.products.filter(product => {
            if (name && !product.nombre.toLowerCase().includes(name)) return false;
            if (query.categoria_id !== undefined && product.categoria_id !== query.categoria_id) return false;
            if (query.temporada && (product.temporada ?? '').trim().toLowerCase() !== query.temporada.trim().toLowerCase()) return false;
            if (query.talla || query.color) {
              if (!(snapshot.variants ?? []).some(variant =>
                variant.producto_slug === product.slug
                && (!query.talla || variant.talla.toLowerCase() === query.talla.trim().toLowerCase())
                && (!query.color || variant.color.toLowerCase() === query.color.trim().toLowerCase())
              )) return false;
            }
            const price = Number(product.precio);
            if (query.precio_min !== undefined && price < query.precio_min) return false;
            if (query.precio_max !== undefined && price > query.precio_max) return false;
            return true;
          }).sort((left, right) => right.id - left.id);
          return {
            data: { items: matches.slice(query.offset, query.offset + query.limit), total: matches.length, limit: query.limit, offset: query.offset },
            source: 'local' as const, downloadedAt: snapshot.downloadedAt,
          };
        })),
      );
    });
  }

  get(slug: string): Observable<CatalogResult<CatalogProduct>> {
    return defer(() => {
      const revision = this.accessRevision;
      return this.api.get(slug).pipe(
        tap(() => this.acceptResponse(revision)),
        map(data => ({ data, source: 'network' as const, downloadedAt: null })),
        catchError((error: unknown) => this.fallback(error, async () => {
          const snapshot = await this.localSnapshot();
          const product = snapshot.products.find(item => item.slug === slug);
          if (!product) throw new CatalogLocalError('missing-product', snapshot.downloadedAt);
          return { data: product, source: 'local' as const, downloadedAt: snapshot.downloadedAt };
        })),
      );
    });
  }

  variantes(slug: string): Observable<CatalogResult<Array<{ id: number; talla: string; color: string }>>> {
    return defer(() => {
      const revision = this.accessRevision;
      return this.api.variantes(slug).pipe(
        tap(() => this.acceptResponse(revision)),
        map(data => ({ data, source: 'network' as const, downloadedAt: null })),
        catchError((error: unknown) => this.fallback(error, async () => {
          const snapshot = await this.localSnapshot();
          if (!snapshot.products.some(product => product.slug === slug)) {
            throw new CatalogLocalError('missing-product', snapshot.downloadedAt);
          }
          if (!snapshot.variants) throw new CatalogLocalError('unavailable-filter', snapshot.downloadedAt);
          return { data: snapshot.variants.filter(item => item.producto_slug === slug)
              .map(({ id, talla, color }) => ({ id, talla, color })),
            source: 'local' as const, downloadedAt: snapshot.downloadedAt };
        })),
      );
    });
  }

  /** Nombres públicos guardados para consultar el contexto de sucursal sin red. */
  async offlineBranches(): Promise<CatalogBranch[]> {
    const snapshot = await this.localSnapshot();
    return snapshot.branches ?? [];
  }

  /** Solo una descarga explícita reemplaza la copia; navegar no la modifica. */
  async download(expectedDownloadedAt?: string | null): Promise<boolean> {
    if (this.downloading()) return false;
    this.downloading.set(true);
    this.progress.set(null);
    this.downloadError.set(null);
    this.downloadConflict.set(false);
    this.downloadNotice.set(null);
    try {
      const locks = globalThis.navigator?.locks;
      if (locks) {
        return await locks.request('vestinova-public-catalog-download', { mode: 'exclusive', ifAvailable: true }, lock => {
          if (!lock) {
            this.downloadError.set('Otra pestaña está descargando el catálogo. Espera a que termine y vuelve a intentarlo.');
            return Promise.resolve(false);
          }
          return this.downloadCatalog(expectedDownloadedAt);
        });
      }
      // Sin Web Locks, la exclusión se limita a esta instancia del servicio.
      return await this.downloadCatalog(expectedDownloadedAt);
    } catch (error: unknown) {
      if (error instanceof CatalogCopyConflict) {
        this.downloadConflict.set(true);
        this.downloadError.set('La copia local cambió después de registrar la operación. Revisa los datos y registra una nueva actualización.');
      } else if (error instanceof HttpErrorResponse && [401, 403].includes(error.status)) {
        this.rememberDenial(error);
        this.downloadError.set('No tienes autorización para descargar el catálogo. La copia anterior se conserva.');
      } else if (error instanceof HttpErrorResponse) {
        this.downloadError.set('No se pudo completar la descarga. Comprueba la conexión e inténtalo de nuevo. La copia anterior se conserva.');
      } else if (error instanceof IncompleteDownloadError) {
        this.downloadError.set('No se pudo verificar el catálogo completo. Puede haber cambiado durante la descarga. Inténtalo de nuevo; la copia anterior se conserva.');
      } else {
        this.downloadError.set('No se pudo guardar el catálogo local. Comprueba el almacenamiento y el espacio del navegador. La copia anterior se conserva.');
      }
      return false;
    } finally {
      this.downloading.set(false);
    }
  }

  private async downloadCatalog(expectedDownloadedAt?: string | null): Promise<boolean> {
    const revision = this.accessRevision;
    // La comparación comparte el mismo Web Lock que las descargas de sincronización del CU13.
    if (expectedDownloadedAt !== undefined) {
      const current = await this.readCurrent();
      if ((current?.downloadedAt ?? null) !== expectedDownloadedAt) throw new CatalogCopyConflict();
      this.checkAccess(revision);
    }
    const limit = 100;
    const products: CatalogProduct[] = [];
    const ids = new Set<number>();
    const slugs = new Set<string>();
    let total: number | undefined;
    let offset = 0;
    let previousId = Infinity;
    do {
      const page = await firstValueFrom(this.api.list({ limit, offset }));
      this.checkAccess(revision);
      if (!page || !Array.isArray(page.items) || !Number.isSafeInteger(page.total) || page.total < 0
        || page.limit !== limit || page.offset !== offset || (total !== undefined && page.total !== total)
        || page.items.length !== Math.min(limit, Math.max(0, page.total - offset))) {
        throw new IncompleteDownloadError();
      }
      total = page.total;
      for (const item of page.items) {
        let product: CatalogProduct;
        try { product = copyPublicProduct(item); } catch { throw new IncompleteDownloadError(); }
        if (ids.has(product.id) || slugs.has(product.slug) || product.id >= previousId) throw new IncompleteDownloadError();
        ids.add(product.id);
        slugs.add(product.slug);
        previousId = product.id;
        products.push(product);
      }
      this.progress.set({ received: products.length, total });
      offset += limit;
    } while (products.length < total);

    // Descargar variantes en la misma preparación de la copia del tenant.
    // Las descargas antiguas no cambian su contrato HTTP.
    let variants: CatalogVariant[] | undefined;
    if (this.shop.tienda()) {
      variants = [];
      let variantOffset = 0;
      let variantTotal: number | undefined;
      let lastVariantId = Infinity;
      do {
        const page = await firstValueFrom(this.api.variantesTienda(limit, variantOffset));
        this.checkAccess(revision);
        if (!Array.isArray(page.items) || !Number.isSafeInteger(page.total) || page.total < 0
          || page.limit !== limit || page.offset !== variantOffset
          || (variantTotal !== undefined && variantTotal !== page.total)
          || page.items.length !== Math.min(limit, Math.max(0, page.total - variantOffset))) {
          throw new IncompleteDownloadError();
        }
        variantTotal = page.total;
        for (const variant of page.items) {
          if (!Number.isSafeInteger(variant.id) || variant.id < 1 || variant.id >= lastVariantId
            || !slugs.has(variant.producto_slug)
            || typeof variant.talla !== 'string' || !variant.talla.trim()
            || typeof variant.color !== 'string' || !variant.color.trim()) {
            throw new IncompleteDownloadError();
          }
          lastVariantId = variant.id;
          variants.push({ id: variant.id, producto_slug: variant.producto_slug,
            talla: variant.talla, color: variant.color });
        }
        variantOffset += limit;
      } while (variants.length < variantTotal);
    }

    let branches: CatalogBranch[] | undefined;
    if (this.shop.tienda()) {
      const visible = await firstValueFrom(this.api.sucursales());
      this.checkAccess(revision);
      if (!Array.isArray(visible) || visible.length > 1000) throw new IncompleteDownloadError();
      branches = visible.map(branch => {
        if (!Number.isSafeInteger(branch.id) || branch.id < 1 ||
            typeof branch.nombre !== 'string' || !branch.nombre.trim() || branch.nombre.length > 120) {
          throw new IncompleteDownloadError();
        }
        return { id: branch.id, nombre: branch.nombre };
      });
      if (new Set(branches.map(branch => branch.id)).size !== branches.length) throw new IncompleteDownloadError();
    }

    const snapshot: CatalogSnapshot = {
      schemaVersion: 1, scope: this.shop.scope(), downloadedAt: new Date().toISOString(),
      total: products.length, products,
      ...(variants === undefined ? {} : { variants }),
      ...(branches === undefined ? {} : { branches }),
    };
    this.checkAccess(revision);
    await this.store.replace(snapshot);
    this.saved.set(this.metadata(snapshot));
    this.storageError.set(null);
    // Un guardado confirmado sigue siendo válido, sin borrar una denegación posterior.
    if (revision === this.accessRevision) this.accessDenial = null;
    this.downloadNotice.set(`Catálogo local actualizado: ${products.length} ${products.length === 1 ? 'prenda guardada' : 'prendas guardadas'}.`);
    this.revision.update(value => value + 1);
    return true;
  }

  private checkAccess(revision: number): void {
    if (revision !== this.accessRevision) {
      if (this.accessDenial) throw this.accessDenial;
      throw new CatalogCopyConflict();
    }
  }

  private acceptResponse(revision: number): void {
    this.checkAccess(revision);
    this.accessDenial = null;
  }

  private rememberDenial(error: HttpErrorResponse): void {
    if (this.accessDenial !== error) {
      this.accessRevision += 1;
      this.accessDenial = error;
    }
  }

  private fallback<T>(error: unknown, read: () => Promise<CatalogResult<T>>): Observable<CatalogResult<T>> {
    if (error instanceof HttpErrorResponse && [401, 403].includes(error.status)) this.rememberDenial(error);
    // Un 401/403/404/5xx es una respuesta del servidor, no una pérdida de conexión.
    if (!(error instanceof HttpErrorResponse) || error.status !== 0) return throwError(() => error);
    if (this.accessDenial) return throwError(() => this.accessDenial);
    return defer(read).pipe(tap(() => {
      if (this.accessDenial) throw this.accessDenial;
    }));
  }

  private async localSnapshot(): Promise<CatalogSnapshot> {
    const scope = this.shop.scope();
    let snapshot: CatalogSnapshot | null;
    try { snapshot = await this.readCurrent(); } catch {
      if (this.accessDenial) throw this.accessDenial;
      throw new CatalogLocalError('storage');
    }
    if (this.accessDenial) throw this.accessDenial;
    if (scope !== this.shop.scope()) throw new CatalogCopyConflict();
    if (!snapshot) throw new CatalogLocalError('no-copy');
    this.saved.set(this.metadata(snapshot));
    this.storageError.set(null);
    return snapshot;
  }

  private metadata(snapshot: CatalogSnapshot): CatalogSnapshotMetadata {
    return { schemaVersion: 1, scope: snapshot.scope, downloadedAt: snapshot.downloadedAt, total: snapshot.total };
  }
}
