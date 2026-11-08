import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, computed, effect, inject, signal, untracked } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Observable, Subject, catchError, distinctUntilChanged, finalize, map, of, startWith, switchMap } from 'rxjs';
import { CatalogDataService } from './catalog-data.service';
import { CatalogShopService } from './catalog-shop.service';
import { CatalogApiService, type CatalogAvailability } from './catalog-api.service';
import { CatalogImage } from './catalog-image';
import { CatalogLocalError, type CatalogProduct, type CatalogResult } from './catalog.models';
import { StorefrontContextService } from './storefront-context.service';
import { PurchaseSelectionService } from '../../compras_reservas/compras/purchase-selection.service';
import { CustomerAuthService } from '../../compras_reservas/clientes/customer-auth.service';
import { CustomerWishlistApi } from '../../compras_reservas/deseos/customer-wishlist-api.service';
import { CustomerRecommendationsService } from '../recomendaciones/customer-recommendations.service';

@Component({
  selector: 'vn-catalog-detail',
  imports: [RouterLink, CatalogImage, DatePipe],
  templateUrl: './catalog-detail.html',
  styleUrl: './catalog.css',
})
export class CatalogDetailPage {
  readonly catalog = inject(CatalogDataService);
  readonly shop = inject(CatalogShopService);
  readonly inAdmin = inject(ActivatedRoute).parent?.snapshot.routeConfig?.path === 'catalogo-consulta';
  readonly inStorefront = inject(ActivatedRoute).parent?.snapshot.routeConfig?.path === 'tienda/:tienda';
  readonly storefront = inject(StorefrontContextService);
  private readonly cart = inject(PurchaseSelectionService);
  private readonly customerAuth = inject(CustomerAuthService);
  private readonly wishlist = inject(CustomerWishlistApi);
  private readonly personal = inject(CustomerRecommendationsService);
  readonly wishlistBusy = signal(false);
  readonly wishlistError = signal<string | null>(null);
  readonly wishlistNotice = signal<string | null>(null);
  readonly cartNotice = signal(false);
  readonly cartError = signal<string | null>(null);
  private readonly availabilityApi = inject(CatalogApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  private readonly retries = new Subject<void>();
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly notFound = signal(false);
  readonly product = signal<CatalogProduct | null>(null);
  readonly source = signal<'network' | 'local' | null>(null);
  readonly downloadedAt = signal<string | null>(null);
  readonly availability = signal<CatalogAvailability | null>(null);
  readonly availabilityLoading = signal(false);
  readonly availabilityError = signal<string | null>(null);
  readonly variants = signal<Array<{id: number; talla: string; color: string}>>([]);
  readonly offlineBranches = signal<Array<{id: number; nombre: string}>>([]);
  readonly variantsLoading = signal(false);
  readonly variantsError = signal<string | null>(null);
  readonly selectedBranchId = signal<number | null>(null);
  readonly selectedVariantId = signal<number | null>(null);
  readonly filteredAvailability = computed(() => this.availability()?.items.filter(item =>
    (this.selectedBranchId() === null || item.sucursal_id === this.selectedBranchId()) &&
    (this.selectedVariantId() === null || item.variante_id === this.selectedVariantId())
  ) ?? []);
  readonly availableBranches = computed(() => {
    const seen = new Map<number, string>();
    for (const item of this.availability()?.items ?? []) seen.set(item.sucursal_id, item.sucursal);
    return [...seen].map(([id, nombre]) => ({ id, nombre }));
  });
  private availabilityRevision = 0;

  constructor() {
    effect(() => {
      if (this.inStorefront) this.selectedBranchId.set(this.storefront.branch());
    });
    this.route.paramMap.pipe(
      map(params => params.get('slug')),
      distinctUntilChanged(),
      switchMap(slug => this.retries.pipe(
        startWith(undefined),
        switchMap(() => this.load(slug)),
      )),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe(response => {
      if (response) {
        this.product.set(response.data);
        this.source.set(response.source);
        if (response.source === 'network' && this.inStorefront) {
          this.registerConsentedView(response.data.slug);
        }
        this.downloadedAt.set(response.downloadedAt);
        if (this.shop.tienda()) this.loadVariants(response.data.slug);
        if (this.inStorefront && response.source === 'network' && this.selectedBranchId() !== null) this.consultAvailability();
        if (response.source === 'local' && this.shop.tienda()) {
          const slug = response.data.slug;
          void this.catalog.offlineBranches().then(branches => {
            if (this.product()?.slug === slug && this.source() === 'local') this.offlineBranches.set(branches);
          }).catch(() => this.offlineBranches.set([]));
        }
      }
      this.loading.set(false);
    });
    let observedRevision = this.catalog.revision();
    effect(() => {
      const revision = this.catalog.revision();
      if (revision > observedRevision) {
        observedRevision = revision;
        untracked(() => this.retries.next());
      }
    });
  }

  chooseBranch(value: string): void {
    const requested = value ? Number(value) : null;
    const allowed = [...this.availableBranches(), ...this.offlineBranches()].map(branch => branch.id);
    const selected = requested !== null && allowed.includes(requested) ? requested : null;
    this.selectedBranchId.set(selected);
    if (this.inStorefront) this.storefront.selectBranch(selected, allowed);
  }

  chooseVariant(value: string): void {
    const id = value ? Number(value) : null;
    this.selectedVariantId.set(id !== null && this.variants().some(v => v.id === id) ? id : null);
    this.cartError.set(null);
    this.cartNotice.set(false);
  }

  addToCart(): void {
    this.cartError.set(null);
    this.cartNotice.set(false);
    const item = this.product();
    const selected = this.selectedVariantId();
    if (!this.shop.tienda() || !item || this.source() !== 'network') {
      this.cartError.set('Conéctate para consultar precios y variantes actuales antes de agregar al carrito.');
      return;
    }
    if (selected === null || !this.variants().some(v => v.id === selected)) {
      this.cartError.set('Elige una talla y color para agregar esta prenda.');
      return;
    }
    this.cart.add({ data: item, source: 'network', downloadedAt: null }, selected);
    this.cartNotice.set(true);
  }

  addToWishlist(): void {
    if (this.wishlistBusy()) return;
    this.wishlistError.set(null);
    this.wishlistNotice.set(null);
    const tienda = this.shop.tienda();
    const variant = this.selectedVariantId();
    if (!tienda || this.source() !== 'network') {
      this.wishlistError.set('Conéctate para guardar la variante publicada.');
      return;
    }
    if (!variant || !this.variants().some(item => item.id === variant)) {
      this.wishlistError.set('Selecciona primero una talla y un color.');
      return;
    }
    if (!this.customerAuth.token(tienda)) {
      this.wishlistError.set('Debes iniciar sesión como cliente en esta tienda para guardar prendas.');
      return;
    }
    this.wishlistBusy.set(true);
    this.wishlist.add(tienda, variant).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: response => {
        this.wishlistBusy.set(false);
        this.wishlistNotice.set(response.agregado
          ? 'Variante guardada en tu lista de deseos.'
          : 'Esta variante ya estaba en tu lista de deseos.');
      },
      error: () => {
        this.wishlistBusy.set(false);
        this.wishlistError.set('No se pudo guardar la variante. Revisa tu sesión o conexión.');
      },
    });
  }

