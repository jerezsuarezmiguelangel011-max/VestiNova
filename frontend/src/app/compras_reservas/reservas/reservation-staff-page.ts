import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import type { ReservationResult } from './reservation-online-api.service';
import { shortageMessage } from './reservation-stock-error';
import { ReservationStaffApiService, type StaffBranch, type StaffVariant } from './reservation-staff-api.service';
import { CompanyService } from '../../organizacion_empresarial/empresa/company.service';

@Component({
  selector: 'vn-reservation-staff',
  imports: [DatePipe, ReactiveFormsModule],
  templateUrl: './reservation-staff-page.html',
  styleUrl: './reservation-staff-page.css',
})
export class ReservationStaffPage {
  private readonly api = inject(ReservationStaffApiService);
  private readonly companies = inject(CompanyService);
  private readonly destroyRef = inject(DestroyRef);
  readonly reservations = signal<ReservationResult[]>([]);
  readonly branches = signal<StaffBranch[]>([]);
  readonly variants = signal<StaffVariant[]>([]);
  readonly selectedLines = signal<Array<StaffVariant & { cantidad: number }>>([]);
  readonly policyHours = signal<number | null>(null);
  readonly loading = signal(false);
  readonly submitting = signal(false);
  readonly error = signal<string | null>(null);
  readonly notice = signal<string | null>(null);
  private scopeRevision = 0;
  private lastAttempt: { fingerprint: string; id: string } | null = null;

  readonly form = new FormGroup({
    cliente_id: new FormControl<number | null>(null, [Validators.required, Validators.min(1)]),
    sucursal_id: new FormControl<number | null>(null, [Validators.required, Validators.min(1)]),
    variante_id: new FormControl<number | null>(null, [Validators.required, Validators.min(1)]),
    cantidad: new FormControl(1, [Validators.required, Validators.min(1), Validators.max(100)]),
  });

