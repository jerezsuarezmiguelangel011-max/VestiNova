import { Injectable, computed, signal } from '@angular/core';
import type { CatalogProduct, CatalogResult } from '../catalog/catalog.models';
import type { PurchaseCommand } from './purchase-api.service';

export interface PurchaseSelection {
  product: CatalogProduct;
  cantidad: string;
  source: 'network' | 'local';
  downloadedAt: string | null;
}

export function validPurchaseQuantity(value: string): boolean {
  return /^[1-9]\d*$/.test(value) && Number.isSafeInteger(Number(value)) && Number(value) <= 2147483647;
}

/** Selección temporal en memoria; no persiste compras, credenciales ni datos en el navegador. */
@Injectable({ providedIn: 'root' })
export class PurchaseSelectionService {
  private readonly selected = signal<readonly PurchaseSelection[]>([]);
  private operation: { signature: string; id: string } | null = null;
  readonly lines = this.selected.asReadonly();
  readonly valid = computed(() => this.selected().length > 0 && this.selected().every(line => validPurchaseQuantity(line.cantidad)));

  add(response: CatalogResult<CatalogProduct>): void {
    if (this.selected().some(line => line.product.id === response.data.id)) return;
    this.selected.update(lines => [...lines, {
      product: response.data, cantidad: '1', source: response.source, downloadedAt: response.downloadedAt,
    }]);
    this.operation = null;
  }

  updateQuantity(id: number, cantidad: string): void {
    if (!this.selected().some(line => line.product.id === id && line.cantidad !== cantidad)) return;
    this.selected.update(lines => lines.map(line => line.product.id === id ? { ...line, cantidad } : line));
    this.operation = null;
  }

  remove(id: number): void {
    if (!this.selected().some(line => line.product.id === id)) return;
    this.selected.update(lines => lines.filter(line => line.product.id !== id));
    this.operation = null;
  }

  command(): PurchaseCommand | null {
    if (!this.valid()) return null;
    const items = this.selected().map(line => ({ producto_id: line.product.id, cantidad: Number(line.cantidad) }))
      .sort((left, right) => left.producto_id - right.producto_id);
    const signature = JSON.stringify(items);
    if (this.operation?.signature !== signature) this.operation = { signature, id: crypto.randomUUID() };
    return { id: this.operation.id, items };
  }

  clear(): void {
    this.selected.set([]);
    this.operation = null;
  }
}
