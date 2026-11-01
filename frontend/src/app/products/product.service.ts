import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Observable } from 'rxjs';
import { Product, ProductInput, ProductList, ProductQuery } from './product.model';
import { CompanyService } from '../company/company.service';

@Injectable({ providedIn: 'root' })
export class ProductService {
  private readonly http = inject(HttpClient);
  private readonly companies = inject(CompanyService);
  private readonly endpoint = '/api/admin/productos';
  readonly notice = signal<string | null>(null);

  constructor() {
    // El servicio sobrevive a las páginas: una confirmación de A no pertenece a B.
    this.companies.changes$.pipe(takeUntilDestroyed()).subscribe(() => this.notice.set(null));
  }

  list(query: ProductQuery): Observable<ProductList> {
    let params = new HttpParams().set('limit', query.limit).set('offset', query.offset);
    if (query.q) params = params.set('q', query.q);
    if (query.activo !== undefined) params = params.set('activo', query.activo);
    return this.companies.scoped(company => this.http.get<ProductList>(this.endpoint, { params, headers: { 'X-Empresa-Id': String(company.id) } }));
  }

  get(id: number): Observable<Product> {
    return this.companies.scoped(company => this.http.get<Product>(`${this.endpoint}/${id}`, { headers: { 'X-Empresa-Id': String(company.id) } }));
  }

  create(product: ProductInput): Observable<Product> {
    return this.companies.scoped(company => this.http.post<Product>(this.endpoint, product, { headers: { 'X-Empresa-Id': String(company.id) } }));
  }

  update(id: number, changes: Partial<ProductInput>): Observable<Product> {
    return this.companies.scoped(company => this.http.patch<Product>(`${this.endpoint}/${id}`, changes, { headers: { 'X-Empresa-Id': String(company.id) } }));
  }
}
