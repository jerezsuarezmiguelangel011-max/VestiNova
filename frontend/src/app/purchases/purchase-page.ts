import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Subject, catchError, distinctUntilChanged, map, of, startWith, switchMap } from 'rxjs';
import { CatalogDataService } from '../catalog/catalog-data.service';
import { CatalogImage } from '../catalog/catalog-image';
import { CatalogLocalError } from '../catalog/catalog.models';
import { PurchaseApiService, type PurchaseCapabilities, type PurchaseReceipt } from './purchase-api.service';
import { PurchaseSelectionService, validPurchaseQuantity } from './purchase-selection.service';

@Component({
  selector: 'vn-purchase-page',
  imports: [RouterLink, CatalogImage, DatePipe],
  template: `
    <section class="purchase-page" aria-labelledby="purchase-title">
      <a class="purchase-back" [routerLink]="sending() ? null : '/catalogo'" [attr.aria-disabled]="sending()">← Volver al catálogo</a>
      <header class="purchase-heading">
        <p class="purchase-eyebrow">VestiNova · CU09 · Compra digital</p>
        <h1 id="purchase-title">Preparar compra</h1>
        <p>Reúne las prendas que elegiste y revisa sus cantidades.</p>
      </header>

      @if (receipt(); as confirmed) {
        <section class="purchase-receipt" aria-labelledby="purchase-confirmed-title" role="status">
          <p class="purchase-eyebrow">Comprobante de compra</p>
          <h2 id="purchase-confirmed-title">Compra confirmada</h2>
          <p class="purchase-receipt-id">Registro: {{ confirmed.id }}</p>
          <p><time [attr.datetime]="confirmed.creado_en">{{ confirmed.creado_en | date:'dd/MM/yyyy HH:mm':'-0400' }}</time> · Hora de Bolivia</p>
          <ul class="purchase-receipt-items">
            @for (item of confirmed.items; track item.producto_id) {
              <li><strong>{{ item.nombre }}</strong><span>{{ item.cantidad }} × Bs {{ item.precio_unitario }}</span><span>Subtotal: Bs {{ item.subtotal }}</span></li>
            }
          </ul>
          <p class="purchase-total">Total confirmado <strong>Bs {{ confirmed.total }} <small>{{ confirmed.moneda }}</small></strong></p>
          <a class="vn-button" routerLink="/catalogo">Seguir explorando</a>
        </section>
      } @else {
        <div class="purchase-grid">
          <section class="purchase-selection" aria-labelledby="purchase-selection-title" [attr.aria-busy]="productLoading()">
            <h2 id="purchase-selection-title">Prendas elegidas</h2>
            @if (productLoading()) { <p class="purchase-status" role="status">Cargando la prenda del catálogo…</p> }
            @if (productError(); as message) {
              <div class="purchase-load-error"><p class="vn-alert vn-alert--error" role="alert">{{ message }}</p><button class="vn-button" type="button" (click)="retryProduct()" [disabled]="productLoading() || sending()">Reintentar</button></div>
            }
            @if (lines().length === 0 && !productLoading()) {
              <div class="purchase-empty"><p>Todavía no elegiste prendas.</p><a class="vn-button" routerLink="/catalogo">Explorar catálogo</a></div>
            }
            <ul class="purchase-lines">
              @for (line of lines(); track line.product.id) {
                <li class="purchase-line">
                  <div class="purchase-image"><vn-catalog-image [url]="line.product.imagen_url" [name]="line.product.nombre" /></div>
                  <div class="purchase-line-content">
                    <h3>{{ line.product.nombre }}</h3>
                    <p class="purchase-price">Precio unitario referencial: <strong>Bs {{ line.product.precio }}</strong> <small>BOB</small></p>
                    @if (line.source === 'local') {
                      <p class="purchase-local">Precio de una copia local; puede estar desactualizado.
                        @if (line.downloadedAt) { <span>Descarga: {{ line.downloadedAt | date:'dd/MM/yyyy HH:mm':'-0400' }} (hora de Bolivia).</span> }
                      </p>
                    }
                    <label class="purchase-quantity" [for]="'purchase-quantity-' + line.product.id">Cantidad
                      <input [id]="'purchase-quantity-' + line.product.id" type="number" min="1" max="2147483647" step="1" inputmode="numeric"
                        [value]="line.cantidad" (input)="updateQuantity(line.product.id, $any($event.target).value)" [disabled]="sending()"
                        [attr.aria-invalid]="!quantityValid(line.cantidad)" [attr.aria-describedby]="!quantityValid(line.cantidad) ? 'purchase-quantity-error-' + line.product.id : null" />
                    </label>
                    @if (!quantityValid(line.cantidad)) { <p class="vn-field__error" [id]="'purchase-quantity-error-' + line.product.id">Ingresa una cantidad entera mayor a cero.</p> }
                    <button class="purchase-remove" type="button" (click)="remove(line.product.id)" [disabled]="sending()" [attr.aria-label]="'Quitar ' + line.product.nombre">Quitar prenda</button>
                  </div>
                </li>
              }
            </ul>
            @if (lines().length > 0) { <a class="purchase-back" [routerLink]="sending() ? null : '/catalogo'" [attr.aria-disabled]="sending()">Añadir otra prenda desde el catálogo →</a> }
          </section>

          <aside class="purchase-summary" aria-labelledby="purchase-summary-title" [attr.aria-busy]="capabilitiesLoading() || sending()">
            <p class="purchase-eyebrow">El siguiente paso</p>
            <h2 id="purchase-summary-title">Revisa tu selección</h2>
            <p>Los precios del catálogo son referenciales. La disponibilidad y el importe final se verificarán antes de confirmar.</p>
            @if (capabilitiesLoading()) { <p role="status">Comprobando disponibilidad de compras…</p> }
            @if (capabilities(); as capabilities) {
              @if (!capabilities.habilitado) {
                <div class="purchase-dependency" role="status"><strong>Compra no disponible</strong><p>{{ capabilities.detail }}</p></div>
              }
            }
            @if (capabilitiesError(); as message) { <p class="vn-alert vn-alert--error" role="alert">{{ message }}</p> }
            @if (!capabilitiesLoading() && !sending() && capabilities()?.habilitado !== true) { <button class="vn-button" type="button" (click)="checkCapabilities()">Volver a comprobar</button> }
            @if (submitError(); as message) { <p class="vn-alert vn-alert--error" role="alert">{{ message }}</p> }
            <button class="vn-button vn-button--primary purchase-confirm" type="button" (click)="confirm()" [disabled]="!canConfirm()" [attr.aria-busy]="sending()">
              {{ sending() ? 'Confirmando…' : 'Confirmar compra' }}
            </button>
          </aside>
        </div>
      }
    </section>
  `,
  styles: `
    :host{display:block;min-width:0}.purchase-page{color:var(--vn-text,#24332c)}.purchase-back{display:inline-flex;align-items:center;min-height:44px;margin-bottom:22px;font-size:13px;text-underline-offset:4px}.purchase-back[aria-disabled=true]{pointer-events:none;opacity:.6}.purchase-heading{margin-bottom:30px}.purchase-eyebrow{margin:0 0 12px;color:var(--vn-emerald,#116149);font-size:11px;font-weight:700;letter-spacing:.13em;text-transform:uppercase}.purchase-heading h1{margin:0;color:var(--vn-coal,#202a25);font:400 clamp(34px,5vw,52px)/1.15 var(--vn-serif,Georgia);letter-spacing:-.04em}.purchase-heading>p:last-child{color:var(--vn-muted,#59685f);line-height:1.8}.purchase-grid{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(280px,1fr);gap:28px;align-items:start}.purchase-selection h2,.purchase-summary h2{margin:0 0 20px;font:400 27px/1.2 var(--vn-serif,Georgia);letter-spacing:-.025em}.purchase-lines{display:grid;gap:18px;margin:0;padding:0;list-style:none}.purchase-line{display:grid;grid-template-columns:110px minmax(0,1fr);gap:22px;padding:20px;border:1px solid var(--vn-line,#d8ded5);border-radius:10px;background:var(--vn-white,#fff)}.purchase-image{height:180px;overflow:hidden;border-radius:6px;background:#edf0e8}.purchase-line-content{min-width:0}.purchase-line h3{margin:3px 0 14px;font:400 24px/1.2 var(--vn-serif,Georgia);overflow-wrap:anywhere}.purchase-price{margin:0 0 18px;color:var(--vn-muted,#59685f);font-size:12px;line-height:1.8}.purchase-price strong{color:var(--vn-emerald,#116149);font-weight:600}.purchase-price small{font-size:10px}.purchase-local{font-size:12px;line-height:1.7;color:var(--vn-muted,#59685f)}.purchase-local span{display:block}.purchase-quantity{display:grid;gap:7px;width:100px;font-size:12px;font-weight:600}.purchase-quantity input{width:100%;min-height:44px;padding:9px 12px;border:1px solid #aebfb3;border-radius:6px;background:#fff;color:var(--vn-text,#24332c)}.purchase-remove{min-height:44px;margin-top:8px;padding:8px 0;border:0;background:transparent;color:var(--vn-emerald,#116149);font-size:12px;text-decoration:underline;text-underline-offset:4px;cursor:pointer}.purchase-summary,.purchase-receipt{padding:28px;border:1px solid var(--vn-line,#d8ded5);border-radius:12px;background:var(--vn-white,#fff)}.purchase-summary>p:not(.purchase-eyebrow){font-size:13px;line-height:1.8;color:var(--vn-muted,#59685f)}.purchase-summary>.vn-button{margin-top:12px}.purchase-confirm{width:100%;justify-content:center}.purchase-dependency{margin-block:20px;padding:16px;border:1px solid #cbdcce;border-radius:7px;background:var(--vn-soft,#eaf2ec);font-size:13px;line-height:1.8}.purchase-dependency p{margin:8px 0 0}.purchase-empty{padding:32px 22px;border:1px solid var(--vn-line,#d8ded5);border-radius:10px;background:var(--vn-white,#fff)}.purchase-empty p,.purchase-status{color:var(--vn-muted,#59685f);line-height:1.8}.purchase-load-error{margin-bottom:18px}.purchase-receipt{max-width:850px}.purchase-receipt h2{margin:0;font:400 36px/1.2 var(--vn-serif,Georgia);letter-spacing:-.03em}.purchase-receipt>p:not(.purchase-eyebrow){font-size:13px;line-height:1.8}.purchase-receipt-id{overflow-wrap:anywhere}.purchase-receipt-items{display:grid;gap:16px;margin:28px 0;padding:0;list-style:none}.purchase-receipt-items li{display:grid;gap:7px;padding-bottom:18px;border-bottom:1px solid var(--vn-line,#d8ded5);font-size:13px}.purchase-total{display:flex;flex-wrap:wrap;gap:14px;align-items:center;justify-content:space-between}.purchase-total strong{color:var(--vn-emerald,#116149);font-size:24px;font-weight:600;font-variant-numeric:tabular-nums}.purchase-total small{font-size:12px;font-weight:400}:is(a,button,input):focus-visible{outline:3px solid var(--vn-emerald,#116149);outline-offset:3px}@media(max-width:800px){.purchase-grid{grid-template-columns:1fr}.purchase-summary{padding:22px}}@media(max-width:480px){.purchase-line{grid-template-columns:90px minmax(0,1fr);gap:14px;padding:16px}.purchase-line h3{font-size:21px}.purchase-receipt{padding:22px}}
  `,
})
export class PurchasePage {
  private readonly catalog = inject(CatalogDataService);
  private readonly api = inject(PurchaseApiService);
  private readonly selection = inject(PurchaseSelectionService);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  private readonly productRetries = new Subject<void>();
  readonly lines = this.selection.lines;
  readonly capabilities = signal<PurchaseCapabilities | null>(null);
  readonly capabilitiesLoading = signal(true);
  readonly capabilitiesError = signal<string | null>(null);
  readonly productLoading = signal(false);
  readonly productError = signal<string | null>(null);
  readonly sending = signal(false);
  readonly submitError = signal<string | null>(null);
  readonly receipt = signal<PurchaseReceipt | null>(null);
  readonly canConfirm = computed(() => this.capabilities()?.habilitado === true && !this.capabilitiesLoading()
    && !this.productLoading() && !this.sending() && this.selection.valid() && !this.receipt());
  readonly quantityValid = validPurchaseQuantity;

