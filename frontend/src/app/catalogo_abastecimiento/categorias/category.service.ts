import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { CompanyService } from '../../organizacion_empresarial/empresa/company.service';

export interface ProductCategory {
  id: number;
  empresa_id: number;
  nombre: string;
  descripcion: string;
  activo: boolean;
}

export interface CategoryInput { nombre: string; descripcion: string; }
export type CategoryChanges = Partial<CategoryInput> & { activo?: boolean };

@Injectable({ providedIn: 'root' })
export class CategoryService {
  private readonly http = inject(HttpClient);
  private readonly companies = inject(CompanyService);
  private readonly endpoint = '/api/admin/categorias';

  list(): Observable<ProductCategory[]> {
    return this.companies.scoped(company => this.http.get<ProductCategory[]>(this.endpoint, {
      headers: { 'X-Empresa-Id': String(company.id) },
    }));
  }

  create(input: CategoryInput): Observable<ProductCategory> {
    return this.companies.scoped(company => this.http.post<ProductCategory>(this.endpoint, input, {
      headers: { 'X-Empresa-Id': String(company.id) },
    }));
  }

  update(id: number, changes: CategoryChanges): Observable<ProductCategory> {
    return this.companies.scoped(company => this.http.patch<ProductCategory>(`${this.endpoint}/${id}`, changes, {
      headers: { 'X-Empresa-Id': String(company.id) },
    }));
  }
}
