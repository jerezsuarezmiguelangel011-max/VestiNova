import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { type AfterSaleStatus } from '../compras/customer-purchases.service';
import { CompanyService } from '../../organizacion_empresarial/empresa/company.service';
import { PostventaApiService, type StaffAfterSaleRequest } from './postventa-api.service';

@Component({
  selector: 'vn-postventa-page',
  imports: [DatePipe],
  templateUrl: './postventa-page.html',
  styleUrl: './postventa-page.css',
})
export class PostventaPage {
  private readonly api = inject(PostventaApiService);
  private readonly companies = inject(CompanyService);
  private readonly destroyRef = inject(DestroyRef);
  readonly requests = signal<StaffAfterSaleRequest[]>([]);
  readonly totalRequests = signal(0);
  readonly status = signal<AfterSaleStatus | null>('PENDIENTE');
  readonly loading = signal(false);
  readonly loadingMore = signal(false);
  readonly error = signal<string | null>(null);
  readonly busyId = signal<string | null>(null);
  readonly notice = signal<string | null>(null);
  readonly responses = signal<Record<string, string>>({});
  private listRevision = 0;

  constructor() { this.load(); }

  load(): void {
    const revision = ++this.listRevision;
    this.loading.set(true);
    this.loadingMore.set(false);
    this.error.set(null);
    this.api.list(this.status()).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: page => {
        if (revision !== this.listRevision) return;
        this.requests.set(page.items);
        this.totalRequests.set(page.total);
        this.loading.set(false);
      },
      error: (error: unknown) => {
        if (revision !== this.listRevision) return;
        this.loading.set(false);
        this.error.set(error instanceof HttpErrorResponse && error.status === 403
          ? 'Tu usuario no tiene permiso para consultar postventa en esta empresa o sucursal.'
          : 'No pudimos cargar las solicitudes. Comprueba la conexión e intenta nuevamente.');
      },
    });
  }

  loadMore(): void {
    if (this.loading() || this.loadingMore() || this.requests().length >= this.totalRequests()) return;
    const revision = this.listRevision;
    this.loadingMore.set(true);
    this.api.list(this.status(), this.requests().length).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: page => {
        if (revision !== this.listRevision) return;
        this.requests.update(current => [...current, ...page.items]);
        this.totalRequests.set(page.total);
        this.loadingMore.set(false);
      },
      error: () => {
        if (revision !== this.listRevision) return;
        this.loadingMore.set(false);
        this.error.set('No se pudieron cargar las solicitudes anteriores. Intenta nuevamente.');
      },
    });
  }

  selectStatus(event: Event): void {
    const value = (event.target as HTMLSelectElement).value;
    this.status.set(value === 'TODAS' ? null : value as AfterSaleStatus);
    this.load();
  }

  responseFor(id: string): string { return this.responses()[id] ?? ''; }
  canManage(): boolean { return this.companies.hasPermission('postventa.gestionar'); }
  updateResponse(id: string, event: Event): void {
    const value = (event.target as HTMLTextAreaElement).value;
    this.responses.update(current => ({ ...current, [id]: value }));
  }

  decide(request: StaffAfterSaleRequest, estado: 'APROBADA' | 'RECHAZADA'): void {
    this.busyId.set(request.id);
    this.error.set(null);
    this.notice.set(null);
    this.api.decide(request.id, estado, this.responseFor(request.id)).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: updated => {
        this.busyId.set(null);
        this.load();
        this.notice.set(estado === 'APROBADA'
          ? updated.referencia_reposicion
            ? `Solicitud aprobada. Nota de reposición ${updated.referencia_reposicion}.`
            : 'Solicitud aprobada para completar en sucursal.'
          : 'Solicitud rechazada y respuesta registrada.');
      },
      error: () => { this.busyId.set(null); this.error.set('No se pudo guardar la decisión. Actualiza la lista e intenta nuevamente.'); },
    });
  }

  complete(request: StaffAfterSaleRequest): void {
    this.busyId.set(request.id);
    this.error.set(null);
    this.notice.set(null);
    this.api.complete(request.id).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: updated => {
        this.busyId.set(null);
        this.load();
        this.notice.set('La atención quedó registrada como completada.');
      },
      error: () => { this.busyId.set(null); this.error.set('No se pudo completar la solicitud. Actualiza la lista e intenta nuevamente.'); },
    });
  }

  statusLabel(value: AfterSaleStatus): string {
    return ({ PENDIENTE: 'Pendiente', APROBADA: 'Aprobada', RECHAZADA: 'Rechazada', COMPLETADA: 'Completada' })[value];
  }

}
