import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';

export interface Recommendation {
  producto_id: number;
  slug: string;
  nombre: string;
  categoria: string;
  material: string;
  temporada: string;
  imagen_url: string | null;
  precio: string;
  moneda: string;
  disponibilidad: 'NO_VERIFICADA' | 'DISPONIBLE_REFERENCIAL' | 'SIN_UNIDADES_CONOCIDAS';
  motivos: string[];
}

export interface RecommendationResult {
  tienda: string;
  basado_en: string | null;
  consultado_en: string;
  criterio: 'REGLAS_SIMILITUD_CATALOGO' | 'REGLAS_HISTORIAL_CONSENTIDO';
  items: Recommendation[];
}

@Injectable({ providedIn: 'root' })
export class RecommendationsApi {
  private readonly http = inject(HttpClient);

  list(tienda: string, filters: {
    producto_slug?: string; talla?: string; color?: string;
    sucursal_id?: number | null;
  }) {
    let params = new HttpParams().set('tienda', tienda).set('limit', 12);
    if (filters.producto_slug) params = params.set('producto_slug', filters.producto_slug);
    if (filters.talla) params = params.set('talla', filters.talla);
    if (filters.color) params = params.set('color', filters.color);
    if (filters.sucursal_id) params = params.set('sucursal_id', filters.sucursal_id);
    return this.http.get<RecommendationResult>('/api/catalogo/recomendaciones', {
      params, headers: { 'ngsw-bypass': 'true' },
    });
  }
}
