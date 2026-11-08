import { DatePipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink, RouterOutlet } from '@angular/router';
import { CatalogApiService } from './catalog-api.service';
import { CatalogDataService } from './catalog-data.service';
import { CatalogPwaService, type CatalogPwaState } from './catalog-pwa.service';

@Component({
  selector: 'vn-catalog-layout',
  imports: [RouterLink, RouterOutlet, DatePipe],
  template: `
    <div class="catalog-shell">
      <a class="catalog-skip" href="#catalog-content">Saltar al contenido</a>
      <header class="catalog-header">
        <a class="catalog-brand" routerLink="/catalogo" aria-label="VestiNova · Catálogo">
          <span class="catalog-brand__seal" aria-hidden="true">VN</span>
          <span>VestiNova</span>
        </a>
        <nav aria-label="Navegación del catálogo">
          <a routerLink="/catalogo" [queryParams]="{ tienda: data.shop.tienda() }">Catálogo de prendas</a>
          <a routerLink="/catalogo/acciones/compra" [queryParams]="{ tienda: data.shop.tienda() }">Mi selección</a>
          <a routerLink="/catalogo/acciones/comparar" [queryParams]="{ tienda: data.shop.tienda() }">Comparar prendas</a>
          <a routerLink="/catalogo/acciones/sincronizacion" [queryParams]="{ tienda: data.shop.tienda() }">Sincronización</a>
        </nav>
      </header>
      <main id="catalog-content" class="catalog-main" tabindex="-1">
        <section class="catalog-shop-picker vn-card" aria-label="Empresa del catálogo">
          <label for="catalog-shop">Tienda que deseas consultar</label>
          <select id="catalog-shop" [value]="data.shop.tienda() || ''" (change)="chooseShop($any($event.target).value)">
            <option value="">Explorar todas las tiendas</option>
            @for (shop of shops(); track shop.slug) {
              <option [value]="shop.slug">{{ shop.nombre }}</option>
            }
          </select>
          @if (shopError(); as error) { <p role="alert">{{ error }}</p> }
          @if (data.shop.tienda()) {
            <p>Estás consultando solamente la tienda seleccionada. Su copia offline se mantiene separada.</p>
          } @else {
            <p>Selecciona una empresa para consultar su catálogo y guardar una copia propia.</p>
          }
        </section>
        <section class="catalog-download" aria-labelledby="catalog-download-title" [attr.aria-busy]="data.downloading()">
          <div>
            <h2 id="catalog-download-title">Tu catálogo sin conexión</h2>
            @if (data.saved(); as saved) {
              <p>Última descarga: <time [attr.datetime]="saved.downloadedAt">{{ saved.downloadedAt | date:'dd/MM/yyyy HH:mm':'-0400' }}</time>
                (hora de Bolivia) · {{ saved.total }} {{ saved.total === 1 ? 'prenda' : 'prendas' }}.</p>
            } @else {
              <p>Todavía no hay un catálogo descargado en este navegador.</p>
            }
          </div>
          <button class="vn-button" type="button" (click)="download()" [disabled]="data.downloading()">
            @if (data.downloading()) { <span class="vn-spinner" aria-hidden="true"></span> Descargando… }
            @else { {{ data.saved() ? 'Actualizar catálogo local' : 'Descargar catálogo' }} }
          </button>
          @if (data.downloading() && data.progress(); as progress) {
            <p class="catalog-download__message" role="status">{{ progress.received }} de {{ progress.total }} prendas recibidas. Espera la confirmación antes de desconectarte.</p>
          }
          @if (data.downloadNotice(); as message) { <p class="catalog-download__message" role="status">{{ message }}</p> }
          @if (data.downloadError(); as message) { <p class="vn-alert vn-alert--error catalog-download__message" role="alert">{{ message }}</p> }
          @if (data.storageError(); as message) { <p class="vn-alert vn-alert--error catalog-download__message" role="alert">{{ message }}</p> }
          <p class="catalog-download__message catalog-pwa-status" role="status">
            @switch (pwaState()) {
              @case ('ready') { Apertura sin conexión preparada. Conserva también una descarga del catálogo. }
              @case ('offline') { Aplicación abierta con recursos guardados. Consulta la fecha de tu copia local; no se pudo comprobar una nueva preparación sin conexión. }
              @case ('preparing') { Preparando la aplicación para abrirla sin conexión… }
              @case ('error') { No se pudo confirmar la preparación de la aplicación. Mantén la conexión y vuelve a abrir el catálogo. }
              @default { La apertura sin conexión aún no está preparada. Los datos guardados pueden consultarse mientras la aplicación permanezca abierta. }
            }
          </p>
        </section>
        <router-outlet />
      </main>
      <footer class="catalog-footer"><span>VestiNova</span><span>Catálogo de prendas</span></footer>
    </div>
  `,
  styleUrl: './catalog.css',
})
export class CatalogLayout {
  readonly data = inject(CatalogDataService);
  private readonly pwa = inject(CatalogPwaService);
  private readonly api = inject(CatalogApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  readonly shops = signal<Array<{ slug: string; nombre: string }>>([]);
  readonly shopError = signal<string | null>(null);

  constructor() {
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(params => {
      this.data.setShop(params.get('tienda'));
    });
  }

  chooseShop(tienda: string): void {
    void this.router.navigate(['/catalogo'], { queryParams: { tienda: tienda || null } });
  }
  readonly pwaState = signal<CatalogPwaState | 'preparing'>('unavailable');

  ngOnInit(): void {
    this.api.tiendas().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: shops => { this.shops.set(shops); this.shopError.set(null); },
      error: () => this.shopError.set('No pudimos actualizar las empresas disponibles.'),
    });
    void this.data.refreshSavedStatus();
    this.pwaState.set('preparing');
    void this.pwa.prepare().then(
      state => this.pwaState.set(state),
      () => this.pwaState.set('error'),
    );
  }

  download(): void { void this.data.download(); }
}
