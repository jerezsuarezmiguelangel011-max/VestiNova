import { Component, effect, inject } from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';
import { CompanyService } from '../../organizacion_empresarial/empresa/company.service';
import { CatalogDataService } from './catalog-data.service';

/**
 * CU08 dentro del panel administrativo. La empresa de trabajo determina
 * obligatoriamente el catálogo consultado; no se usan búsquedas globales.
 */
@Component({
  selector: 'vn-admin-catalog-page',
  imports: [RouterLink, RouterOutlet],
  template: `
    <section class="admin-catalog-intro" aria-labelledby="admin-catalog-title">
      <p class="catalog-eyebrow">Consulta · CU08</p>
      <h1 id="admin-catalog-title">Consultar catálogo de prendas</h1>
      <p>Prendas publicadas de <strong>{{ companies.active()?.nombre }}</strong>.
        La consulta respeta la empresa con la que estás trabajando.</p>
      <a routerLink="/catalogo" [queryParams]="{ tienda: companies.active()?.slug }"
         target="_blank" rel="noopener noreferrer">Abrir vista pública del catálogo</a>
    </section>
    <router-outlet />
  `,
  styleUrl: './catalog.css',
})
export class AdminCatalogPage {
  readonly companies = inject(CompanyService);
  private readonly catalog = inject(CatalogDataService);

  constructor() {
    // Establecer el ámbito ANTES de que el listado hijo consulte la API.
    this.catalog.setShop(this.companies.active()?.slug || 'tienda-no-disponible');
    effect(() => {
      // Si cambia la empresa activa, nunca se muestra el catálogo global.
      this.catalog.setShop(this.companies.active()?.slug || 'tienda-no-disponible');
    });
  }
}
