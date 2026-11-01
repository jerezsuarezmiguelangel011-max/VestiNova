import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Subject, catchError, defer, finalize, of, switchMap } from 'rxjs';
import { CompanyService } from '../company/company.service';
import { productError } from './product-errors';
import { ProductList, ProductQuery } from './product.model';
import { ProductService } from './product.service';

@Component({
  selector: 'app-product-list',
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './product-list.html',
  styleUrl: './products.css',
})
export class ProductListPage {
  readonly companies = inject(CompanyService);
  private readonly products = inject(ProductService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly requests = new Subject<ProductQuery>();
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly notice = this.products.notice;
  readonly result = signal<ProductList>({ items: [], total: 0, limit: 20, offset: 0 });
  readonly filters = new FormGroup({
    q: new FormControl('', { nonNullable: true, validators: [Validators.maxLength(120)] }),
    activo: new FormControl('', { nonNullable: true }),
  });
  private currentQuery: ProductQuery = { limit: 20, offset: 0 };

  constructor() {
    this.requests.pipe(
      switchMap(query => defer(() => {
        this.loading.set(true); this.error.set(null);
        return this.products.list(query).pipe(
        catchError(error => { this.error.set(productError(error)); return of(null); }),
        finalize(() => this.loading.set(false)),
      ); })),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe(response => {
      if (response) this.result.set(response);
    });
    let revision = this.companies.revision();
    this.companies.changes$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(next => {
      if (revision === next) return;
      revision = next;
      this.notice.set(null);
      this.filters.reset();
      this.currentQuery = { limit: 20, offset: 0 };
      this.result.set({ items: [], total: 0, limit: 20, offset: 0 });
      this.error.set(null);
      if (this.companies.active()) this.reload();
    });
  }

  ngOnInit(): void { this.reload(); }

  search(): void {
    if (this.filters.invalid) { this.filters.markAllAsTouched(); return; }
    const filters = this.filters.getRawValue();
    this.currentQuery = {
      q: filters.q.trim() || undefined,
      activo: filters.activo === '' ? undefined : filters.activo === 'true',
      limit: 20, offset: 0,
    };
    this.reload();
  }

  clear(): void { this.filters.reset(); this.search(); }
  reload(): void { this.requests.next({ ...this.currentQuery }); }

  page(direction: -1 | 1): void {
    if (this.loading()) return;
    const next = this.currentQuery.offset + direction * this.currentQuery.limit;
    if (next < 0 || next >= this.result().total) return;
    this.currentQuery = { ...this.currentQuery, offset: next };
    this.reload();
  }

  first(): number { return this.result().total === 0 ? 0 : this.result().offset + 1; }
  last(): number { return Math.min(this.result().offset + this.result().items.length, this.result().total); }
  hasFilters(): boolean { return Boolean(this.currentQuery.q || this.currentQuery.activo !== undefined); }
}
