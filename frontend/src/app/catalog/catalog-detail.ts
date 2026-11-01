import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, effect, inject, signal, untracked } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Observable, Subject, catchError, distinctUntilChanged, map, of, startWith, switchMap } from 'rxjs';
import { CatalogDataService } from './catalog-data.service';
import { CatalogImage } from './catalog-image';
import { CatalogLocalError, type CatalogProduct, type CatalogResult } from './catalog.models';

@Component({
  selector: 'vn-catalog-detail',
  imports: [RouterLink, CatalogImage, DatePipe],
  templateUrl: './catalog-detail.html',
  styleUrl: './catalog.css',
})
export class CatalogDetailPage {
  private readonly catalog = inject(CatalogDataService);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  private readonly retries = new Subject<void>();
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly notFound = signal(false);
  readonly product = signal<CatalogProduct | null>(null);
  readonly source = signal<'network' | 'local' | null>(null);
  readonly downloadedAt = signal<string | null>(null);

  constructor() {
    this.route.paramMap.pipe(
      map(params => params.get('slug')),
      distinctUntilChanged(),
      switchMap(slug => this.retries.pipe(
        startWith(undefined),
        switchMap(() => this.load(slug)),
      )),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe(response => {
      if (response) {
        this.product.set(response.data);
        this.source.set(response.source);
        this.downloadedAt.set(response.downloadedAt);
      }
      this.loading.set(false);
    });
    let observedRevision = this.catalog.revision();
    effect(() => {
      const revision = this.catalog.revision();
      if (revision > observedRevision) {
        observedRevision = revision;
        untracked(() => this.retries.next());
      }
    });
  }

  retry(): void {
    if (!this.loading() && this.error()) this.retries.next();
  }

  private load(slug: string | null): Observable<CatalogResult<CatalogProduct> | null> {
    this.loading.set(true);
    this.error.set(null);
    this.notFound.set(false);
    this.product.set(null);
    this.source.set(null);
    this.downloadedAt.set(null);
    if (!slug) {
      this.notFound.set(true);
      return of(null);
    }
    return this.catalog.get(slug).pipe(catchError((error: unknown) => {
      if (error instanceof CatalogLocalError) {
        this.error.set(error.message);
        this.downloadedAt.set(error.downloadedAt);
        if (error.downloadedAt) this.source.set('local');
        return of(null);
      }
      const status = error instanceof HttpErrorResponse ? error.status : undefined;
      if (status === 404) {
        this.notFound.set(true);
      } else {
        this.error.set(status === 0
          ? 'No pudimos conectar con el catálogo. Comprueba tu conexión e inténtalo nuevamente.'
          : status === 401 || status === 403
            ? 'No tienes permiso para consultar este producto.'
            : 'No pudimos cargar el producto. Inténtalo nuevamente.');
      }
      return of(null);
    }));
  }
}
