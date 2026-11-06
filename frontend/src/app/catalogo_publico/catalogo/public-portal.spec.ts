import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { of } from 'rxjs';
import { CatalogApiService } from './catalog-api.service';
import { CatalogDataService } from './catalog-data.service';
import { PublicPortalPage } from './public-portal';
import { StorefrontLayout } from './storefront-layout';
import { StorefrontContextService } from './storefront-context.service';

@Component({ template: '<p>Listado público de prendas</p>' })
class ProductListStub {}

const STORES = [
  { slug: 'demo-moda-andina', nombre: 'Moda Andina Demo' },
  { slug: 'demo-moda-urbana', nombre: 'Moda Urbana Demo' },
];

describe('VestiNova · portal multitenant', () => {
  it('muestra enlaces por empresa desde el directorio, sin datos hardcodeados en HTML', async () => {
    TestBed.configureTestingModule({
      imports: [PublicPortalPage],
      providers: [
        provideRouter([]),
        { provide: CatalogApiService, useValue: { tiendas: () => of(STORES) } },
      ],
    });
    const fixture = TestBed.createComponent(PublicPortalPage);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    const html = fixture.nativeElement as HTMLElement;
    const cards = [...html.querySelectorAll<HTMLAnchorElement>('.public-shop-card')];
    expect(cards).toHaveLength(2);
    expect(cards[0].textContent).toContain('Moda Andina Demo');
    expect(cards[0].getAttribute('href')).toBe('/tienda/demo-moda-andina');
    expect(cards[1].getAttribute('href')).toBe('/tienda/demo-moda-urbana');
    expect(html.querySelector('#public-how-title')?.textContent).toContain('De descubrir tu estilo');
    expect(html.textContent).not.toContain('sk_test_');
  });

  it('conserva independencia de sucursales al cambiar de empresa', () => {
    TestBed.configureTestingModule({ providers: [StorefrontContextService] });
    const store = TestBed.inject(StorefrontContextService);
    store.selectCompany('demo-moda-andina');
    store.selectBranch(2, [2, 3]);
    expect(store.branch()).toBe(2);
    store.selectBranch(500, [2, 3]);
    expect(store.branch()).toBeNull();
    store.selectBranch(3, [2, 3]);
    store.selectCompany('demo-moda-urbana');
    expect(store.company()).toBe('demo-moda-urbana');
    expect(store.branch()).toBeNull();
  });

  it('la plantilla reutiliza la API por tienda y no obliga a elegir sucursal para explorar', async () => {
    const activeShop = signal<string | null>(null);
    const mockCatalog = {
      setShop: (slug: string) => activeShop.set(slug),
      saved: signal(null), downloading: signal(false),
      downloadNotice: signal(null), downloadError: signal(null),
      refreshSavedStatus: async () => undefined,
      download: async () => true,
    };
    TestBed.configureTestingModule({
      providers: [
        provideRouter([{
          path: 'tienda/:tienda', component: StorefrontLayout, children: [
            { path: '', pathMatch: 'full', component: ProductListStub },
          ],
        }]),
        { provide: CatalogDataService, useValue: mockCatalog },
        { provide: CatalogApiService, useValue: {
          tiendas: () => of(STORES),
          sucursales: () => of([
            { id: 2, nombre: 'Andina Centro' },
            { id: 3, nombre: 'Andina Norte' },
          ]),
        } },
      ],
    });
    const harness = await RouterTestingHarness.create();
    const page = await harness.navigateByUrl('/tienda/demo-moda-andina', StorefrontLayout);
    harness.detectChanges();
    const host = harness.routeNativeElement as HTMLElement;
    const branch = host.querySelector('#public-shop-branch') as HTMLSelectElement;
    expect(page.name()).toBe('Moda Andina Demo');
    expect(activeShop()).toBe('demo-moda-andina');
    expect(page.context.branch()).toBeNull();
    expect(branch.options).toHaveLength(3);
    expect(branch.options[0].textContent).toContain('Todas las sucursales');
    branch.value = '2';
    branch.dispatchEvent(new Event('change'));
    harness.detectChanges();
    expect(page.context.branch()).toBe(2);
    expect(host.textContent).toContain('La disponibilidad mostrada');
    await harness.navigateByUrl('/tienda/demo-moda-urbana', StorefrontLayout);
    harness.detectChanges();
    expect(page.context.company()).toBe('demo-moda-urbana');
    expect(page.context.branch()).toBeNull();
    expect(activeShop()).toBe('demo-moda-urbana');
  });
});
