import { DatePipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { from } from 'rxjs';
import { RestockAlertsService, type RestockAlert } from './restock-alerts.service';

@Component({
  selector: 'vn-restock-alerts-page',
  imports: [RouterLink, DatePipe],
  templateUrl: './restock-alerts-page.html',
  styleUrls: ['../clientes/customer.css', '../clientes/customer-enhancements.css'],
})
export class RestockAlertsPage {
  private readonly api = inject(RestockAlertsService);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  readonly slug = this.route.snapshot.paramMap.get('tienda') ?? '';
  readonly alerts = signal<RestockAlert[]>([]);
  readonly loading = signal(true);
  readonly processing = signal(false);
  readonly busyId = signal<number | null>(null);
  readonly error = signal<string | null>(null);
  readonly notice = signal<string | null>(null);
  readonly statusLoading = signal(true);
  readonly serverEnabled = signal<boolean | null>(null);
  readonly browserEnabled = signal<boolean | null>(null);

  constructor() {
    this.reload();
    from(this.api.status(this.slug)).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: value => {
        this.serverEnabled.set(value.serverEnabled);
        this.browserEnabled.set(value.browserEnabled);
        this.statusLoading.set(false);
      },
      error: () => this.statusLoading.set(false),
    });
  }

  reload(): void {
    this.loading.set(true);
    this.error.set(null);
    from(this.api.list(this.slug)).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: rows => { this.alerts.set(rows); this.loading.set(false); },
      error: () => {
        this.loading.set(false);
        this.error.set('No pudimos consultar tus alertas. Comprueba tu sesión y la conexión.');
      },
    });
  }

  cancel(id: number): void {
    if (this.processing()) return;
    this.processing.set(true);
    this.busyId.set(id);
    this.error.set(null);
    this.notice.set(null);
    from(this.api.cancel(this.slug, id)).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: () => {
        this.alerts.update(rows => rows.filter(row => row.id !== id));
        this.processing.set(false);
        this.busyId.set(null);
        this.notice.set('Alerta cancelada correctamente.');
      },
      error: () => {
        this.processing.set(false);
        this.busyId.set(null);
        this.error.set('No se pudo cancelar la alerta. Vuelve a intentarlo.');
      },
    });
  }
}
