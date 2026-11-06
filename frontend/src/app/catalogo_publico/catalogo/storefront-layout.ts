import { Component, DestroyRef, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink, RouterOutlet } from '@angular/router';
import { CatalogApiService } from './catalog-api.service';
import { CatalogDataService } from './catalog-data.service';
import { StorefrontContextService } from './storefront-context.service';

interface StorefrontBranch { id: number; nombre: string; }

@Component({
  selector: 'vn-storefront-layout',
  imports: [RouterLink, RouterOutlet, DatePipe],
  template: `
    <div class="storefront-shell">
      <a class="storefront-skip" href="#storefront-content">Saltar al catálogo</a>
      <header class="storefront-nav">
        <a class="storefront-vn" routerLink="/" aria-label="Volver a VestiNova">
          <span aria-hidden="true">VN</span> VestiNova
        </a>
        <span class="storefront-nav-divider" aria-hidden="true"></span>
        <a class="storefront-shop-name" [routerLink]="['/tienda', slug()]">{{ name() || 'Tu tienda' }}</a>
        <nav aria-label="Navegación de la tienda">
          <a [routerLink]="['/tienda',slug()]">Prendas</a>
          <a routerLink="/catalogo/acciones/compra" [queryParams]="{ tienda: slug() }">Mi carrito</a>
          <a [routerLink]="['/tienda',slug(),'acceso']">Mi cuenta</a>
        </nav>
      </header>

      @if (loading()) {
        <main class="storefront-message" role="status">Preparando la tienda…</main>
      } @else if (error(); as message) {
        <main class="storefront-message" role="alert">
          <h1>No encontramos esta tienda</h1>
          <p>{{ message }}</p>
          <a routerLink="/">Explorar las tiendas de VestiNova</a>
        </main>
      } @else {
        @if (showHero()) {
          <section class="storefront-hero" aria-labelledby="storefront-heading">
            <div class="storefront-hero-copy">
              <p class="storefront-eyebrow">UNA TIENDA DE VESTINOVA</p>
              <h1 id="storefront-heading">{{ name() }}</h1>
              <p>Descubre sus prendas, encuentra tus favoritas y explora las promociones vigentes.</p>
              <a class="storefront-hero-link" href="#storefront-products">Explorar colección <span aria-hidden="true">↗</span></a>
            </div>
            <div class="storefront-hero-art" aria-hidden="true">
              <div class="storefront-orbit"></div>
              <div class="storefront-fashion-front"></div>
              <div class="storefront-fashion-back"></div>
              <span>{{ name() }}</span>
            </div>
          </section>
        }
        <section class="storefront-branch-bar" aria-label="Consulta por sucursal">
          <div class="storefront-branch-label">
            <span class="storefront-eyebrow">ENCUENTRA TU SUCURSAL</span>
            <strong>¿Dónde quieres consultar disponibilidad?</strong>
            <p>Puedes explorar todas las prendas sin elegir sucursal. Para comprar, será obligatorio elegir una.</p>
          </div>
          <label class="storefront-branch-control" for="public-shop-branch">
            <span>Sucursal</span>
            <select id="public-shop-branch" [value]="context.branch() ?? ''"
                    (change)="selectBranch($any($event.target).value)">
              <option value="">Todas las sucursales</option>
              @for (branch of branches(); track branch.id) {
                <option [value]="branch.id">{{ branch.nombre }}</option>
              }
            </select>
            @if (context.branch() !== null) {
              <small>La disponibilidad mostrada se consultará para esta sucursal.</small>
            }
          </label>
          @if (branchesError()) { <p class="storefront-branch-error" role="status">No pudimos actualizar las sucursales; sigue explorando el catálogo.</p> }
        </section>
        <main class="storefront-content" id="storefront-content" tabindex="-1">
          @if (showHero()) {
            <div class="storefront-products-intro" id="storefront-products">
              <p class="storefront-eyebrow">EXPLORA LA COLECCIÓN</p>
              <h2>Prendas de {{ name() }}</h2>
              <span>Precios en bolivianos · Promociones cuando estén vigentes</span>
            </div>
          }
          <router-outlet (activate)="onPageActivated()"/>
          @if (showHero()) {
            <details class="storefront-offline">
              <summary>¿Quieres consultar el catálogo sin conexión?</summary>
              @if (data.saved(); as saved) {
                <p>Última copia: <time [attr.datetime]="saved.downloadedAt">{{ saved.downloadedAt | date:'dd/MM/yyyy HH:mm':'-0400' }}</time> · {{ saved.total }} prendas.</p>
              } @else {
                <p>Aún no guardaste una copia de esta tienda.</p>
              }
              <button type="button" (click)="download()" [disabled]="data.downloading()">
                {{ data.downloading() ? 'Guardando catálogo…' : 'Descargar catálogo de esta tienda' }}
              </button>
              @if (data.downloadNotice(); as notice) { <p role="status">{{ notice }}</p> }
              @if (data.downloadError(); as message) { <p role="alert">{{ message }}</p> }
            </details>
          }
        </main>
      }
      <footer class="storefront-footer">
        <div><strong>{{ name() || 'VestiNova' }}</strong><span>Tu estilo, a tu manera.</span></div>
        <a routerLink="/">Descubrir otras tiendas</a>
        <span>Una tienda en VestiNova</span>
      </footer>
    </div>
  `,
  styleUrl: './storefront-layout.css',
})
export class StorefrontLayout {
  readonly data = inject(CatalogDataService);
  readonly context = inject(StorefrontContextService);
  private readonly api = inject(CatalogApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  readonly slug = signal('');
  readonly name = signal('');
  readonly branches = signal<StorefrontBranch[]>([]);
  readonly branchesError = signal(false);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly showHero = signal(true);
  private request = 0;

  constructor() {
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(params => {
      const slug = params.get('tienda') ?? '';
      this.slug.set(slug);
      this.name.set('');
      this.branches.set([]);
      this.branchesError.set(false);
      this.error.set(null);
      this.loading.set(true);
      const revision = ++this.request;
      if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)) {
        this.error.set('El enlace de la tienda no es válido.');
        this.loading.set(false);
        return;
      }
      this.context.selectCompany(slug);
      this.data.setShop(slug);
      this.api.tiendas().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: shops => {
          if (revision !== this.request) return;
          const company = shops.find(item => item.slug === slug);
          if (!company) {
            this.error.set('Esta empresa no está disponible en VestiNova.');
            this.loading.set(false);
            return;
          }
          this.name.set(company.nombre);
          this.loading.set(false);
          void this.data.refreshSavedStatus();
          this.api.sucursales().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
            next: branches => {
              if (revision !== this.request) return;
              this.branches.set(branches);
              this.context.selectBranch(this.context.branch(), branches.map(branch => branch.id));
            },
            error: () => { if (revision === this.request) this.branchesError.set(true); },
          });
        },
        error: () => {
          if (revision === this.request) {
            this.error.set('No se pudo verificar esta empresa. Comprueba tu conexión.');
            this.loading.set(false);
          }
        },
      });
    });
  }

  onPageActivated(): void {
    this.showHero.set(this.route.firstChild?.snapshot.routeConfig?.path === '');
  }

  selectBranch(value: string): void {
    const id = value ? Number(value) : null;
    this.context.selectBranch(id, this.branches().map(branch => branch.id));
  }

  download(): void { void this.data.download(); }
}
