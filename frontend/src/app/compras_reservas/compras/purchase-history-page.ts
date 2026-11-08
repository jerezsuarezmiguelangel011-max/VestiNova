import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectorRef, Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';
import { CustomerAuthService } from '../clientes/customer-auth.service';
import { CustomerPurchasesService } from './customer-purchases.service';
import { type AfterSaleRequest, type AfterSaleType, type PurchaseHistoryItem } from './customer-purchases.service';

@Component({
  selector: 'vn-purchase-history-page',
  imports: [RouterLink, DatePipe],
  template: `
    <main class="customer-shell purchase-history" aria-labelledby="history-title" [attr.aria-busy]="loading()">
      <div class="customer-brand"><span aria-hidden="true">VN</span> VestiNova</div>
      <section class="customer-card vn-card">
        <a class="purchase-history__back" [routerLink]="['/tienda', slug(), 'cuenta']">← Volver a mi cuenta</a>
        @if (auth.customer(); as customer) {
          <p class="vn-eyebrow">{{ customer.empresa.nombre }}</p>
          <h1 id="history-title" class="vn-title">Mis compras</h1>
          <p class="purchase-history__intro">Consulta tus compras confirmadas, comprobantes y solicitudes de cambio o devolución.</p>
          <div class="account-history-links">
            <a class="vn-button" [routerLink]="['/tienda',slug(),'valoraciones']">Mis valoraciones · CU25</a>
            <a class="vn-button" [routerLink]="['/tienda',slug(),'alertas']">Mis alertas · CU26</a>
          </div>
        }

        @if (loading()) {
          <p role="status">Cargando tu historial…</p>
        } @else if (error(); as message) {
          <p class="vn-alert vn-alert--error" role="alert">{{ message }}</p>
          <button type="button" class="vn-button" (click)="reload()">Reintentar</button>
        } @else if (purchases().length === 0) {
          <div class="purchase-history__empty" role="status">
            <h2>Aún no hay compras registradas</h2>
            <p>Las compras confirmadas desde esta cuenta aparecerán aquí.</p>
            <a class="vn-button vn-button--primary" routerLink="/catalogo">Ver catálogo</a>
          </div>
        } @else {
          <div class="purchase-history__list">
            @for (purchase of purchases(); track purchase.id) {
              <article class="purchase-history__card" [class.purchase-history__card--printing]="printingPurchaseId() === purchase.id" [attr.aria-labelledby]="'purchase-' + purchase.id">
                <header class="purchase-history__header">
                  <div>
                    <p class="vn-eyebrow">Compra confirmada</p>
                    <h2 [id]="'purchase-' + purchase.id">{{ purchase.creado_en | date:'dd/MM/yyyy HH:mm':'-0400' }} (hora de Bolivia)</h2>
                    <p class="purchase-history__id">Comprobante {{ purchase.id }}</p>
                  </div>
                  <strong>Bs {{ purchase.importe_total }}</strong>
                </header>

                <p class="purchase-history__status" role="status">Compra confirmada · Entrega: {{ purchase.seguimiento_entrega === 'ENTREGADA' ? 'confirmada por la sucursal' : 'pendiente de verificación' }}.</p>
                <details class="purchase-history__receipt">
                  <summary>Ver comprobante y prendas</summary>
                  <ul>
                    @for (line of purchase.items; track line.producto_id) {
                      <li>
                        <span><strong>{{ line.nombre }}</strong><small>Variante {{ line.variante_id }} · {{ line.cantidad }} unidad(es)</small></span>
                        <span>Bs {{ line.subtotal }}</span>
                      </li>
                    }
                  </ul>
                  <p class="purchase-history__receipt-total">Total registrado: Bs {{ purchase.importe_total }} {{ purchase.moneda }}</p>
                      <button class="vn-button" type="button" (click)="printReceipt(purchase.id)">Imprimir o guardar comprobante</button>
                </details>

                <div class="purchase-history__requests">
                  <h3>Cambios y devoluciones</h3>
                  @for (request of requestsFor(purchase.id); track request.id) {
                    <div class="purchase-history__request" role="status">
                      <strong>{{ request.tipo === 'CAMBIO' ? 'Cambio' : 'Devolución' }} · {{ statusLabel(request.estado) }}</strong>
                      <p>{{ request.motivo }}</p>
                      @if (request.referencia_reposicion) { <p>Nota de reposición: <strong>{{ request.referencia_reposicion }}</strong></p> }
                      @if (request.respuesta) { <p>Respuesta de la sucursal: {{ request.respuesta }}</p> }
                      @for (line of request.items; track line.producto_id) {
                        <small>{{ line.nombre }} · {{ line.cantidad }} unidad(es)</small>
                      }
                    </div>
                  } @empty {
                    <p class="purchase-history__muted">No tienes solicitudes asociadas a esta compra.</p>
                  }
                  <button class="vn-button" type="button" (click)="toggleRequest(purchase)" [disabled]="sending()">
                    {{ activePurchaseId() === purchase.id ? 'Cerrar solicitud' : 'Solicitar cambio o devolución' }}
                  </button>

                  @if (activePurchaseId() === purchase.id) {
                    <form class="purchase-history__form" (submit)="submitRequest($event, purchase)">
                      <label class="vn-field">Tipo de solicitud
                        <select [value]="requestType()" (change)="changeType($event)">
                          <option value="DEVOLUCION">Devolución</option>
                          <option value="CAMBIO">Cambio</option>
                        </select>
                      </label>
                      <label class="vn-field">Prenda
                        <select [value]="selectedProductId() ?? ''" (change)="changeProduct($event)">
                          @for (line of purchase.items; track line.producto_id) {
                            <option [value]="line.producto_id">{{ line.nombre }} · variante {{ line.variante_id }} · {{ line.cantidad }} unidad(es)</option>
                          }
                        </select>
                      </label>
                      <label class="vn-field">Cantidad
                        <input type="number" min="1" [max]="maxQuantity(purchase)" [value]="quantity()" (input)="changeQuantity($event)" required>
                      </label>
                      <label class="vn-field">Motivo
                        <textarea rows="3" minlength="3" maxlength="1000" [value]="reason()" (input)="changeReason($event)" required></textarea>
                      </label>
                      <p class="purchase-history__muted">La sucursal revisará la solicitud. La creación no ejecuta reembolsos ni modifica existencias.</p>
                      @if (requestError(); as message) { <p class="vn-alert vn-alert--error" role="alert">{{ message }}</p> }
                      <button class="vn-button vn-button--primary" type="submit" [disabled]="sending()">
                        {{ sending() ? 'Enviando…' : 'Enviar solicitud' }}
                      </button>
                    </form>
                  }
                </div>
              </article>
            }
          </div>
          @if (purchases().length < totalPurchases()) {
            <button class="vn-button purchase-history__more" type="button" (click)="loadMore()" [disabled]="loadingMore()">
              {{ loadingMore() ? 'Cargando…' : 'Ver compras anteriores' }}
            </button>
          }
        }
      </section>
    </main>
  `,
  styleUrls: ['./purchase-history-page.css', './purchase-history-print.css', '../clientes/customer.css'],
})
export class PurchaseHistoryPage {
  readonly auth = inject(CustomerAuthService);
  private readonly api = inject(CustomerPurchasesService);
  private readonly route = inject(ActivatedRoute);
  private readonly changeDetector = inject(ChangeDetectorRef);
  private readonly destroyRef = inject(DestroyRef);
  readonly slug = signal(this.route.snapshot.paramMap.get('tienda') ?? '');
  readonly purchases = signal<PurchaseHistoryItem[]>([]);
  readonly totalPurchases = signal(0);
  readonly requests = signal<AfterSaleRequest[]>([]);
  readonly loading = signal(true);
  readonly loadingMore = signal(false);
  readonly sending = signal(false);
  readonly error = signal<string | null>(null);
  readonly requestError = signal<string | null>(null);
  readonly activePurchaseId = signal<string | null>(null);
  readonly selectedProductId = signal<number | null>(null);
  readonly requestType = signal<AfterSaleType>('DEVOLUCION');
  readonly quantity = signal(1);
  readonly reason = signal('');
  readonly printingPurchaseId = signal<string | null>(null);

