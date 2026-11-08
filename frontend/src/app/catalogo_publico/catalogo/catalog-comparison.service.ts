import { HttpClient } from '@angular/common/http';
import { computed, inject, Injectable, signal } from '@angular/core';
import { Observable } from 'rxjs';
import type { CatalogProduct } from './catalog.models';
import { CatalogShopService } from './catalog-shop.service';

export interface ComparisonVariant {
  id: number;
  talla: string;
  color: string;
  sucursales: Array<{
    sucursal_id: number;
    sucursal: string;
    estado: 'DISPONIBLE' | 'AGOTADO' | 'NO_VERIFICADO';
    actualizado_en: string | null;
  }>;
}
export interface ComparisonProduct extends CatalogProduct {
  variantes: ComparisonVariant[];
}
export interface ComparisonResult {
  tienda: string;
  consultado_en: string;
  alcance: 'DISPONIBILIDAD_REFERENCIAL';
  items: ComparisonProduct[];
}

/** Selección efímera: nunca mezcla productos de tiendas diferentes ni usa datos offline como vigentes. */
@Injectable({ providedIn: 'root' })
export class CatalogComparisonService {
  private readonly http = inject(HttpClient);
  readonly shop = inject(CatalogShopService);
  private readonly tenant = signal<string | null>(null);
  private readonly draft = signal<CatalogProduct[]>([]);
  readonly items = computed(() => this.tenant() === this.shop.tienda() ? this.draft() : []);
  readonly count = computed(() => this.items().length);

  add(product: CatalogProduct): string {
    const tienda = this.shop.tienda();
    if (!tienda) return 'Selecciona una tienda antes de comparar prendas.';
    if (this.tenant() !== tienda) {
      this.tenant.set(tienda);
      this.draft.set([]);
    }
    if (this.draft().some(item => item.id === product.id)) return 'La prenda ya está en la comparación.';
    if (this.draft().length >= 4) return 'Puedes comparar como máximo cuatro prendas. Retira una para continuar.';
    this.draft.update(items => [...items, product]);
    return 'Prenda agregada a la comparación.';
  }

  remove(id: number): void {
    this.draft.update(items => items.filter(item => item.id !== id));
  }

  compare(): Observable<ComparisonResult> {
    const tienda = this.shop.tienda();
    const selected = this.items();
    if (!tienda || selected.length < 2 || selected.length > 4) {
      throw new Error('Selecciona entre dos y cuatro prendas de la misma tienda.');
    }
    return this.http.post<ComparisonResult>('/api/catalogo/comparar',
      { tienda, producto_ids: selected.map(item => item.id) },
      { headers: { 'ngsw-bypass': 'true' } },
    );
  }
}
