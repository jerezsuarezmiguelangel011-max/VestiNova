import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { CompanyService } from '../empresa/company.service';

export interface Branch {
  id: number;
  empresa_id: number;
  codigo: string;
  nombre: string;
  ciudad: string;
  ubicacion: string;
  contacto: string;
  activo: boolean;
}

export interface BranchInput {
  codigo: string;
  nombre: string;
  ciudad: string;
  ubicacion: string;
  contacto: string;
}

export type BranchChanges = Partial<Omit<BranchInput, 'codigo'>> & { activo?: boolean };

@Injectable({ providedIn: 'root' })
export class BranchService {
  private readonly http = inject(HttpClient);
  private readonly companies = inject(CompanyService);
  private readonly endpoint = '/api/admin/sucursales';

  list(): Observable<Branch[]> {
    return this.companies.scoped(company => this.http.get<Branch[]>(`${this.endpoint}/gestion`, {
      headers: { 'X-Empresa-Id': String(company.id) },
    }));
  }

  create(input: BranchInput): Observable<Branch> {
    return this.companies.scoped(company => this.http.post<Branch>(this.endpoint, input, {
      headers: { 'X-Empresa-Id': String(company.id) },
    }));
  }

  update(id: number, changes: BranchChanges): Observable<Branch> {
    return this.companies.scoped(company => this.http.patch<Branch>(`${this.endpoint}/${id}`, changes, {
      headers: { 'X-Empresa-Id': String(company.id) },
    }));
  }
}