  constructor() {
    this.route.queryParamMap.pipe(
      map(params => params.get('slug')),
      distinctUntilChanged(),
      switchMap(slug => this.productRetries.pipe(startWith(undefined), switchMap(() => {
        this.productError.set(null);
        this.productLoading.set(Boolean(slug));
        if (!slug) return of(null);
        return this.catalog.get(slug).pipe(catchError((error: unknown) => {
          this.productError.set(error instanceof CatalogLocalError ? error.message
            : error instanceof HttpErrorResponse && error.status === 404 ? 'No encontramos esta prenda en el catálogo.'
              : 'No se pudo cargar la prenda. Comprueba la conexión e inténtalo nuevamente.');
          return of(null);
        }));
      }))),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe(response => {
      this.productLoading.set(false);
      if (response && !this.sending()) {
        this.selection.add(response);
        this.receipt.set(null);
        this.submitError.set(null);
      }
    });
    this.checkCapabilities();
  }

  checkCapabilities(): void {
    if (this.sending()) return;
    this.capabilitiesLoading.set(true);
    this.capabilitiesError.set(null);
    this.api.capabilities().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: capabilities => { this.capabilities.set(capabilities); this.capabilitiesLoading.set(false); },
      error: () => {
        this.capabilities.set(null);
        this.capabilitiesLoading.set(false);
        this.capabilitiesError.set('No se pudo verificar la disponibilidad de compras. Comprueba la conexión e inténtalo nuevamente.');
      },
    });
  }

  retryProduct(): void { if (!this.productLoading() && !this.sending()) this.productRetries.next(); }

  updateQuantity(id: number, cantidad: string): void {
    if (this.sending()) return;
    this.selection.updateQuantity(id, cantidad);
    this.submitError.set(null);
  }

  remove(id: number): void {
    if (this.sending()) return;
    this.selection.remove(id);
    this.submitError.set(null);
  }

  confirm(): void {
    if (!this.canConfirm()) return;
    const command = this.selection.command();
    if (!command) return;
    this.sending.set(true);
    this.submitError.set(null);
    this.api.create(command).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: receipt => {
        this.receipt.set(receipt);
        this.selection.clear();
        this.sending.set(false);
      },
      error: (error: unknown) => {
        const status = error instanceof HttpErrorResponse ? error.status : undefined;
        this.submitError.set(status === 503
          ? 'La compra no se pudo confirmar porque falta una dependencia del sistema. Tu selección se conserva.'
          : status === 401 || status === 403 ? 'Necesitas un acceso de cliente autorizado para confirmar la compra.'
            : status === 409 ? 'No se pudo confirmar la compra. Revisa las prendas y cantidades antes de volver a intentarlo.'
              : status === 0 ? 'No pudimos comprobar la compra por un fallo de conexión. Conservamos la selección para que vuelvas a intentarlo.'
                : 'No se pudo verificar la confirmación de compra. Tu selección se conserva; inténtalo nuevamente.');
        this.sending.set(false);
      },
    });
  }
}
