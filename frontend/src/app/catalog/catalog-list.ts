import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, effect, inject, signal, untracked } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Subject, catchError, of, switchMap, tap } from 'rxjs';
import { CatalogDataService } from './catalog-data.service';
import { CatalogImage } from './catalog-image';
import { CatalogLocalError } from './catalog.models';
import type { CatalogList, CatalogQuery } from './catalog.models';

@Component({
  selector: 'app-catalog-list',
  imports: [ReactiveFormsModule, RouterLink, CatalogImage, DatePipe],
  templateUrl: './catalog-list.html',
  styleUrl: './catalog.css',
})
export class CatalogListPage {
  private readonly catalog = inject(CatalogDataService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly requests = new Subject<CatalogQuery>();
  private currentQuery: CatalogQuery = { limit: 20, offset: 0 };

  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly source = signal<'network' | 'local' | null>(null);
  readonly downloadedAt = signal<string | null>(null);
  readonly result = signal<CatalogList>({ items: [], total: 0, limit: 20, offset: 0 });
  readonly filters = new FormGroup({
    q: new FormControl('', { nonNullable: true, validators: [Validators.maxLength(120)] }),
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
    effect(() => {
      const revision = this.catalog.revision();
      if (revision > observedRevision) {
        observedRevision = revision;
        untracked(() => this.reload());
      }
    });
  }

  ngOnInit(): void { this.reload(); }

  search(): void {
    if (this.filters.invalid) {
      this.filters.markAllAsTouched();
      return;
    }
    this.currentQuery = {
      q: this.filters.controls.q.value.trim() || undefined,
      limit: 20,
      offset: 0,
    };
    this.reload();
  }

  clear(): void {
    this.filters.reset();
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

  hasSearch(): boolean { return Boolean(this.currentQuery.q); }
  first(): number { return this.result().items.length ? this.result().offset + 1 : 0; }
  last(): number {
    return this.result().items.length
      ? Math.min(this.result().offset + this.result().items.length, this.result().total)
      : 0;
  }
}
