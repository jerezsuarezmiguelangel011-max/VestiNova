import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { describe, expect, it, vi } from 'vitest';

import { routes } from '../../app.routes';
import { CompanyService } from '../../organizacion_empresarial/empresa/company.service';
import { CatalogDataService } from './catalog-data.service';
import { AdminCatalogPage } from './admin-catalog-page';

describe('CU08: navegación desde Administración', () => {
  it('mantiene el catálogo en la empresa autorizada y muestra su nombre', async () => {
    const active = signal({ slug: 'demo-moda-andina', nombre: 'Moda Andina Demo' });
    const setShop = vi.fn();
    TestBed.configureTestingModule({
      imports: [AdminCatalogPage],
      providers: [
        provideRouter([]),
        { provide: CompanyService, useValue: { active } },
        { provide: CatalogDataService, useValue: { setShop } },
      ],
    });
    const fixture = TestBed.createComponent(AdminCatalogPage);
    fixture.detectChanges();
    expect(setShop).toHaveBeenCalledWith('demo-moda-andina');
    expect(fixture.nativeElement.textContent).toContain('Consultar catálogo de prendas');
    expect(fixture.nativeElement.textContent).toContain('Moda Andina Demo');
    const publicLink = fixture.nativeElement.querySelector('.admin-catalog-intro a') as HTMLAnchorElement;
    expect(publicLink.getAttribute('href')).toContain('tienda=demo-moda-andina');

    active.set({ slug: 'demo-moda-urbana', nombre: 'Moda Urbana Demo' });
    fixture.detectChanges();
    await fixture.whenStable();
    expect(setShop).toHaveBeenCalledWith('demo-moda-urbana');
    expect(fixture.nativeElement.textContent).toContain('Moda Urbana Demo');

    active.set({ slug: '', nombre: '' });
    fixture.detectChanges();
    await fixture.whenStable();
    expect(setShop).toHaveBeenCalledWith('tienda-no-disponible');
  });

  it('existe una ruta de listado y detalle bajo el panel administrativo', () => {
    const admin = routes.find(route => route.path === 'admin');
    const catalog = admin?.children?.find(route => route.path === 'catalogo-consulta');
    expect(catalog?.canActivate?.length).toBeGreaterThan(0);
    expect(catalog?.children?.map(route => route.path)).toEqual(['', ':slug']);
  });
});
