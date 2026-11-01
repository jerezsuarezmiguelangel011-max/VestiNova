import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { CompanyService } from '../company/company.service';
import { Variant, VariantInput } from './variant.model';

@Injectable({ providedIn: 'root' })
export class VariantService {
  private readonly http = inject(HttpClient);
  private readonly companies = inject(CompanyService);

  list(productId: number) {
    return this.companies.scoped(company => this.http.get<Variant[]>(`/api/admin/productos/${productId}/variantes`, { headers: { 'X-Empresa-Id': String(company.id) } }));
  }

  create(productId: number, input: VariantInput) {
    return this.companies.scoped(company => this.http.post<Variant>(`/api/admin/productos/${productId}/variantes`, input, { headers: { 'X-Empresa-Id': String(company.id) } }));
  }

  update(variantId: number, changes: Partial<VariantInput>) {
    return this.companies.scoped(company => this.http.patch<Variant>(`/api/admin/variantes/${variantId}`, changes, { headers: { 'X-Empresa-Id': String(company.id) } }));
  }
}
