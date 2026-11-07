import { Component, DestroyRef, computed, effect, inject, signal, untracked } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { CatalogApiService } from './catalog-api.service';
import { CatalogDataService } from './catalog-data.service';
import { CatalogImage } from './catalog-image';
import { CatalogShopService } from './catalog-shop.service';
import type { CatalogProduct } from './catalog.models';

interface PublicCategory { id: number; nombre: string; }

/** Escaparate de una empresa: datos auténticos de CU08, no un segundo catálogo. */
@Component({
  selector: 'vn-storefront-home',
  imports: [RouterLink, CatalogImage],
  template: `
    <div class="storefront-home">
      <section class="storefront-value" aria-label="Comprar en la tienda">
        <span>Prendas de esta empresa</span>
        <span>Promociones vigentes</span>
        <span>Retiro o entrega según tu compra</span>
      </section>

      <section id="storefront-collections" class="storefront-featured" aria-labelledby="storefront-new-title">
        <div class="storefront-home-heading">
          <div><p class="storefront-home-eyebrow">DESCUBRE LA COLECCIÓN</p>
            <h2 id="storefront-new-title">Lo último en la tienda</h2>
            <p>Una selección de las prendas publicadas recientemente.</p>
          </div>
          <a [routerLink]="['/tienda', shop.tienda(), 'catalogo']">Ver catálogo completo <span aria-hidden="true">↗</span></a>
        </div>
        @if (loading()) {
          <p class="storefront-home-state" role="status">Cargando las prendas…</p>
        } @else if (error(); as message) {
          <div class="storefront-home-state" role="alert"><p>{{ message }}</p>
            <button type="button" (click)="reload()">Volver a intentar</button>
          </div>
        } @else if (featured().length === 0) {
          <p class="storefront-home-state">Todavía no hay prendas publicadas en esta tienda.</p>
        } @else {
          @if (source() === 'local') {
            <p class="storefront-home-offline" role="status">Estás viendo una copia descargada. Conéctate antes de comprar: los precios y el stock pueden haber cambiado.</p>
          }
          <div class="storefront-featured-grid">
            @for (product of featured(); track product.id) {
              <a class="storefront-featured-card" [routerLink]="['/tienda', shop.tienda(), 'prenda', product.slug]">
                <div class="storefront-featured-image">
                  <vn-catalog-image [url]="product.imagen_url" [name]="product.nombre"/>
                  @if (product.precio_promocional) { <span class="storefront-sale-label">Oferta</span> }
                </div>
                <div class="storefront-featured-meta">
                  <span>{{ product.categoria_nombre || 'Colección' }}</span>
                  <h3>{{ product.nombre }}</h3>
                  <p>@if (product.precio_promocional) {
                    <strong>Bs {{ product.precio_promocional }}</strong>
                    <del>Bs {{ product.precio }}</del>
                  } @else { <strong>Bs {{ product.precio }}</strong> }</p>
                  <span class="storefront-featured-link">Ver prenda <span aria-hidden="true">↗</span></span>
                </div>
              </a>
            }
          </div>
        }
      </section>

      <section class="storefront-category-strip" aria-labelledby="storefront-category-title">
        <div class="storefront-home-heading">
          <div><p class="storefront-home-eyebrow">ENCUENTRA LO TUYO</p>
            <h2 id="storefront-category-title">Explora por categoría</h2>
          </div>
        </div>
        @if (categories().length === 0 && !categoriesLoading()) {
          <p>Descubre las prendas desde el catálogo completo.</p>
          <a [routerLink]="['/tienda', shop.tienda(), 'catalogo']">Ver todas las prendas ↗</a>
        } @else {
          <div class="storefront-category-grid">
            @for (category of categories(); track category.id; let i = $index) {
              <a [routerLink]="['/tienda', shop.tienda(), 'catalogo']" [queryParams]="{ categoria: category.id }"
                 class="storefront-category-item">
                <span class="storefront-category-icon" aria-hidden="true">{{ (i + 1).toString().padStart(2, '0') }}</span>
                <strong>{{ category.nombre }}</strong>
                <span aria-hidden="true">↗</span>
              </a>
            }
          </div>
        }
      </section>

      <section id="storefront-offers" class="storefront-offers" aria-labelledby="storefront-offers-title">
        <div class="storefront-home-heading">
          <div><p class="storefront-home-eyebrow">ENCUENTRA OPORTUNIDADES</p>
            <h2 id="storefront-offers-title">Promociones de la tienda</h2>
            <p>Descuentos publicados por esta empresa, cuando estén disponibles.</p>
          </div>
        </div>
        @if (loading()) {
          <p role="status">Consultando ofertas…</p>
        } @else if (offers().length === 0) {
          <div class="storefront-offers-empty">
            <p>No encontramos promociones vigentes entre las prendas consultadas. Puedes revisar el catálogo completo.</p>
            <a [routerLink]="['/tienda', shop.tienda(), 'catalogo']">Explorar el catálogo →</a>
          </div>
        } @else {
          <div class="storefront-offers-grid">
            @for (product of offers(); track product.id) {
              <a [routerLink]="['/tienda', shop.tienda(), 'prenda', product.slug]">
                <div><vn-catalog-image [url]="product.imagen_url" [name]="product.nombre"/></div>
                <span>{{ product.promocion_nombre }}</span>
                <h3>{{ product.nombre }}</h3>
                <p>Bs {{ product.precio_promocional }} <del>Bs {{ product.precio }}</del></p>
              </a>
            }
          </div>
        }
      </section>
      <section class="storefront-home-last">
        <div><p class="storefront-home-eyebrow">SIGUE EXPLORANDO</p>
          <h2>Tu próxima prenda puede estar aquí.</h2>
          <p>Consulta colores, tallas y sucursales antes de decidir.</p>
        </div>
        <a [routerLink]="['/tienda', shop.tienda(), 'catalogo']">Ver todas las prendas ↗</a>
      </section>
    </div>
  `,
  styleUrl: './storefront-home.css',
})
export class StorefrontHomePage {
  readonly shop = inject(CatalogShopService);
  private readonly api = inject(CatalogApiService);
  private readonly data = inject(CatalogDataService);
  private readonly destroyRef = inject(DestroyRef);
  readonly products = signal<CatalogProduct[]>([]);
  readonly categories = signal<PublicCategory[]>([]);
  readonly categoriesLoading = signal(true);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly source = signal<'network' | 'local' | null>(null);
  readonly featured = computed(() => this.products().slice(0, 6));
  readonly offers = computed(() => this.products().filter(item => item.precio_promocional).slice(0, 4));
  private requestId = 0;

  constructor() {
    effect(() => {
      const slug = this.shop.tienda();
      this.data.revision();
      if (!slug) return;
      untracked(() => this.load(slug));
    });
  }
  reload(): void {
    const slug = this.shop.tienda();
    if (slug) this.load(slug);
  }

  private load(slug: string): void {
    const version = ++this.requestId;
    this.loading.set(true);
    this.categoriesLoading.set(true);
    this.error.set(null);
    this.products.set([]);
    this.categories.set([]);
    this.data.list({ limit: 100, offset: 0 }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        if (version !== this.requestId || this.shop.tienda() !== slug) return;
        this.products.set(result.data.items);
        this.source.set(result.source);
        this.loading.set(false);
      },
      error: () => {
        if (version !== this.requestId || this.shop.tienda() !== slug) return;
        this.error.set('No pudimos cargar la colección. Comprueba tu conexión.');
        this.loading.set(false);
      },
    });
    this.api.categorias().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: categories => {
        if (version !== this.requestId || this.shop.tienda() !== slug) return;
        this.categories.set(categories);
        this.categoriesLoading.set(false);
      },
      error: () => {
        if (version === this.requestId && this.shop.tienda() === slug) this.categoriesLoading.set(false);
      },
    });
  }
}
