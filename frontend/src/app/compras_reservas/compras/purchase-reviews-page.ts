import { DatePipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';
import { CustomerPurchasesService, type PurchaseHistoryItem, type ProductReview } from './customer-purchases.service';

@Component({
  selector: 'vn-purchase-reviews',
  imports: [RouterLink, DatePipe],
  templateUrl: './purchase-reviews-page.html',
  styleUrls: ['../clientes/customer.css', '../clientes/customer-enhancements.css'],
})
export class PurchaseReviewsPage {
  private readonly api = inject(CustomerPurchasesService);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  readonly slug = this.route.snapshot.paramMap.get('tienda') ?? '';
  readonly purchases = signal<PurchaseHistoryItem[]>([]);
  readonly reviews = signal<ProductReview[]>([]);
  readonly totalPurchases = signal(0);
  readonly loadingMore = signal(false);
  readonly loading = signal(true);
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);
  readonly notice = signal<string | null>(null);

  constructor() {
    forkJoin({ purchases: this.api.history(this.slug), reviews: this.api.reviews(this.slug) })
      .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: data => {
          this.purchases.set(data.purchases.items);
          this.totalPurchases.set(data.purchases.total);
          this.reviews.set(data.reviews.items);
          this.loading.set(false);
        },
        error: () => { this.loading.set(false); this.error.set('No se pudieron consultar tus compras. Comprueba tu sesión y conexión.'); },
      });
  }

  loadMore(): void {
    if (this.loadingMore() || this.purchases().length >= this.totalPurchases()) return;
    this.loadingMore.set(true);
    this.api.history(this.slug, this.purchases().length).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: page => {
        this.purchases.update(old => [...old, ...page.items]);
        this.totalPurchases.set(page.total);
        this.loadingMore.set(false);
      },
      error: () => {
        this.loadingMore.set(false);
        this.error.set('No pudimos consultar compras anteriores. Intenta nuevamente.');
      },
    });
  }

  uniqueProductItems(purchase: PurchaseHistoryItem): PurchaseHistoryItem['items'] {
    const seen = new Set<number>();
    return purchase.items.filter(item => {
      if (seen.has(item.producto_id)) return false;
      seen.add(item.producto_id);
      return true;
    });
  }

  reviewFor(compraId: string, productoId: number): ProductReview | undefined {
    return this.reviews().find(x => x.compra_id === compraId && x.producto_id === productoId);
  }

  save(compraId: string, productoId: number, puntuacion: number, comentario: string): void {
    if (!Number.isInteger(puntuacion) || puntuacion < 1 || puntuacion > 5 || comentario.length > 1000) {
      this.error.set('Introduce una puntuación válida y hasta mil caracteres.'); return;
    }
    this.saving.set(true); this.error.set(null); this.notice.set(null);
    const previous = this.reviewFor(compraId, productoId);
    const req = previous
      ? this.api.editReview(this.slug, previous.id, { puntuacion, comentario })
      : this.api.createReview(this.slug, { compra_id: compraId, producto_id: productoId, puntuacion, comentario });
    req.pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: review => {
        this.reviews.update(rows => previous ? rows.map(row => row.id === review.id ? review : row) : [review, ...rows]);
        this.saving.set(false); this.notice.set('Valoración guardada.');
      },
      error: () => { this.saving.set(false); this.error.set('No se pudo guardar. Verifica que la compra esté entregada.'); },
    });
  }
}
