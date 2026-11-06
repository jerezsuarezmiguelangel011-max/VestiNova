import { TestBed } from '@angular/core/testing';
import { CatalogShopService } from '../../catalogo_publico/catalogo/catalog-shop.service';
import type { CatalogProduct } from '../../catalogo_publico/catalogo/catalog.models';
import { PurchaseSelectionService } from './purchase-selection.service';

describe('CU09: carrito aislado por empresa', () => {
  it('descarta automáticamente la selección de otra tienda', () => {
    TestBed.configureTestingModule({});
    const shop = TestBed.inject(CatalogShopService);
    shop.setTienda('demo-moda-andina');
    const selection = TestBed.inject(PurchaseSelectionService);
    const andina = { id: 11, nombre: 'Polera Andina' } as CatalogProduct;
    const urbana = { id: 22, nombre: 'Jeans Urbana' } as CatalogProduct;
    selection.add({ data: andina, source: 'network', downloadedAt: null });
    expect(selection.lines().map(item => item.product.id)).toEqual([11]);

    shop.setTienda('demo-moda-urbana');
    selection.add({ data: urbana, source: 'network', downloadedAt: null });
    expect(selection.lines().map(item => item.product.id)).toEqual([22]);

    shop.setTienda('demo-moda-andina');
    selection.add({ data: andina, source: 'network', downloadedAt: null });
    expect(selection.lines().map(item => item.product.id)).toEqual([11]);
  });

  it('conserva talla/color elegido desde el detalle sin duplicar la misma prenda', () => {
    TestBed.configureTestingModule({});
    const shop = TestBed.inject(CatalogShopService);
    shop.setTienda('demo-moda-andina');
    const selection = TestBed.inject(PurchaseSelectionService);
    const product = { id: 11, nombre: 'Polera', slug: 'polera' } as CatalogProduct;
    const value = { data: product, source: 'network' as const, downloadedAt: null };
    selection.add(value, 14);
    expect(selection.lines()[0].varianteId).toBe(14);
    selection.add(value, 15);
    expect(selection.lines()).toHaveLength(1);
    expect(selection.lines()[0].varianteId).toBe(15);
    selection.clear();
    expect(selection.lines()).toHaveLength(0);
  });
});
