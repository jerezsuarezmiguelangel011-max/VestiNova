import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { CatalogList, CatalogProduct, CatalogQuery } from './catalog.models';

@Injectable({ providedIn: 'root' })
export class CatalogApiService {
  private readonly http = inject(HttpClient);
  private readonly endpoint = '/api/catalogo/productos';
  // La API pública usa IndexedDB explícitamente. Sin este bypass, el worker puede
  // convertir una pérdida de red en 504 y ocultar la causa real al repositorio.
  private readonly headers = { 'ngsw-bypass': 'true' };

  list(query: CatalogQuery): Observable<CatalogList> {
    let params = new HttpParams().set('limit', query.limit).set('offset', query.offset);
    const name = query.q?.trim();
    if (name) params = params.set('q', name);
    return this.http.get<CatalogList>(this.endpoint, { params, headers: this.headers });
  }

  get(slug: string): Observable<CatalogProduct> {
    return this.http.get<CatalogProduct>(`${this.endpoint}/${encodeURIComponent(slug)}`, { headers: this.headers });
  }
}
