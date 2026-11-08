import { DatePipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { CustomerWishlistApi, type WishlistItem } from './customer-wishlist-api.service';
import { CatalogImage } from '../../catalogo_publico/catalogo/catalog-image';

@Component({
  selector: 'vn-customer-wishlist',
  imports: [RouterLink, DatePipe, CatalogImage],
  template: `
  <main class="wish-page">
    <a [routerLink]="['/tienda', tienda(), 'catalogo']">← Volver a la tienda</a>
    <p class="wish-tag">VestiNova · CU23</p>
    <h1>Mi lista de deseos</h1>
    <p>Estas variantes están guardadas en tu cuenta de esta tienda.
       Guardarlas no reserva stock ni congela el precio.</p>
    @if (loading()) { <p role="status">Cargando tu lista…</p> }
    @if (error(); as message) { <p class="wish-error" role="alert">{{ message }}</p> }
    @if (notice(); as message) { <p class="wish-notice" role="status">{{ message }}</p> }
    <div class="wish-grid">
      @for (item of items(); track item.variante_id) {
        <article class="wish-item">
          <vn-catalog-image [url]="item.imagen_url" [name]="item.nombre" />
          <div class="wish-body">
            <h2>{{ item.nombre }}</h2>
            <p>Talla {{ item.talla }} · {{ item.color }}</p>
            @if (item.publicada) {
              <p><strong>Bs {{ item.precio_vigente }}</strong> (precio consultado en línea)</p>
              @switch (item.disponibilidad) {
                @case ('DISPONIBLE_REFERENCIAL') { <p class="wish-stock">Hay unidades conocidas en alguna sucursal; verificar antes de comprar.</p> }
                @case ('AGOTADA') { <p class="wish-inactive">Sin unidades disponibles según las sucursales consultadas.</p> }
                @default { <p class="wish-stock">Disponibilidad no verificada.</p> }
              }
              <a [routerLink]="['/tienda', tienda(), 'prenda', item.slug]">Ver prenda</a>
            } @else {
              <p class="wish-inactive">Variante no disponible actualmente.</p>
            }
            <p class="wish-date">Guardada {{ item.creado_en | date:'dd/MM/yyyy HH:mm':'-0400' }}</p>
            <button type="button" (click)="remove(item)"
              [disabled]="busy() === item.variante_id">
              {{ busy() === item.variante_id ? 'Quitando…' : 'Eliminar de mi lista' }}
            </button>
          </div>
        </article>
      } @empty {
        @if (!loading() && !error()) {
          <p>Todavía no tienes prendas guardadas. Explora el catálogo y elige una talla y color.</p>
        }
      }
    </div>
  </main>
  `,
  styles: `
    :host{display:block}.wish-page{max-width:1050px;margin:0 auto;padding:30px;color:#27382e}
    .wish-page h1{font:400 42px Georgia,serif}.wish-page>p{line-height:1.65}
    .wish-tag{font-weight:700;color:#116a4d;font-size:11px;letter-spacing:.1em;text-transform:uppercase}
    .wish-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:18px;margin-top:24px}
    .wish-item{border:1px solid #d9e4d9;background:#fff;border-radius:12px;overflow:hidden}
    .wish-item vn-catalog-image{display:block;height:180px;background:#e8eee4}
    .wish-body{padding:20px}.wish-body h2{font:400 25px Georgia,serif;margin:0 0 10px}
    .wish-body p{font-size:14px}.wish-body a{color:#176b4b;display:inline-block;margin:10px 0}
    .wish-body button{display:block;border-radius:7px;border:1px solid #b6d0bd;background:#edf6ef;color:#245b3f;cursor:pointer;min-height:42px;padding:10px}
    .wish-body button:disabled{opacity:.5}.wish-date{color:#6c7a6e;font-size:12px!important}
    .wish-error{padding:12px;background:#fff0f0;color:#a02735}
    .wish-notice{padding:12px;background:#ebf5ed;color:#176b4b}
    .wish-inactive{color:#a02735}.wish-stock{color:#486b55}
  `,
})
export class CustomerWishlistPage {
  private readonly api = inject(CustomerWishlistApi);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  readonly tienda = signal('');
  readonly items = signal<WishlistItem[]>([]);
  readonly loading = signal(false);
  readonly busy = signal<number | null>(null);
  readonly error = signal<string | null>(null);
  readonly notice = signal<string | null>(null);

  private revision = 0;

  constructor() {
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(params => {
      this.revision++;
      this.tienda.set(params.get('tienda') ?? '');
      this.items.set([]);
      this.busy.set(null);
      this.notice.set(null);
      this.load();
    });
  }

  load(): void {
    const tienda = this.tienda();
    if (!tienda) return;
    const revision = this.revision;
    this.loading.set(true);
    this.error.set(null);
    this.api.list(tienda).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => { if (revision === this.revision) {
        this.items.set(result.items); this.loading.set(false);
      } },
      error: () => { if (revision === this.revision) {
        this.error.set('No pudimos recuperar tu lista. Inicia sesión y revisa la conexión.');
        this.loading.set(false);
      } },
    });
  }

  remove(item: WishlistItem): void {
    if (this.busy() !== null) return;
    const revision = this.revision;
    const tienda = this.tienda();
    this.busy.set(item.variante_id); this.error.set(null); this.notice.set(null);
    this.api.remove(tienda, item.variante_id).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => { if (revision === this.revision) {
        this.items.update(items => items.filter(row => row.variante_id !== item.variante_id));
        this.busy.set(null); this.notice.set('Prenda retirada de tu lista.');
      } },
      error: () => { if (revision === this.revision) {
        this.busy.set(null);
        this.error.set('No se pudo retirar esta prenda. Comprueba tu conexión e inténtalo nuevamente.');
      } },
    });
  }
}
