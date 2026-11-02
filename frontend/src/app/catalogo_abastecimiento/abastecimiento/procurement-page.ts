import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { finalize, forkJoin } from 'rxjs';
import { CompanyService } from '../../organizacion_empresarial/empresa/company.service';
import { InventoryApiService, InventoryBranch } from '../../inventario/inventory-api.service';
import { ProcurementOrder, ProcurementService, ProcurementVariant, Supplier } from './procurement.service';

@Component({
  selector: 'vn-procurement-page',
  imports: [ReactiveFormsModule, DatePipe],
  templateUrl: './procurement-page.html',
  styleUrl: './procurement-page.css',
})
export class ProcurementPage {
  readonly companies = inject(CompanyService);
  private readonly api = inject(ProcurementService);
  private readonly inventory = inject(InventoryApiService);
  private readonly destroyRef = inject(DestroyRef);
  readonly suppliers = signal<Supplier[]>([]);
  readonly variants = signal<ProcurementVariant[]>([]);
  readonly branches = signal<InventoryBranch[]>([]);
  readonly orders = signal<ProcurementOrder[]>([]);
  readonly lines = signal<{ variante_id: number; cantidad: number; costo_unitario: string; label: string }[]>([]);
  readonly receiveQuantities = signal<Record<number, number>>({});
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);
  readonly notice = signal<string | null>(null);
  readonly supplierForm = new FormGroup({
    codigo: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.maxLength(40), Validators.pattern(/^[a-zA-Z0-9][a-zA-Z0-9_-]*$/)] }),
    nombre: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.minLength(2), Validators.maxLength(120)] }),
    contacto: new FormControl('', { nonNullable: true, validators: [Validators.maxLength(120)] }),
    correo: new FormControl('', { nonNullable: true, validators: [Validators.email, Validators.maxLength(254)] }),
    telefono: new FormControl('', { nonNullable: true, validators: [Validators.maxLength(40)] }),
  });
  readonly orderForm = new FormGroup({
    proveedor_id: new FormControl<number | null>(null, [Validators.required, Validators.min(1)]),
    sucursal_id: new FormControl<number | null>(null, [Validators.required, Validators.min(1)]),
    variante_id: new FormControl<number | null>(null, [Validators.required, Validators.min(1)]),
    cantidad: new FormControl<number | null>(null, [Validators.required, Validators.min(1), Validators.max(1_000_000)]),
    costo_unitario: new FormControl<number | null>(null, [Validators.required, Validators.min(0.01)]),
    observaciones: new FormControl('', { nonNullable: true, validators: [Validators.maxLength(500)] }),
  });

  ngOnInit(): void {
    this.load();
    this.companies.changes$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.suppliers.set([]); this.variants.set([]); this.branches.set([]); this.orders.set([]); this.lines.set([]); this.receiveQuantities.set({}); this.load();
    });
  }

  load(): void {
    if (!this.companies.canViewProcurement()) return;
    this.loading.set(true); this.error.set(null);
    forkJoin({ suppliers: this.api.suppliers(), variants: this.api.variants(), branches: this.inventory.branches(), orders: this.api.orders() })
      .pipe(finalize(() => this.loading.set(false)), takeUntilDestroyed(this.destroyRef)).subscribe({
        next: data => { this.suppliers.set(data.suppliers); this.variants.set(data.variants); this.branches.set(data.branches); this.orders.set(data.orders.items); },
        error: error => this.error.set(this.message(error)),
      });
  }

  addLine(): void {
    const controls = this.orderForm.controls;
    if (!controls.variante_id.value || !controls.cantidad.value || !controls.costo_unitario.value || controls.variante_id.invalid || controls.cantidad.invalid || controls.costo_unitario.invalid) {
      controls.variante_id.markAsTouched(); controls.cantidad.markAsTouched(); controls.costo_unitario.markAsTouched(); return;
    }
    if (this.lines().some(line => line.variante_id === controls.variante_id.value)) { this.error.set('La variante ya está en la orden.'); return; }
    const variant = this.variants().find(item => item.id === controls.variante_id.value);
    if (!variant) return;
    this.lines.update(lines => [...lines, { variante_id: variant.id, cantidad: controls.cantidad.value!, costo_unitario: Number(controls.costo_unitario.value).toFixed(2), label: `${variant.producto} · ${variant.talla} · ${variant.color}` }]);
    controls.variante_id.reset(null); controls.cantidad.reset(null); controls.costo_unitario.reset(null); this.error.set(null);
  }

  removeLine(variantId: number): void { this.lines.update(lines => lines.filter(line => line.variante_id !== variantId)); }

  createSupplier(): void {
    if (this.supplierForm.invalid || this.saving()) { this.supplierForm.markAllAsTouched(); return; }
    const input = this.supplierForm.getRawValue();
    this.run(this.api.createSupplier({ ...input, codigo: input.codigo.trim().toUpperCase(), nombre: input.nombre.trim(), contacto: input.contacto.trim(), correo: input.correo.trim(), telefono: input.telefono.trim() }), supplier => {
      this.notice.set(`Proveedor ${supplier.nombre} registrado.`); this.supplierForm.reset({ codigo: '', nombre: '', contacto: '', correo: '', telefono: '' }); this.load();
    });
  }

  toggleSupplier(supplier: Supplier): void {
    this.run(this.api.updateSupplier(supplier.id, { activo: !supplier.activo }), updated => { this.notice.set(`${updated.nombre} quedó ${updated.activo ? 'activo' : 'inactivo'}.`); this.load(); });
  }

  createOrder(): void {
    if (this.saving()) return;
    const value = this.orderForm.getRawValue();
    if (!value.proveedor_id || !value.sucursal_id || !this.lines().length) {
      this.orderForm.controls.proveedor_id.markAsTouched(); this.orderForm.controls.sucursal_id.markAsTouched();
      if (!this.lines().length) this.error.set('Agrega al menos una variante a la orden.');
      return;
    }
    const input = { proveedor_id: value.proveedor_id, sucursal_id: value.sucursal_id, observaciones: value.observaciones.trim(), lineas: this.lines().map(({ variante_id, cantidad, costo_unitario }) => ({ variante_id, cantidad, costo_unitario })) };
    this.run(this.api.createOrder(input), order => { this.notice.set(`Orden #${order.id} creada para ${order.proveedor}.`); this.lines.set([]); this.orderForm.reset({ proveedor_id: null, sucursal_id: null, variante_id: null, cantidad: null, costo_unitario: null, observaciones: '' }); this.load(); });
  }

  receiveAll(order: ProcurementOrder): void {
    const lineas = order.lineas.filter(line => line.cantidad_solicitada > line.cantidad_recibida).map(line => ({ linea_id: line.id, cantidad: line.cantidad_solicitada - line.cantidad_recibida }));
    if (!lineas.length || this.saving()) return;
    this.run(this.api.receive(order.id, { id: crypto.randomUUID(), lineas }), updated => { this.notice.set(`Recepción de la orden #${updated.id} registrada; se actualizó el inventario.`); this.load(); });
  }

  setReceiveQuantity(lineId: number, raw: string): void {
    const value = Number(raw);
    const quantity = Number.isSafeInteger(value) && value > 0 ? value : 0;
    this.receiveQuantities.update(current => ({ ...current, [lineId]: quantity }));
  }

  receiveSelected(order: ProcurementOrder): void {
    const lineas = order.lineas.map(line => ({ linea_id: line.id, cantidad: this.receiveQuantities()[line.id] ?? 0 })).filter(line => line.cantidad > 0);
    if (!lineas.length) { this.error.set('Indica al menos una cantidad positiva para recibir.'); return; }
    const pending = new Map(order.lineas.map(line => [line.id, line.cantidad_solicitada - line.cantidad_recibida]));
    if (lineas.some(line => line.cantidad > (pending.get(line.linea_id) ?? 0))) { this.error.set('La cantidad no puede superar lo pendiente en cada línea.'); return; }
    if (this.saving()) return;
    this.run(this.api.receive(order.id, { id: crypto.randomUUID(), lineas }), updated => {
      this.notice.set(`Recepcion de la orden #${updated.id} registrada; el inventario se actualizo.`);
      this.receiveQuantities.update(current => {
        const next = { ...current };
        for (const line of updated.lineas) delete next[line.id];
        return next;
      });
      this.load();
    });
  }

  cancel(order: ProcurementOrder): void {
    if (order.estado !== 'PENDIENTE' || this.saving()) return;
    this.run(this.api.cancel(order.id), updated => { this.notice.set(`Orden #${updated.id} cancelada.`); this.load(); });
  }

  total(): string { return this.lines().reduce((sum, line) => sum + Number(line.costo_unitario) * line.cantidad, 0).toFixed(2); }
  remaining(order: ProcurementOrder): number { return order.lineas.reduce((sum, line) => sum + line.cantidad_solicitada - line.cantidad_recibida, 0); }

  private run<T>(request: import('rxjs').Observable<T>, onSuccess: (value: T) => void): void {
    if (this.saving()) return;
    this.saving.set(true); this.error.set(null);
    request.pipe(finalize(() => this.saving.set(false)), takeUntilDestroyed(this.destroyRef)).subscribe({ next: onSuccess, error: error => this.error.set(this.message(error)) });
  }

  private message(error: unknown): string {
    if (error instanceof HttpErrorResponse && typeof error.error?.detail === 'string') return error.error.detail;
    return 'No pudimos completar la operación. Revisa el proveedor, sucursal, cantidades y variantes.';
  }
}
