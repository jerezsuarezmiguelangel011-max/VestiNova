import { Component, DestroyRef, computed, effect, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { HttpErrorResponse } from '@angular/common/http';
import { CatalogApiService } from '../../catalogo_publico/catalogo/catalog-api.service';
import { CatalogDataService } from '../../catalogo_publico/catalogo/catalog-data.service';
import { CatalogShopService } from '../../catalogo_publico/catalogo/catalog-shop.service';
import { StorefrontContextService } from '../../catalogo_publico/catalogo/storefront-context.service';
import { CustomerAuthService } from '../clientes/customer-auth.service';
import { PurchaseSelectionService, validPurchaseQuantity } from './purchase-selection.service';
import { StripePurchaseApiService, StripeCheckoutState, StripeCheckoutInput } from './stripe-purchase-api.service';

interface VariantChoice { id: number; talla: string; color: string; }
interface BranchChoice { id: number; nombre: string; }

@Component({
  selector: 'vn-stripe-purchase-page',
  imports: [RouterLink],
  templateUrl: './stripe-purchase-page.html',
  styleUrl: './stripe-purchase-page.css',
})
export class StripePurchasePage {
  readonly shop = inject(CatalogShopService);
  private readonly storefront = inject(StorefrontContextService);
  readonly customers = inject(CustomerAuthService);
  private readonly catalog = inject(CatalogDataService);
  private readonly directory = inject(CatalogApiService);
  private readonly api = inject(StripePurchaseApiService);
  private readonly selection = inject(PurchaseSelectionService);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);

  readonly lines = this.selection.lines;
  readonly branches = signal<BranchChoice[]>([]);
  readonly variants = signal<Record<number, VariantChoice[]>>({});
  readonly chosenVariants = signal<Record<number, number>>({});
  readonly branch = signal<number | null>(null);
  readonly delivery = signal<'RETIRO' | 'DOMICILIO'>('RETIRO');
  readonly address = signal('');
  readonly enabled = signal(false);
  readonly checkingStripe = signal(true);
  readonly stripeMessage = signal('Stripe de prueba todavía no está configurado.');
  readonly loading = signal(true);
  readonly submitting = signal(false);
  readonly error = signal<string | null>(null);
  readonly status = signal<StripeCheckoutState | null>(null);
  readonly returnId = signal<string | null>(null);
  readonly returnCancelled = signal(false);

  private initializedShop: string | null = null;
  private readonly restoredShops = new Set<string>();
  private pendingBranch: number | null = null;
  private readonly requestedVariants = new Set<number>();
  private operation: { fingerprint: string; id: string } | null = null;

  readonly canPay = computed(() => {
    const slug = this.shop.tienda();
    return !!slug && !!this.customers.token(slug) && this.enabled()
      && this.branch() !== null && !this.loading() && !this.submitting()
      && this.lines().length > 0 && !this.returnId()
      && this.lines().every(item => item.source === 'network'
        && validPurchaseQuantity(item.cantidad)
        && !!this.chosenVariants()[item.product.id]
        && !!this.variants()[item.product.id]?.some(v => v.id === this.chosenVariants()[item.product.id]))
      && (this.delivery() === 'RETIRO' || this.address().trim().length >= 10);
  });

  readonly paymentBlocker = computed((): string | null => {
    const slug = this.shop.tienda();
    if (!slug) return 'Selecciona una tienda para comenzar.';
    if (this.checkingStripe()) return 'Comprobando la disponibilidad de Stripe de prueba…';
    if (!this.enabled()) return this.stripeMessage();
    if (!this.customers.token(slug)) return 'Inicia sesión o crea una cuenta de esta tienda para continuar.';
    if (this.loading()) return 'Consultando las sucursales de esta tienda…';
    if (this.lines().length === 0) return 'Agrega al menos una prenda al carrito.';
    if (this.lines().some(line => line.source !== 'network')) return 'Necesitas una consulta actualizada en línea para comprar.';
    if (this.lines().some(line => !validPurchaseQuantity(line.cantidad))) return 'Introduce una cantidad válida en cada prenda.';
    if (this.lines().some(line => !this.chosenVariants()[line.product.id] ||
      !this.variants()[line.product.id]?.some(v => v.id === this.chosenVariants()[line.product.id]))) {
      return 'Selecciona talla y color de todas las prendas.';
    }
    if (this.branch() === null) return 'Selecciona la sucursal que preparará tu compra.';
    if (this.delivery() === 'DOMICILIO' && this.address().trim().length < 10) {
      return 'Completa la dirección de entrega (al menos 10 caracteres).';
    }
    return null;
  });

  constructor() {
    effect(() => {
      const slug = this.shop.tienda();
      if (!slug || slug === this.initializedShop) return;
      if (this.initializedShop && this.initializedShop !== slug) this.selection.clear();
      this.initializedShop = slug;
      this.requestedVariants.clear();
      this.variants.set({});
      this.chosenVariants.set({});
      this.loading.set(true);
      this.error.set(null);
      this.branches.set([]);
      this.branch.set(null);
      this.enabled.set(false);
      this.checkingStripe.set(true);
      this.stripeMessage.set('Stripe de prueba todavía no está configurado.');
      this.directory.sucursales().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: branches => {
          if (this.shop.tienda() !== slug) return;
          this.branches.set(branches);
          const preferred = this.pendingBranch ??
            (this.storefront.company() === slug ? this.storefront.branch() : null);
          if (preferred !== null && branches.some(b => b.id === preferred)) {
            this.branch.set(preferred);
          }
          this.pendingBranch = null;
          this.loading.set(false);
        },
        error: () => { if (this.shop.tienda() === slug) {
          this.loading.set(false);
          this.error.set('No se pudieron consultar las sucursales de esta empresa.');
        } },
      });
      this.restoreCart(slug);
      if (this.returnId() && this.customers.token(slug)) this.checkPayment();
      this.api.capabilities(slug).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: info => {
          if (this.shop.tienda() !== slug) return;
          this.enabled.set(info.habilitado);
          this.stripeMessage.set(info.detail || 'Stripe de prueba no está disponible.');
          this.checkingStripe.set(false);
        },
        error: () => {
          if (this.shop.tienda() !== slug) return;
          this.enabled.set(false);
          this.stripeMessage.set('No se pudo verificar Stripe. Comprueba que el backend esté funcionando.');
          this.checkingStripe.set(false);
        },
      });
    });

    effect(() => {
      const slug = this.shop.tienda();
      if (!slug) return;
      for (const line of this.lines()) {
        if (this.requestedVariants.has(line.product.id)) continue;
        this.requestedVariants.add(line.product.id);
        this.directory.variantes(line.product.slug).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
          next: variants => {
            if (this.shop.tienda() !== slug) return;
            this.variants.update(values => ({ ...values, [line.product.id]: variants }));
            const preferred = this.lines().find(item => item.product.id === line.product.id)?.varianteId;
            if (preferred && variants.some(v => v.id === preferred)) {
              this.chosenVariants.update(values => ({ ...values, [line.product.id]: preferred }));
            }
          },
          error: () => this.error.set('No se pudieron consultar las variantes de una prenda.'),
        });
      }
    });

    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(params => {
      const product = params.get('slug');
      const checkout = params.get('checkout');
      this.returnCancelled.set(params.get('resultado') === 'cancelado');
      if (checkout && /^[0-9a-f-]{36}$/i.test(checkout)) {
        this.returnId.set(checkout);
        this.checkPayment();
      } else {
        this.returnId.set(null);
        this.status.set(null);
      }
      if (product) {
        this.catalog.get(product).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
          next: result => {
            this.selection.add(result);
            if (result.source === 'local') {
              this.error.set('Solo puedes realizar compras con datos verificados en línea.');
            }
          },
          error: () => this.error.set('No pudimos consultar la prenda seleccionada.'),
        });
      }
    });
  }

  selectBranch(raw: string): void {
    const id = Number(raw);
    this.branch.set(this.branches().some(b => b.id === id) ? id : null);
    this.operation = null;
  }
  chooseVariant(productId: number, raw: string): void {
    const id = Number(raw);
    if (!this.variants()[productId]?.some(v => v.id === id)) return;
    this.chosenVariants.update(v => ({ ...v, [productId]: id }));
    this.selection.chooseVariant(productId, id);
    this.operation = null;
  }
  changeQuantity(productId: number, value: string): void {
    this.selection.updateQuantity(productId, value);
    this.operation = null;
  }
  remove(productId: number): void {
    this.selection.remove(productId);
    this.operation = null;
  }
  selectDelivery(method: string): void {
    this.delivery.set(method === 'DOMICILIO' ? 'DOMICILIO' : 'RETIRO');
    this.operation = null;
  }
  setAddress(value: string): void {
    this.address.set(value);
    this.operation = null;
  }

  /** Guarda únicamente identificadores públicos: nunca tokens, pagos ni direcciones. */
  private saveCart(slug: string): void {
    const draft = {
      branch: this.branch(), delivery: this.delivery(),
      items: this.lines().map(line => ({
        slug: line.product.slug, id: line.product.id, variant: this.chosenVariants()[line.product.id],
        quantity: line.cantidad,
      })),
    };
    try { sessionStorage.setItem('vestinova-cu09-cart:' + slug, JSON.stringify(draft)); }
    catch { /* solo memoria */ }
  }

  private restoreCart(slug: string): void {
    if (this.restoredShops.has(slug)) return;
    this.restoredShops.add(slug);
    try {
      const raw = sessionStorage.getItem('vestinova-cu09-cart:' + slug);
      if (!raw) return;
      const draft = JSON.parse(raw);
      if (!draft || !Array.isArray(draft.items) || draft.items.length > 30) return;
      if (draft.delivery === 'RETIRO' || draft.delivery === 'DOMICILIO') this.delivery.set(draft.delivery);
      const requestedBranch = Number(draft.branch);
      if (Number.isSafeInteger(requestedBranch) && requestedBranch > 0) {
        this.pendingBranch = requestedBranch;
      }
      for (const item of draft.items) {
        if (typeof item.slug !== 'string' || !/^[a-z0-9-]{3,140}$/.test(item.slug)
          || !Number.isSafeInteger(item.id) || !Number.isSafeInteger(item.variant)
          || !validPurchaseQuantity(String(item.quantity))) continue;
        this.catalog.get(item.slug).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
          next: response => {
            if (this.shop.tienda() !== slug || response.data.id !== item.id) return;
            this.selection.add(response, item.variant);
            this.selection.updateQuantity(item.id, String(item.quantity));
            this.chosenVariants.update(ids => ({ ...ids, [item.id]: item.variant }));
          },
          error: () => { /* Producto retirado: requiere nueva selección */ },
        });
      }
    } catch { /* copia local inválida: no se envía al backend */ }
  }

  prepareAccess(): void {
    const slug = this.shop.tienda();
    if (slug) this.saveCart(slug);
  }

  proceed(): void {
    if (!this.canPay()) return;
    const slug = this.shop.tienda()!;
    const input: Omit<StripeCheckoutInput, 'id'> = {
      sucursal_id: this.branch()!, entrega: this.delivery(), direccion: this.address().trim(),
      items: this.lines().map(line => ({
        producto_id: line.product.id, variante_id: this.chosenVariants()[line.product.id],
        cantidad: Number(line.cantidad),
      })),
    };
    const fingerprint = JSON.stringify(input);
    if (this.operation?.fingerprint !== fingerprint) {
      this.operation = { fingerprint, id: crypto.randomUUID() };
    }
    this.submitting.set(true);
    this.error.set(null);
    this.api.checkout(slug, { ...input, id: this.operation.id })
      .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: result => {
          this.submitting.set(false);
          if (result.estado !== 'PAGO_PENDIENTE' || !result.checkout_url
            || !/^https:\/\/checkout\.stripe\.com\//.test(result.checkout_url)) {
            this.error.set('Stripe no proporcionó una sesión de pago válida. Consulta el estado de la operación.');
            return;
          }
          // Solo URLs HTTPS del dominio oficial de Checkout. No se confía en enlaces arbitrarios.
          this.saveCart(slug);
          window.location.assign(result.checkout_url);
        },
        error: (error: unknown) => {
          this.submitting.set(false);
          const code = error instanceof HttpErrorResponse ? error.status : undefined;
          this.error.set(code === 503 ? 'El pago con Stripe no está configurado o no está disponible. No se inició el cobro.'
            : code === 409 ? 'La disponibilidad o el importe cambiaron. Revisa la compra.'
              : code === 401 ? 'Inicia sesión como cliente de esta tienda para pagar.'
                : 'No se pudo iniciar el pago. Tu selección no se ha confirmado.');
        },
      });
  }

  checkPayment(): void {
    const slug = this.shop.tienda();
    const id = this.returnId();
    if (!slug || !id || !this.customers.token(slug)) return;
    this.submitting.set(true);
    this.error.set(null);
    this.api.reconcile(slug, id).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: value => {
        this.status.set(value);
        if (value.estado === 'CONFIRMADA') {
          this.selection.clear();
          try { sessionStorage.removeItem('vestinova-cu09-cart:' + slug); } catch { /* solo memoria */ }
        }
        this.submitting.set(false);
      },
      error: () => {
        this.error.set('No se pudo comprobar el estado del pago. Inténtalo nuevamente.');
        this.submitting.set(false);
      },
    });
  }
}
