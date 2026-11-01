import { DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';
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
          <a routerLink="/catalogo">Catálogo de prendas</a>
          <a routerLink="/catalogo/acciones/compra">Mi selección</a>
          <a routerLink="/catalogo/acciones/sincronizacion">Sincronización</a>
        </nav>
      </header>
      <main id="catalog-content" class="catalog-main" tabindex="-1">
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
  readonly pwaState = signal<CatalogPwaState | 'preparing'>('unavailable');

  ngOnInit(): void {
    void this.data.refreshSavedStatus();
    this.pwaState.set('preparing');
    void this.pwa.prepare().then(
      state => this.pwaState.set(state),
      () => this.pwaState.set('error'),
    );
  }

  download(): void { void this.data.download(); }
}
