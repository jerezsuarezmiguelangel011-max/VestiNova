import { DatePipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { CompanyService } from '../../organizacion_empresarial/empresa/company.service';
import { InventoryApiService, type InventoryBranch } from '../../inventario/inventory-api.service';
import { ReconciliationApi, type SyncConflict, type SyncConflictDetail,
  type ResolveConflictInput } from './reconciliation-api.service';

@Component({
  selector: 'vn-reconciliation-page',
  imports: [ReactiveFormsModule, DatePipe],
  template: `
  <section class="conflict-page">
    <header><p class="eyebrow">VestiNova · CU13</p>
      <h1>Conciliación de sincronización</h1>
      <p>Revisa conflictos de ventas cobradas offline y solicitudes de reserva no confirmadas.
      Solo el Encargado autorizado puede documentar una resolución.</p></header>
    <aside class="warning"><strong>Sin modificar el cobro original ni forzar stock</strong>
      La conciliación registra el acuerdo y la constancia. Una devolución o
      entrega alternativa debe realizarse y comprobarse fuera de esta pantalla;
      marcarla aquí documenta esa acción, no ejecuta automáticamente dinero ni inventario.</aside>
    @if (error(); as message) { <p role="alert" class="error">{{ message }}</p> }
    @if (notice(); as message) { <p role="status" class="notice">{{ message }}</p> }
    <section class="panel">
      <h2>Filtrar conflictos</h2>
      <form [formGroup]="filters" (ngSubmit)="load()">
        <label>Sucursal
          <select formControlName="sucursal_id">
            <option [ngValue]="null">Todas mis sucursales</option>
            @for (b of branches(); track b.id) { <option [ngValue]="b.id">{{ b.nombre }}</option> }
          </select>
        </label>
        <label>Estado
          <select formControlName="estado">
            <option [ngValue]="null">Todos</option>
            <option value="CONFLICTO">Conflictos pendientes</option>
            <option value="RESUELTO">Resueltos</option>
          </select>
        </label>
        <button type="submit" [disabled]="loading()">Actualizar</button>
      </form>
    </section>
    <section class="panel">
      <h2>Bandeja central por empresa y sucursal</h2>
      @if (loading()) { <p role="status">Consultando conflictos…</p> }
      @for (row of conflicts(); track row.id) {
        <article class="conflict-row">
          <div>
            <strong>{{ row.tipo }} · {{ row.estado }}</strong>
            <p>UUID original: {{ row.operacion_id }}</p>
            <p>{{ branchName(row.sucursal_id) }} · {{ row.creada_en | date:'medium' }}</p>
            <p>{{ row.motivo }}</p>
          </div>
          <button type="button" (click)="select(row)" [disabled]="busy()">Revisar</button>
        </article>
      } @empty { @if (!loading()) { <p>No hay conflictos en las sucursales consultadas.</p> } }
    </section>
    @if (selected(); as row) {
      <section class="panel">
        <h2>Revisión de conflicto · {{ row.id }}</h2>
        <p>Tipo: <strong>{{ row.tipo }}</strong> · Estado: <strong>{{ row.estado }}</strong></p>
        <p>UUID de operación: {{ row.operacion_id }}</p>
        <p>{{ row.motivo }}</p>
        <div class="conflict-original" aria-label="Datos originales de la operación">
          <h3>Datos originales capturados sin conexión</h3>
          <p>Estos son los datos preservados al sincronizar. La conciliación no los modifica.</p>
          <dl class="conflict-facts">
            <div><dt>Sucursal</dt><dd>{{ branchName(row.sucursal_id) }}</dd></div>
            @if (originalText(row, 'cliente_id'); as cliente) {
              <div><dt>Cliente original</dt><dd>#{{ cliente }}</dd></div>
            }
            @if (originalText(row, 'origen'); as origen) {
              <div><dt>Origen</dt><dd>{{ origen }}</dd></div>
            }
            @if (originalText(row, 'efectivo'); as efectivo) {
              <div><dt>Efectivo declarado</dt><dd>Bs {{ efectivo }}</dd></div>
            }
            @if (originalFlag(row, 'efectivo_cobrado'); as cobro) {
              <div><dt>Cobro declarado</dt><dd>{{ cobro }}</dd></div>
            }
            @if (originalFlag(row, 'entrega_local'); as entrega) {
              <div><dt>Entrega declarada</dt><dd>{{ entrega }}</dd></div>
            }
          </dl>
          @if (originalLines(row).length) {
            <h4>Prendas y cantidades registradas</h4>
            <ul class="conflict-lines">
              @for (line of originalLines(row); track $index) {
                <li>
                  <span>Variante #{{ line.variante_id }} · {{ line.cantidad }} {{ line.cantidad === 1 ? 'unidad' : 'unidades' }}</span>
                  @if (line.precio_unitario) { <span>Bs {{ line.precio_unitario }} / unidad</span> }
                </li>
              }
            </ul>
          } @else {
            <p>No se incluyó un detalle de prendas en el registro original.</p>
          }
        </div>
        @if (row.tipo === 'VENTA_CONTADO') {
          <p class="warning">Si el efectivo ya se recibió, debe conservarse la evidencia
            y documentarse explícitamente la solución comercial.</p>
        }
        @if (row.estado === 'CONFLICTO') {
          <form [formGroup]="resolution" (ngSubmit)="resolve(row)">
            <label>Decisión comercial documentada
              <select formControlName="decision">
                <option value="ACUERDO_DOCUMENTADO">Acuerdo documentado</option>
                <option value="DEVOLUCION_DOCUMENTADA">Devolución documentada</option>
                <option value="ENTREGA_ALTERNATIVA_DOCUMENTADA">Entrega alternativa documentada</option>
              </select>
            </label>
            <label>Referencia de constancia o acta
              <input formControlName="referencia_constancia" maxlength="120" placeholder="Acta, recibo o código externo" />
            </label>
            <label>Observaciones de la solución
              <textarea formControlName="observacion" rows="4" maxlength="350"
                placeholder="Describe lo comprobado y la solución real"></textarea>
            </label>
            <button type="submit" [disabled]="busy() || resolution.invalid">
              {{ busy() ? 'Registrando…' : 'Registrar resolución trazable' }}
            </button>
          </form>
        } @else {
          <p>Decisión: <strong>{{ row.decision }}</strong></p>
          <p>Responsable #{{ row.responsable_id }} · {{ row.resuelta_en | date:'medium' }}</p>
          <p>{{ row.observacion }}</p>
        }
      </section>
    }
  </section>
  `,
  styles: `
  :host{display:block;min-width:0}.conflict-page{display:grid;gap:22px;max-width:1060px;color:#25372b}
  .conflict-page h1{font:400 clamp(32px,5vw,44px) Georgia,serif}
  .conflict-page h2{font:400 26px Georgia,serif;margin:0 0 16px}.conflict-page p{line-height:1.65}
  .eyebrow{color:#116149;text-transform:uppercase;font-size:11px;font-weight:700;letter-spacing:.1em}
  .warning{padding:18px;border-radius:9px;border:1px solid #dccba4;background:#fff8e8;color:#765b27}
  .warning strong{display:block}.panel{border:1px solid #dae3da;border-radius:11px;background:white;padding:24px}
  .panel form{display:grid;gap:12px;max-width:640px}.panel label{display:grid;gap:7px;font-size:13px;font-weight:600}
  .panel :is(select,input,textarea){padding:11px;border:1px solid #b4c6b9;border-radius:6px;min-height:44px}
  .panel button{min-height:44px;padding:9px 16px;border-radius:7px;border:1px solid #126147;background:#edf6ee;color:#126147;font-weight:600;cursor:pointer}
  .panel button:disabled{opacity:.5;cursor:not-allowed}
  .conflict-row{border-bottom:1px solid #e1e8df;padding:15px 0;display:flex;align-items:center;gap:15px;justify-content:space-between;flex-wrap:wrap;overflow-wrap:anywhere}
  .conflict-row p{margin:5px 0;font-size:13px}.error{color:#9d2631;background:#fff0f0;padding:12px}
  .notice{color:#225e40;background:#e7f4ea;padding:12px}
  .conflict-original{background:#f5f8f5;border:1px solid #dbe6db;border-radius:9px;padding:18px;margin:18px 0}
  .conflict-original h3{font-size:16px;margin:0 0 5px}
  .conflict-original h4{font-size:13px;margin:20px 0 8px}
  .conflict-original>p{font-size:12px;color:#5d6e61}
  .conflict-facts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px 20px}
  .conflict-facts div{min-width:0}.conflict-facts dt{font-size:11px;color:#667a6b}
  .conflict-facts dd{font-size:13px;font-weight:650;margin:3px 0;overflow-wrap:anywhere}
  .conflict-lines{list-style:none;padding:0;margin:0;background:#fff;border:1px solid #e2eae2;border-radius:6px}
  .conflict-lines li{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;padding:10px 12px;font-size:13px;border-bottom:1px solid #e5ece5}
  .conflict-lines li:last-child{border-bottom:0}
  @media(max-width:650px){.conflict-facts{grid-template-columns:1fr}}
  `,
})
export class ReconciliationPage {
  private readonly api = inject(ReconciliationApi);
  private readonly company = inject(CompanyService);
  private readonly inventory = inject(InventoryApiService);
  private readonly destroyRef = inject(DestroyRef);
  readonly branches = signal<InventoryBranch[]>([]);
  readonly conflicts = signal<SyncConflict[]>([]);
  readonly selected = signal<SyncConflictDetail | null>(null);
  readonly loading = signal(false);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly notice = signal<string | null>(null);
  private revision = 0;

  branchName(id: number): string {
    const branch = this.branches().find(item => item.id === id);
    return branch ? branch.nombre : 'Sucursal #' + id;
  }

  originalText(row: SyncConflictDetail, field: string): string | null {
    const value = row.datos_originales?.[field];
    return typeof value === 'string' || (typeof value === 'number' && Number.isFinite(value))
      ? String(value) : null;
  }

  originalFlag(row: SyncConflictDetail, field: string): string | null {
    const value = row.datos_originales?.[field];
    return typeof value === 'boolean' ? (value ? 'Sí' : 'No') : null;
  }

  originalLines(row: SyncConflictDetail): Array<{
    variante_id: number; cantidad: number; precio_unitario: string | null;
  }> {
    const raw = row.datos_originales?.['lineas'];
    if (!Array.isArray(raw)) return [];
    return raw.filter((item): item is Record<string, unknown> =>
      item !== null && typeof item === 'object' &&
      Number.isSafeInteger(item['variante_id']) &&
      Number.isSafeInteger(item['cantidad']) &&
      Number(item['cantidad']) > 0)
      .map(item => ({
        variante_id: Number(item['variante_id']),
        cantidad: Number(item['cantidad']),
        precio_unitario: typeof item['precio_unitario'] === 'string' ? item['precio_unitario'] : null,
      }));
  }

  readonly filters = new FormGroup({
    sucursal_id: new FormControl<number | null>(null),
    estado: new FormControl<'CONFLICTO' | 'RESUELTO' | null>(null),
  });
  readonly resolution = new FormGroup({
    decision: new FormControl<ResolveConflictInput['decision']>('ACUERDO_DOCUMENTADO',
      { nonNullable: true, validators: [Validators.required] }),
    referencia_constancia: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.minLength(4)] }),
    observacion: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.minLength(15)] }),
  });

  constructor() {
    this.company.changes$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      ++this.revision; this.branches.set([]); this.conflicts.set([]); this.selected.set(null);
      this.loading.set(false); this.busy.set(false);
      this.error.set(null); this.notice.set(null);
      this.filters.reset({ sucursal_id: null, estado: null });
      this.loadAll();
    });
    this.loadAll();
  }

  private loadAll(): void {
    if (!this.company.active()) return;
    const revision = this.revision;
    this.inventory.branches().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: rows => { if (revision === this.revision) this.branches.set(rows.filter(b => b.activo)); },
      error: () => { if (revision === this.revision) this.error.set('No fue posible consultar las sucursales.'); },
    });
    this.load();
  }
  load(): void {
    if (!this.company.active()) return;
    const revision = this.revision;
    this.loading.set(true); this.error.set(null);
    this.api.list(this.filters.controls.sucursal_id.value ?? undefined,
      this.filters.controls.estado.value ?? undefined)
      .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: rows => { if (revision === this.revision) { this.conflicts.set(rows); this.loading.set(false); } },
        error: () => { if (revision === this.revision) { this.loading.set(false); this.error.set('No fue posible consultar la bandeja de conciliación.'); } },
      });
  }
  select(row: SyncConflict): void {
    if (this.busy()) return;
    const revision = this.revision;
    this.api.detail(row.id).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: value => { if (revision === this.revision) this.selected.set(value); },
      error: () => { if (revision === this.revision) this.error.set('No se puede consultar este conflicto.'); },
    });
  }
  resolve(row: SyncConflictDetail): void {
    if (this.busy() || this.resolution.invalid) return;
    const revision = this.revision;
    this.busy.set(true);
    this.api.resolve(row.id, this.resolution.getRawValue()).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => { if (revision !== this.revision) return;
        this.busy.set(false);
        this.selected.set({ ...row, ...result });
        this.notice.set('Resolución registrada. Se conservan la operación y el efectivo originales, sin modificar inventario.'); this.load(); },
      error: () => { if (revision !== this.revision) return; this.busy.set(false);
        this.error.set('No se pudo registrar la resolución. Verifica permisos y estado central.'); },
    });
  }
}