  constructor() { this.reload(); }

  reload(): void {
    const slug = this.slug();
    this.loading.set(true);
    this.error.set(null);
    forkJoin({ purchases: this.api.history(slug), afterSales: this.api.afterSales(slug) })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: result => {
          this.purchases.set(result.purchases.items);
          this.totalPurchases.set(result.purchases.total);
          this.requests.set(result.afterSales.items);
          this.loading.set(false);
        },
        error: (error: unknown) => {
          this.loading.set(false);
          this.error.set(error instanceof HttpErrorResponse && error.status === 0
            ? 'No hay conexión para consultar el historial privado. Intenta nuevamente cuando tengas conexión.'
            : error instanceof HttpErrorResponse && error.status === 401
              ? 'Tu sesión terminó. Inicia sesión nuevamente para consultar tus compras.'
              : 'No pudimos verificar tu historial. Intenta nuevamente.');
        },
      });
  }

  requestsFor(purchaseId: string): AfterSaleRequest[] {
    return this.requests().filter(request => request.compra_id === purchaseId);
  }

  loadMore(): void {
    if (this.loading() || this.purchases().length >= this.totalPurchases()) return;
    this.loadingMore.set(true);
    this.api.history(this.slug(), this.purchases().length).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: page => {
        this.purchases.update(current => [...current, ...page.items]);
        this.totalPurchases.set(page.total);
        this.loadingMore.set(false);
      },
      error: () => { this.loadingMore.set(false); this.error.set('No pudimos cargar las compras anteriores. Intenta nuevamente.'); },
    });
  }

  toggleRequest(purchase: PurchaseHistoryItem): void {
    if (this.activePurchaseId() === purchase.id) {
      this.activePurchaseId.set(null);
      return;
    }
    this.activePurchaseId.set(purchase.id);
    this.selectedProductId.set(purchase.items[0]?.producto_id ?? null);
    this.quantity.set(1);
    this.requestType.set('DEVOLUCION');
    this.reason.set('');
    this.requestError.set(null);
  }

  changeType(event: Event): void { this.requestType.set((event.target as HTMLSelectElement).value as AfterSaleType); }
  changeProduct(event: Event): void { this.selectedProductId.set(Number((event.target as HTMLSelectElement).value)); this.quantity.set(1); }
  changeQuantity(event: Event): void { this.quantity.set(Number((event.target as HTMLInputElement).value)); }
  changeReason(event: Event): void { this.reason.set((event.target as HTMLTextAreaElement).value); }
  maxQuantity(purchase: PurchaseHistoryItem): number {
    return purchase.items.find(item => item.producto_id === this.selectedProductId())?.cantidad ?? 1;
  }

  submitRequest(event: Event, purchase: PurchaseHistoryItem): void {
    event.preventDefault();
    const productId = this.selectedProductId();
    const quantity = this.quantity();
    const reason = this.reason().trim();
    if (!productId || !Number.isSafeInteger(quantity) || quantity < 1 || quantity > this.maxQuantity(purchase) || reason.length < 3) {
      this.requestError.set('Revisa la prenda, la cantidad y el motivo antes de enviar.');
      return;
    }
    this.sending.set(true);
    this.requestError.set(null);
    this.api.requestAfterSale(this.slug(), {
      id: crypto.randomUUID(),
      compra_id: purchase.id,
      tipo: this.requestType(),
      motivo: reason,
      items: [{ producto_id: productId, cantidad: quantity }],
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: created => {
        this.requests.update(current => [created, ...current]);
        this.sending.set(false);
        this.activePurchaseId.set(null);
      },
      error: (error: unknown) => {
        this.sending.set(false);
        const detail = error instanceof HttpErrorResponse ? String(error.error?.detail ?? '') : '';
        this.requestError.set(error instanceof HttpErrorResponse && error.status === 409 && detail
          ? detail
          : 'No pudimos registrar la solicitud. Comprueba tu conexión e inténtalo nuevamente.');
      },
    });
  }

  statusLabel(status: AfterSaleRequest['estado']): string {
    return ({ PENDIENTE: 'Pendiente de revisión', APROBADA: 'Aprobada', RECHAZADA: 'Rechazada', COMPLETADA: 'Completada' })[status];
  }

  printReceipt(purchaseId: string): void {
    if (typeof window === 'undefined') return;
    this.printingPurchaseId.set(purchaseId);
    this.changeDetector.detectChanges();
    window.addEventListener('afterprint', () => this.printingPurchaseId.set(null), { once: true });
    window.print();
  }
}