  private registerConsentedView(slug: string): void {
    const tienda = this.shop.tienda();
    if (!tienda || !this.personal.activeSession(tienda)) return;
    this.personal.preferences(tienda).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: state => {
        if (!state.habilitado || this.product()?.slug !== slug || this.shop.tienda() !== tienda) return;
        this.personal.registerView(tienda, slug)
          .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
            next: () => {},
            error: () => {}, // La navegación funciona aunque falle el registro opcional.
          });
      },
      error: () => {},
    });
  }

  private loadVariants(slug: string): void {
    this.variantsLoading.set(true);
    this.variantsError.set(null);
    this.catalog.variantes(slug).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: response => {
        if (this.product()?.slug === slug) {
          this.variants.set(response.data);
          this.variantsLoading.set(false);
        }
      },
      error: (error: unknown) => {
        if (this.product()?.slug === slug) {
          this.variantsLoading.set(false);
          this.variantsError.set(error instanceof CatalogLocalError ? error.message
            : 'No se pudieron consultar las variantes. Intenta nuevamente.');
        }
      },
    });
  }

  consultAvailability(): void {
    const product = this.product();
    if (!product || this.source() !== 'network' || this.availabilityLoading()) return;
    const revision = ++this.availabilityRevision;
    this.availabilityLoading.set(true);
    this.availabilityError.set(null);
    this.availabilityApi.availability(product.slug).pipe(
      takeUntilDestroyed(this.destroyRef),
      finalize(() => { if (revision === this.availabilityRevision) this.availabilityLoading.set(false); }),
    ).subscribe({
      next: result => {
        if (revision === this.availabilityRevision && this.product()?.slug === product.slug) {
          this.availability.set(result);
        }
      },
      error: (error: unknown) => {
        if (revision !== this.availabilityRevision) return;
        this.availabilityError.set(error instanceof HttpErrorResponse && error.status === 0
          ? 'Sin conexión. La disponibilidad por sucursal no se puede verificar sin internet.'
          : 'No se pudo consultar la disponibilidad por sucursal. Inténtalo nuevamente.');
      },
    });
  }

  retry(): void {
    if (!this.loading() && this.error()) this.retries.next();
  }

  private load(slug: string | null): Observable<CatalogResult<CatalogProduct> | null> {
    this.availabilityRevision++;
    this.availability.set(null);
    this.variants.set([]);
    this.offlineBranches.set([]);
    this.variantsLoading.set(false);
    this.variantsError.set(null);
    this.selectedBranchId.set(this.inStorefront ? this.storefront.branch() : null);
    this.cartNotice.set(false);
    this.cartError.set(null);
    this.wishlistNotice.set(null);
    this.wishlistError.set(null);
    this.wishlistBusy.set(false);
    this.selectedVariantId.set(null);
    this.availabilityLoading.set(false);
    this.availabilityError.set(null);
    this.loading.set(true);
    this.error.set(null);
    this.notFound.set(false);
    this.product.set(null);
    this.source.set(null);
    this.downloadedAt.set(null);
    if (!slug) {
      this.notFound.set(true);
      return of(null);
    }
    return this.catalog.get(slug).pipe(catchError((error: unknown) => {
      if (error instanceof CatalogLocalError) {
        this.error.set(error.message);
        this.downloadedAt.set(error.downloadedAt);
        if (error.downloadedAt) this.source.set('local');
        return of(null);
      }
      const status = error instanceof HttpErrorResponse ? error.status : undefined;
      if (status === 404) {
        this.notFound.set(true);
      } else {
        this.error.set(status === 0
          ? 'No pudimos conectar con el catálogo. Comprueba tu conexión e inténtalo nuevamente.'
          : status === 401 || status === 403
            ? 'No tienes permiso para consultar este producto.'
            : 'No pudimos cargar el producto. Inténtalo nuevamente.');
      }
      return of(null);
    }));
  }
}
