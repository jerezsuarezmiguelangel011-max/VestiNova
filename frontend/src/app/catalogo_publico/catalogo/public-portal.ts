import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { CatalogApiService } from './catalog-api.service';

interface PublicShop { slug: string; nombre: string; }

@Component({
  selector: 'vn-public-portal',
  imports: [RouterLink],
  template: `
    <div class="public-portal">
      <a class="public-skip" href="#public-content">Saltar al contenido</a>
      <header class="public-topbar" id="public-top">
        <a class="public-logo" routerLink="/" aria-label="VestiNova, inicio">
          <span class="public-monogram" aria-hidden="true">VN</span> VestiNova
        </a>
        <nav aria-label="Navegación principal">
          <a href="#como-funciona" (click)="jumpTo($event, 'como-funciona')">Cómo funciona</a>
          <a href="#tiendas" (click)="jumpTo($event, 'tiendas')">Explorar tiendas</a>
        </nav>
      </header>

      <main id="public-content">
        <section class="public-hero" aria-labelledby="public-title">
          <div class="public-hero-copy">
            <p class="public-eyebrow">VESTINOVA · MODA MASCULINA</p>
            <h1 id="public-title">Tu próxima prenda, <em>tu propio estilo.</em></h1>
            <p>Descubre las tiendas que forman parte de VestiNova.
              Descubre moda masculina para cada ocasión: básicos, streetwear, camisas, pantalones y accesorios. Elige tu tienda y explora su colección.</p>
            <div class="public-actions">
              <a class="public-action-main" href="#tiendas" (click)="jumpTo($event, 'tiendas')">Descubrir tiendas <span aria-hidden="true">↗</span></a>
              <a class="public-action-outline" href="#como-funciona" (click)="jumpTo($event, 'como-funciona')">Conocer VestiNova</a>
            </div>
            <div class="public-hero-note">
              <span class="public-note-line" aria-hidden="true"></span>
              Moda masculina · marcas independientes · sucursales reales.
            </div>
          </div>
          <div class="public-hero-art" aria-hidden="true">
            <div class="public-orbit public-orbit--outer"></div>
            <div class="public-orbit public-orbit--inner"></div>
            <div class="public-look-portrait"></div>
            <div class="public-hero-monogram" aria-hidden="true">VN</div>
            <div class="public-float-tag public-float-tag--one"><span>01</span> Descubre</div>
            <div class="public-float-tag public-float-tag--two"><span>02</span> Elige</div>
            <div class="public-art-caption">VESTINOVA / MENSWEAR EDITION</div>
          </div>
          <span class="public-hero-index" aria-hidden="true">VESTINOVA / 2026</span>
        </section>

        <section class="public-intro public-reveal" id="como-funciona" aria-labelledby="public-how-title">
          <div>
            <p class="public-eyebrow">ASÍ DE SENCILLO</p>
            <h2 id="public-how-title">De descubrir tu estilo a encontrar tu próxima prenda.</h2>
          </div>
          <div class="public-steps">
            <article><span>01</span><h3>Elige una tienda</h3><p>Explora las tiendas de moda masculina disponibles en VestiNova.</p></article>
            <article><span>02</span><h3>Encuentra tu prenda</h3><p>Busca por categoría, talla, color y precio. Consulta promociones.</p></article>
            <article><span>03</span><h3>Elige una sucursal</h3><p>Consulta su disponibilidad y selecciona dónde preparar tu pedido.</p></article>
          </div>
        </section>

        <section class="public-directory public-reveal" id="tiendas" aria-labelledby="public-shops-title">
          <div class="public-section-heading">
            <div>
              <p class="public-eyebrow">ENCUENTRA TU ESTILO</p>
              <h2 id="public-shops-title">Tiendas que puedes explorar</h2>
              <p>Dos estilos diferentes. Una experiencia de moda masculina.</p>
            </div>
            <span class="public-count" aria-live="polite">{{ shops().length }} {{ shops().length === 1 ? 'tienda' : 'tiendas' }}</span>
          </div>
          @if (loading()) {
            <p class="public-info" role="status">Descubriendo tiendas disponibles…</p>
          } @else if (error()) {
            <div class="public-info" role="alert">
              <p>No pudimos cargar las tiendas. Revisa la conexión.</p>
              <button type="button" (click)="loadShops()">Reintentar</button>
            </div>
          } @else if (shops().length === 0) {
            <p class="public-info">Todavía no hay tiendas disponibles para explorar.</p>
          } @else {
            <div class="public-shop-grid">
              @for (shop of shops(); track shop.slug; let i = $index) {
                <a class="public-shop-card" [routerLink]="['/tienda', shop.slug]"
                   [attr.aria-label]="'Explorar tienda ' + shop.nombre">
                  <div class="public-shop-illustration" [class.public-shop-illustration--alt]="i % 2 === 1"
                       [class.public-shop-illustration--andina]="shop.slug === 'demo-moda-andina'"
                       [class.public-shop-illustration--urbana]="shop.slug === 'demo-moda-urbana'">
                    <span class="public-shop-initial" aria-hidden="true">{{ shop.slug === 'demo-moda-andina' ? 'MA' : shop.slug === 'demo-moda-urbana' ? 'MU' : shop.nombre.charAt(0) }}</span>
                    <span class="public-shop-overlay" aria-hidden="true">COLECCIÓN PARA HOMBRE · VESTINOVA</span>
                  </div>
                  <div class="public-shop-bottom">
                    <div><span class="public-shop-number">TIENDA {{ (i + 1).toString().padStart(2, '0') }}</span><h3>{{ shop.nombre }}</h3></div>
                    <span class="public-shop-arrow" aria-hidden="true">↗</span>
                  </div>
                  <p>Explorar catálogo y sucursales</p>
                </a>
              }
            </div>
          }
        </section>

        <section class="public-closing public-reveal" aria-labelledby="public-closing-title">
          <span class="public-eyebrow">TU PRÓXIMA PRENDA TE ESPERA</span>
          <h2 id="public-closing-title">Andina o Urbana. Elige el estilo que va contigo.</h2>
          <p>Explora empresas, descubre prendas y elige la sucursal que más te convenga. Tu recorrido empieza aquí.</p>
          <a href="#tiendas" (click)="jumpTo($event, 'tiendas')">Quiero explorar tiendas <span aria-hidden="true">↗</span></a>
        </section>
      </main>
      <footer class="public-footer"><strong>VestiNova.</strong><span>Explora tiendas de moda desde un solo lugar.</span><a href="#public-top" (click)="jumpTo($event, 'public-top')">Volver arriba ↑</a></footer>
    </div>
  `,
  styleUrl: './public-portal.css',
})
export class PublicPortalPage {
  private readonly api = inject(CatalogApiService);
  private readonly destroyRef = inject(DestroyRef);
  readonly shops = signal<PublicShop[]>([]);
  readonly loading = signal(true);
  readonly error = signal(false);

  ngOnInit(): void { this.loadShops(); }

  /** Navegación accesible y visible aunque no esté configurado anchorScrolling. */
  jumpTo(event: MouseEvent, id: 'como-funciona' | 'tiendas' | 'public-content' | 'public-top'): void {
    const target = document.getElementById(id);
    if (!target) return;
    event.preventDefault();
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    target.scrollIntoView({ block: 'start', behavior: reduced ? 'instant' : 'smooth' });
    history.replaceState(history.state, '', '#' + id);
  }


  loadShops(): void {
    if (this.loading() && this.shops().length > 0) return;
    this.loading.set(true);
    this.error.set(false);
    this.api.tiendas().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        this.shops.set(result.filter(shop =>
          /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(shop.slug)
          && shop.slug !== 'vestinova-inicial'));
        this.loading.set(false);
      },
      error: () => { this.error.set(true); this.loading.set(false); },
    });
  }
}