  constructor() {
    this.refreshScope();
    this.companies.changes$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.reservations.set([]);
      this.branches.set([]);
      this.variants.set([]);
      this.selectedLines.set([]);
      this.lastAttempt = null;
      this.policyHours.set(null);
      this.notice.set(null);
      this.error.set(null);
      this.loading.set(false);
      this.submitting.set(false);
      this.form.reset({ cliente_id: null, sucursal_id: null, variante_id: null, cantidad: 1 });
      this.refreshScope();
    });
  }

  private refreshScope(): void {
    const revision = ++this.scopeRevision;
    this.load();
    this.api.policy().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: value => { if (revision === this.scopeRevision) this.policyHours.set(value.vigencia_horas); },
      error: () => { if (revision === this.scopeRevision) this.policyHours.set(null); },
    });
    this.api.branches().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: rows => { if (revision === this.scopeRevision) this.branches.set(rows); },
      error: () => { if (revision === this.scopeRevision) this.error.set('No se pudieron consultar tus sucursales autorizadas.'); }, 
    });
    this.api.variants().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => { if (revision === this.scopeRevision) this.variants.set(result.items); },
      error: () => { if (revision === this.scopeRevision) this.error.set('No se pudo cargar el catálogo de variantes.'); }, 
    });
  }

  load(): void {
    const revision = this.scopeRevision;
    this.loading.set(true);
    this.api.list().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: rows => { if (revision === this.scopeRevision) { this.reservations.set(rows); this.loading.set(false); } },
      error: (error: unknown) => {
        if (revision !== this.scopeRevision) return;
        this.loading.set(false);
        this.error.set(error instanceof HttpErrorResponse && error.status === 403
          ? 'No tienes autorización para gestionar reservas de esta empresa.'
          : 'No se pudo consultar el historial de reservas.');
      },
    });
  }

  addLine(): void {
    this.error.set(null);
    if (this.submitting()) return;
    const { variante_id, cantidad } = this.form.getRawValue();
    const variant = this.variants().find(item => item.id === variante_id);
    if (!variant || !Number.isSafeInteger(cantidad) || cantidad === null || cantidad < 1 || cantidad > 100) {
      this.error.set('Selecciona una variante y una cantidad entera entre 1 y 100.');
      return;
    }
    const selected = this.selectedLines();
    if (selected.length >= 30 || selected.some(line => line.id === variant.id)) {
      this.error.set('La variante ya está añadida o alcanzaste el máximo de 30 variantes.');
      return;
    }
    this.selectedLines.update(items => [...items, { ...variant, cantidad }]);
    this.form.patchValue({ variante_id: null, cantidad: 1 });
  }

  removeLine(variantId: number): void {
    if (!this.submitting()) this.selectedLines.update(items => items.filter(item => item.id !== variantId));
  }

  create(): void {
    this.error.set(null);
    this.notice.set(null);
    if (this.submitting() || (!this.selectedLines().length && this.form.invalid)) {
      this.form.markAllAsTouched();
      return;
    }
    const { cliente_id, sucursal_id, variante_id, cantidad } = this.form.getRawValue();
    const savedLines = this.selectedLines();
    const chosen = savedLines.length ? savedLines.map(item => ({ variante_id: item.id, cantidad: item.cantidad }))
      : [{ variante_id: variante_id ?? 0, cantidad: cantidad ?? 0 }];
    if (!Number.isSafeInteger(cliente_id) || Number(cliente_id) < 1 ||
        !Number.isSafeInteger(sucursal_id) || Number(sucursal_id) < 1 ||
        !this.branches().some(row => row.id === sucursal_id) ||
        chosen.length > 30 || chosen.some(row => !Number.isSafeInteger(row.cantidad) ||
        row.cantidad < 1 || row.cantidad > 100 ||
        !this.variants().some(variant => variant.id === row.variante_id))) {
      this.error.set('Selecciona un cliente, una sucursal y hasta 30 variantes válidas.');
      return;
    }
    // Reutilizar UUID cuando la respuesta del servidor fue incierta.
    // Un nuevo contenido genera otro UUID; el backend evita comprometer dos veces.
    const fingerprint = JSON.stringify({ cliente_id, sucursal_id, chosen });
    const id = this.lastAttempt?.fingerprint === fingerprint
      ? this.lastAttempt.id : crypto.randomUUID();
    this.lastAttempt = { fingerprint, id };
    this.submitting.set(true);
    const revision = this.scopeRevision;
    this.api.create({
      id,
      cliente_id: cliente_id!, sucursal_id: sucursal_id!,
      lineas: chosen,
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        if (revision !== this.scopeRevision) return;
        this.submitting.set(false);
        this.notice.set(`Reserva confirmada: ${result.codigo}`);
        this.lastAttempt = null;
        this.form.reset({ cliente_id: null, sucursal_id: null, variante_id: null, cantidad: 1 });
        this.selectedLines.set([]);
        this.load();
      },
      error: (error: unknown) => {
        if (revision !== this.scopeRevision) return;
        this.submitting.set(false);
        // No reusar UUID ante rechazos definitivos; mantenerlo si no sabemos
        // si la transacción confirmó pero se perdió la respuesta.
        if (error instanceof HttpErrorResponse && error.status > 0 && error.status < 500) {
          this.lastAttempt = null;
        }
        this.error.set(error instanceof HttpErrorResponse && error.status === 409
          ? shortageMessage(error) ?? 'Stock insuficiente o solicitud en conflicto.'
          : 'No se pudo confirmar la reserva. Consulta el historial antes de reintentar.');
      },
    });
  }

  cancel(row: ReservationResult): void {
    if (this.submitting() || row.estado !== 'CONFIRMADA') return;
    this.submitting.set(true);
    this.error.set(null);
    const revision = this.scopeRevision;
    this.api.cancel(row.id).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: updated => {
        if (revision !== this.scopeRevision) return;
        this.submitting.set(false);
        this.reservations.update(items => items.map(item => item.id === row.id ? updated : item));
        this.notice.set(`Reserva ${updated.codigo} cancelada y compromiso liberado.`);
      },
      error: () => {
        if (revision !== this.scopeRevision) return;
        this.submitting.set(false);
        this.error.set('No se pudo cancelar; verifica el estado y el acceso a esta sucursal.');
      },
    });
  }
}
