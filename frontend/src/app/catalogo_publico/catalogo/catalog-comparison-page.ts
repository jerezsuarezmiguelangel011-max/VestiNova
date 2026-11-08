import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { CatalogComparisonService, type ComparisonResult } from './catalog-comparison.service';

@Component({
  selector: 'vn-comparison-page',
  imports: [RouterLink],
  template: `
    <section class="vn-comparison" aria-labelledby="comparison-title">
      <p class="catalog-eyebrow">VestiNova · CU24</p>
      <h1 id="comparison-title">Comparar prendas</h1>
      <p>Compara entre dos y cuatro prendas de una misma tienda. Los precios y saldos se consultan al servidor; no se reservan unidades.</p>
      @if (comparison.shop.tienda(); as tienda) {
        <p>Selección: {{ comparison.count() }} de 4 prendas.</p>
        <div class="vn-comparison__selection">
          @for (item of comparison.items(); track item.id) {
            <div class="vn-comparison__selection-item">
              <strong>{{ item.nombre }}</strong>
              <button type="button" class="vn-button" (click)="remove(item.id)" [attr.aria-label]="'Retirar ' + item.nombre">Retirar</button>
            </div>
          } @empty { <p>Selecciona prendas desde el catálogo de esta tienda.</p> }
        </div>
        <div class="vn-comparison__actions">
          <a class="vn-button" [routerLink]="inStorefront ? ['/tienda', tienda, 'catalogo'] : ['/catalogo']"
             [queryParams]="inStorefront ? null : { tienda }">Elegir prendas</a>
          <button type="button" class="vn-button vn-button--primary" [disabled]="comparison.count() < 2 || loading()"
                  (click)="reload()">{{ loading() ? 'Consultando…' : 'Comparar selección' }}</button>
        </div>
        @if (comparison.count() < 2) { <p role="status">Selecciona por lo menos dos prendas diferentes para comparar.</p> }
        @if (error(); as message) { <p class="vn-alert vn-alert--error" role="alert">{{ message }}</p> }
        @if (result(); as data) {
          <p role="status">Datos consultados: {{ data.consultado_en }}. Disponibilidad referencial, sujeta a cambios.</p>
          <div class="vn-comparison__scroll" role="region" tabindex="0" aria-label="Tabla comparativa de prendas">
            <table class="vn-comparison__table">
              <thead><tr><th scope="col">Característica</th>
                @for (product of data.items; track product.id) { <th scope="col">{{ product.nombre }}</th> }
              </tr></thead>
              <tbody>
                <tr><th scope="row">Categoría</th>@for (p of data.items; track p.id) { <td>{{ p.categoria_nombre || 'No disponible' }}</td> }</tr>
                <tr><th scope="row">Precio vigente</th>@for (p of data.items; track p.id) {
                  <td>Bs {{ p.precio_promocional || p.precio }} @if (p.precio_promocional) { <small>Oferta · antes Bs {{ p.precio }}</small> }</td>
                }</tr>
                <tr><th scope="row">Descripción</th>@for (p of data.items; track p.id) { <td>{{ p.descripcion || 'No disponible' }}</td> }</tr>
                <tr><th scope="row">Material</th>@for (p of data.items; track p.id) { <td>{{ p.material || 'No disponible' }}</td> }</tr>
                <tr><th scope="row">Medidas</th>@for (p of data.items; track p.id) { <td>{{ p.medidas || 'No disponible' }}</td> }</tr>
                <tr><th scope="row">Temporada</th>@for (p of data.items; track p.id) { <td>{{ p.temporada || 'No disponible' }}</td> }</tr>
                <tr><th scope="row">Tallas, colores y existencias</th>@for (p of data.items; track p.id) {
                  <td>
                    @for (v of p.variantes; track v.id) {
                      <div class="vn-comparison__variant"><strong>{{ v.talla }} / {{ v.color }}</strong>
                        @for (s of v.sucursales; track s.sucursal_id) {
                          <small>{{ s.sucursal }}:
                            {{ s.estado === 'DISPONIBLE' ? 'Disponible según registro' :
                              s.estado === 'AGOTADO' ? 'Agotado según registro' : 'No verificado' }}</small>
                        } @empty { <small>Disponibilidad por sucursal no disponible</small> }
                      </div>
                    } @empty { <span>No disponible</span> }
                  </td>
                }</tr>
                <tr><th scope="row">Ficha</th>@for (p of data.items; track p.id) {
                  <td><a [routerLink]="inStorefront ? ['/tienda', tienda, 'prenda', p.slug] : ['/catalogo', p.slug]"
                         [queryParams]="inStorefront ? null : { tienda }">Ver detalle</a></td>
                }</tr>
              </tbody>
            </table>
          </div>
        }
      } @else { <p role="alert">Selecciona una tienda antes de utilizar la comparación.</p> }
    </section>
  `,
  styles: [`
    .vn-comparison { padding: 1.2rem; max-width: 100%; }
    .vn-comparison__selection,.vn-comparison__actions { display:flex;flex-wrap:wrap;gap:.65rem;margin:1rem 0 }
    .vn-comparison__selection-item { display:flex;align-items:center;gap:.75rem;padding:.7rem;border:1px solid #ccd3df;border-radius:.65rem }
    .vn-comparison__scroll { max-width:100%;overflow-x:auto;margin:1.5rem 0 }
    .vn-comparison__table { border-collapse:collapse;min-width:640px;width:100%;background:#fff;color:#182236 }
    .vn-comparison__table th,.vn-comparison__table td { border:1px solid #d7dee8;text-align:left;vertical-align:top;padding:.8rem;min-width:160px }
    .vn-comparison__table th:first-child { min-width:130px }
    .vn-comparison__variant { padding:.35rem 0;border-bottom:1px solid #e6eaf0 }
    .vn-comparison__variant small { display:block;margin-top:.2rem }
  `],
})
export class CatalogComparisonPage {
  readonly comparison = inject(CatalogComparisonService);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  readonly inStorefront = this.route.parent?.snapshot.routeConfig?.path === 'tienda/:tienda';
  readonly result = signal<ComparisonResult | null>(null);
  readonly error = signal<string | null>(null);
  readonly loading = signal(false);
  private request = 0;

  ngOnInit(): void {
    if (this.comparison.count() >= 2) this.reload();
  }

  reload(): void {
    const revision = ++this.request;
    this.result.set(null);
    this.error.set(null);
    if (this.comparison.count() < 2) return;
    this.loading.set(true);
    this.comparison.compare().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: data => {
        if (revision !== this.request || data.tienda !== this.comparison.shop.tienda()) return;
        this.result.set(data);
        this.loading.set(false);
      },
      error: (error: unknown) => {
        if (revision !== this.request) return;
        this.loading.set(false);
        this.error.set(error instanceof HttpErrorResponse && error.status === 409
          ? 'Algunas prendas ya no están publicadas en esta tienda. Retíralas y vuelve a seleccionarlas.'
          : 'No pudimos consultar datos actuales. Comprueba tu conexión y vuelve a intentarlo.');
      },
    });
  }

  remove(id: number): void {
    this.comparison.remove(id);
    this.result.set(null);
    this.error.set(null);
    if (this.comparison.count() >= 2) this.reload();
    else { ++this.request; this.loading.set(false); }
  }
}
