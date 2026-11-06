import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { CatalogApiService } from './catalog-api.service';
import { CatalogDataService } from './catalog-data.service';
import { CatalogShopService } from './catalog-shop.service';
import type { CatalogProduct } from './catalog.models';
import { StorefrontHomePage } from './storefront-home';

const demoProduct = (id: number, slug: string, nombre: string, promo: boolean): CatalogProduct => ({
  id, slug, nombre, categoria_nombre: 'Poleras', precio: '120.00',
  moneda: 'BOB', imagen_url: null,
  precio_promocional: promo ? '108.00' : null,
  promocion_nombre: promo ? 'Oferta de demostración' : null,
} as CatalogProduct);

describe('Vitrina pública de empresa', () => {
  it('muestra novedades y descuentos de la empresa seleccionada, nunca de otra', async () => {
    const shop = new CatalogShopService();
    const revision = signal(0);
    const andina = demoProduct(12, 'polera-andina', 'Polera Andina', true);
    const urbana = demoProduct(25, 'polera-urbana', 'Polera Urbana', false);
    shop.setTienda('demo-moda-andina');
    const list = vi.fn(() => of({
      data: { items: shop.tienda() === 'demo-moda-andina' ? [andina] : [urbana],
        total: 1, limit: 24, offset: 0 }, source: 'network' as const, downloadedAt: null,
    }));
    TestBed.configureTestingModule({
      imports: [StorefrontHomePage],
      providers: [
        provideRouter([]), { provide: CatalogShopService, useValue: shop },
        { provide: CatalogDataService, useValue: { revision, list } },
        { provide: CatalogApiService, useValue: {
          categorias: () => of([{ id: 10, nombre: 'Poleras' }]),
        } },
      ],
    });
    const fixture = TestBed.createComponent(StorefrontHomePage);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;
    expect(root.textContent).toContain('Polera Andina');
    expect(root.textContent).toContain('Oferta de demostración');
    expect(root.textContent).not.toContain('Polera Urbana');
    expect(root.querySelector('.storefront-featured-card')?.getAttribute('href'))
      .toBe('/tienda/demo-moda-andina/prenda/polera-andina');
    expect(root.querySelector('.storefront-category-item')?.getAttribute('href'))
      .toContain('/tienda/demo-moda-andina/catalogo?categoria=10');

    shop.setTienda('demo-moda-urbana');
    revision.update(n => n + 1);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(root.textContent).toContain('Polera Urbana');
    expect(root.textContent).not.toContain('Polera Andina');
    expect(root.textContent).toContain('Por ahora no hay promociones vigentes');
    expect(list).toHaveBeenCalled();
  });
});
