import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, effect, inject, signal, untracked } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Subject, catchError, of, switchMap, tap } from 'rxjs';
import { CatalogDataService } from './catalog-data.service';
import { CatalogShopService } from './catalog-shop.service';
import { CatalogApiService } from './catalog-api.service';
import { CatalogImage } from './catalog-image';
import { CatalogLocalError } from './catalog.models';
import { StorefrontContextService } from './storefront-context.service';
import type { CatalogList, CatalogQuery } from './catalog.models';

@Component({
  selector: 'app-catalog-list',
  imports: [ReactiveFormsModule, RouterLink, CatalogImage, DatePipe],
  templateUrl: './catalog-list.html',
  styleUrl: './catalog.css',
})
export class CatalogListPage {
  readonly catalog = inject(CatalogDataService);
  readonly shop = inject(CatalogShopService);
  private readonly currentRoute = inject(ActivatedRoute);
  readonly inAdmin = this.currentRoute.parent?.snapshot.routeConfig?.path === 'catalogo-consulta';
  readonly inStorefront = this.currentRoute.parent?.snapshot.routeConfig?.path === 'tienda/:tienda';
  readonly storefront = inject(StorefrontContextService);
  readonly filtersExpanded = signal(false);
  private readonly api = inject(CatalogApiService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly requests = new Subject<CatalogQuery>();
  private currentQuery: CatalogQuery = { limit: 20, offset: 0 };

  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly filterError = signal<string | null>(null);
  readonly categories = signal<Array<{id: number; nombre: string}>>([]);
  readonly source = signal<'network' | 'local' | null>(null);
  readonly downloadedAt = signal<string | null>(null);
  readonly result = signal<CatalogList>({ items: [], total: 0, limit: 20, offset: 0 });
  readonly filters = new FormGroup({
    q: new FormControl('', { nonNullable: true, validators: [Validators.maxLength(120)] }),
    categoria_id: new FormControl<number | null>(null),
    talla: new FormControl('', { nonNullable: true, validators: [Validators.maxLength(30)] }),
    color: new FormControl('', { nonNullable: true, validators: [Validators.maxLength(60)] }),
    temporada: new FormControl('', { nonNullable: true, validators: [Validators.maxLength(60)] }),
    precio_min: new FormControl<number | null>(null, [Validators.min(0)]),
    precio_max: new FormControl<number | null>(null, [Validators.min(0)]),
  });

  constructor() {
    this.requests.pipe(
      tap(() => {
        this.loading.set(true);
        this.error.set(null);
        this.source.set(null);
        this.downloadedAt.set(null);
      }),
      switchMap(query => this.catalog.list(query).pipe(
        catchError((error: unknown) => {
          if (error instanceof CatalogLocalError) {
            this.error.set(error.message);
            this.downloadedAt.set(error.downloadedAt);
            if (error.downloadedAt) this.source.set('local');
          } else {
            const denied = error instanceof HttpErrorResponse && [401, 403].includes(error.status);
            this.error.set(denied
              ? 'No tienes permiso para consultar este catálogo.'
              : 'Comprueba tu conexión e inténtalo de nuevo.');
          }
          return of(null);
        }),
      )),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe(response => {
      this.loading.set(false);
      if (response) {
        this.result.set(response.data);
        this.source.set(response.source);
        this.downloadedAt.set(response.downloadedAt);
      }
    });
    let observedRevision = this.catalog.revision();
    let observedShop = this.shop.tienda();
    effect(() => {
      const revision = this.catalog.revision();
      if (revision > observedRevision) {
        observedRevision = revision;
        const nextShop = this.shop.tienda();
        untracked(() => {
          if (observedShop !== nextShop) {
            observedShop = nextShop;
            this.filters.reset();
            this.currentQuery = { limit: 20, offset: 0 };
            this.loadCategories();
          }
          this.reload();
        });
      }
    });
  }

  ngOnInit(): void {
    this.loadCategories();
    this.reload();
  }

  private loadCategories(): void {
    const tienda = this.shop.tienda();
    this.categories.set([]);
    if (!tienda) return;
    this.api.categorias().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: categories => {
        if (this.shop.tienda() === tienda) this.categories.set(categories);
      },
      error: () => {
        if (this.shop.tienda() === tienda) this.categories.set([]);
      },
    });
  }

  search(): void {
    this.filterError.set(null);
    if (this.filters.invalid) {
      this.filters.markAllAsTouched();
      this.filterError.set('Revisa los filtros antes de buscar.');
      return;
    }
    const v = this.filters.getRawValue();
    if (v.precio_min !== null && v.precio_max !== null && v.precio_min > v.precio_max) {
      this.filterError.set('El precio mínimo no puede superar el precio máximo.');
      return;
    }
    this.currentQuery = {
      q: v.q.trim() || undefined,
      ...(v.categoria_id === null ? {} : { categoria_id: v.categoria_id }),
      talla: v.talla.trim() || undefined,
      color: v.color.trim() || undefined,
      temporada: v.temporada.trim() || undefined,
      ...(v.precio_min === null ? {} : { precio_min: v.precio_min }),
      ...(v.precio_max === null ? {} : { precio_max: v.precio_max }),
      limit: 20,
      offset: 0,
    };
    this.reload();
  }

  clear(): void {
    this.filters.reset();
    this.filterError.set(null);
    this.search();
  }

  reload(): void { this.requests.next({ ...this.currentQuery }); }

  page(direction: -1 | 1): void {
    if (this.loading()) return;
    let offset = this.currentQuery.offset + direction * this.currentQuery.limit;
    if (direction === -1) {
      const lastOffset = Math.max(0, Math.floor((this.result().total - 1) / this.currentQuery.limit) * this.currentQuery.limit);
      offset = Math.min(offset, lastOffset);
    }
    if (offset < 0 || offset === this.currentQuery.offset || (direction === 1 && offset >= this.result().total)) return;
    this.currentQuery = { ...this.currentQuery, offset };
    this.reload();
  }

  hasSearch(): boolean {
    return Boolean(this.currentQuery.q || this.currentQuery.categoria_id ||
      this.currentQuery.talla || this.currentQuery.color || this.currentQuery.temporada ||
      this.currentQuery.precio_min !== undefined || this.currentQuery.precio_max !== undefined);
  }
  first(): number { return this.result().items.length ? this.result().offset + 1 : 0; }
  last(): number {
    return this.result().items.length
      ? Math.min(this.result().offset + this.result().items.length, this.result().total)
      : 0;
  }
}
