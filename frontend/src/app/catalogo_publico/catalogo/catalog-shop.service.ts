import { Injectable, signal } from '@angular/core';

/** Identidad de la tienda pública actual; no concede privilegios administrativos. */
@Injectable({ providedIn: 'root' })
export class CatalogShopService {
  readonly tienda = signal<string | null>(null);

  setTienda(value: string | null): boolean {
    // Un identificador inválido jamás debe convertirse en "todas las tiendas".
    const next = value === null ? null
      : /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(value) && value.length <= 100
        ? value : 'tienda-no-disponible';
    if (this.tienda() === next) return false;
    this.tienda.set(next);
    return true;
  }

  scope(): string {
    const slug = this.tienda();
    return slug ? 'public-catalog:' + slug : 'public-catalog';
  }
}
