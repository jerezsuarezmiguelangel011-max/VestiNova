import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { CompanyService } from '../../organizacion_empresarial/empresa/company.service';
import { InventoryApiService, type InventoryBranch } from '../../inventario/inventory-api.service';
import { ReservationAttentionApi, type AttentionFilter, type AttentionResult } from './reservation-attention-api.service';


@Component({
  selector: 'vn-reservation-attention',
  imports: [DatePipe, ReactiveFormsModule],
  template: `
  <section class="attention-page" aria-labelledby="attention-title">
    <header class="attention-heading">
      <p class="attention-eyebrow">VestiNova · CU14</p>
      <h1 id="attention-title">Atender retiro de reservas</h1>
      <p>Localiza la reserva del cliente, verifica su identidad y entrega las prendas.
        La salida se registra en el inventario únicamente después de confirmar la atención.</p>
    </header>

    <div class="attention-instructions" aria-label="Procedimiento para atender una reserva">
      <div><span class="attention-step">01</span><strong>Busca la reserva</strong><small>Por código, cliente o sucursal.</small></div>
      <div><span class="attention-step">02</span><strong>Comprueba el retiro</strong><small>Revisa prendas, vigencia e identidad.</small></div>
      <div><span class="attention-step">03</span><strong>Confirma la entrega</strong><small>El servidor registra la salida una sola vez.</small></div>
    </div>

    @if (error(); as message) { <p class="attention-error" role="alert">{{ message }}</p> }
    @if (notice(); as message) { <p class="attention-notice" role="status">{{ message }}</p> }

    <section class="attention-card" aria-labelledby="attention-search-title">
      <div class="attention-section-heading">
        <h2 id="attention-search-title">Buscar reservas</h2>
        <p>Solo aparecen las sucursales a las que tienes acceso.</p>
      </div>
      <form [formGroup]="search" (ngSubmit)="load()" class="attention-search">
        <label>Sucursal
          <select formControlName="sucursal_id">
            <option [ngValue]="null">Todas mis sucursales</option>
            @for (branch of branches(); track branch.id) {
              <option [ngValue]="branch.id">{{ branch.nombre }}</option>
            }
          </select>
        </label>
        <label>Código de reserva
          <input formControlName="codigo" maxlength="36" placeholder="Ej.: VN-R-9ED1..." />
        </label>
        <label>Cliente (ID opcional)
          <input type="number" min="1" step="1" formControlName="cliente_id" placeholder="Número de cliente" />
        </label>
        <label>Mostrar
          <select formControlName="estado">
            <option value="CONFIRMADA">Confirmadas · listas para retirar</option>
            <option value="TODAS">Todas las reservas</option>
            <option value="ATENDIDA">Entregadas</option>
            <option value="CANCELADA">Canceladas</option>
            <option value="VENCIDA">Vencidas</option>
          </select>
        </label>
        <div class="attention-search-actions">
          <button type="submit" [disabled]="loading()">Buscar reservas</button>
          <button type="button" class="attention-button--secondary" (click)="resetFilters()" [disabled]="loading()">Limpiar filtros</button>
        </div>
      </form>
    </section>

    <section class="attention-card" aria-labelledby="attention-list-title">
      <div class="attention-section-heading attention-section-heading--inline">
        <div>
          <h2 id="attention-list-title">{{ search.controls.estado.value === 'CONFIRMADA' ? 'Pendientes de retiro' : 'Historial de reservas' }}</h2>
          <p>{{ search.controls.estado.value === 'CONFIRMADA'
            ? 'Selecciona una reserva confirmada para verificarla y registrar el retiro.'
            : 'Consulta el estado y el historial de las reservas de tus sucursales.' }}</p>
        </div>
        <button type="button" class="attention-button--secondary" (click)="load()" [disabled]="loading()">Actualizar</button>
      </div>
      @if (loading()) { <p role="status" class="attention-loading">Actualizando reservas…</p> }
      @for (row of rows(); track row.id) {
        <div class="attention-entry">
          <article class="attention-item" [class.attention-item--open]="selectedId() === row.id">
            <div class="attention-item__main">
              <div class="attention-item__title">
                <strong>{{ row.codigo }}</strong>
                <span class="attention-state"
                  [class.attention-state--confirmed]="row.estado === 'CONFIRMADA'"
                  [class.attention-state--closed]="row.estado !== 'CONFIRMADA'">{{ statusLabel(row.estado) }}</span>
              </div>
              <p><strong>{{ row.cliente_nombre || ('Cliente #' + row.cliente_id) }}</strong>
                <span>· {{ row.sucursal_nombre || ('Sucursal #' + row.sucursal_id) }}</span></p>
              <p>{{ totalUnits(row) }} {{ totalUnits(row) === 1 ? 'unidad' : 'unidades' }}
                · {{ row.lineas.length }} {{ row.lineas.length === 1 ? 'variante' : 'variantes' }}
                · vence {{ row.vence_en | date:'medium' }}</p>
              <div class="attention-item__products">
                @for (line of row.lineas; track line.variante_id) {
                  <span>{{ line.producto_nombre || ('Prenda #' + line.variante_id) }}
                    @if (line.talla || line.color) { · {{ line.talla }} / {{ line.color }} }
                    × {{ line.cantidad }}</span>
                }
              </div>
            </div>
            <button type="button" class="attention-item__action"
              [disabled]="busy() || (detailLoading() && selectedId() === row.id)"
              [attr.aria-expanded]="selectedId() === row.id"
              [attr.aria-controls]="'attention-detail-' + row.id"
              (click)="select(row)">
              {{ selectedId() === row.id ? 'Cerrar detalle' : (row.estado === 'CONFIRMADA' ? 'Atender reserva' : 'Ver historial') }}
            </button>
          </article>
          @if (selectedId() === row.id) {
            <div class="attention-detail" [id]="'attention-detail-' + row.id">
              @if (detailLoading()) {
                <p role="status">Verificando el estado central de la reserva…</p>
              } @else if (detailError(); as message) {
                <p class="attention-error" role="alert">{{ message }}</p>
                <button type="button" class="attention-button--secondary" (click)="select(row)">Reintentar consulta</button>
              } @else if (selected(); as reservation) {
                <div class="attention-detail__heading">
                  <h3>Atención de {{ reservation.codigo }}</h3>
                  <span class="attention-state" [class.attention-state--confirmed]="reservation.estado === 'CONFIRMADA'"
                    [class.attention-state--closed]="reservation.estado !== 'CONFIRMADA'">
                    {{ statusLabel(reservation.estado) }}
                  </span>
                </div>
                <dl class="attention-summary">
                  <div><dt>Cliente</dt><dd>{{ reservation.cliente_nombre || ('Cliente #' + reservation.cliente_id) }}</dd></div>
                  <div><dt>Sucursal de retiro</dt><dd>{{ reservation.sucursal_nombre || ('Sucursal #' + reservation.sucursal_id) }}</dd></div>
                  <div><dt>Confirmada el</dt><dd>{{ reservation.creada_en | date:'medium' }}</dd></div>
                  <div><dt>Válida hasta</dt><dd>{{ reservation.vence_en | date:'medium' }}</dd></div>
                </dl>
                <h4>Prendas que debe entregar</h4>
                <div class="attention-detail__products">
                  @for (line of reservation.lineas; track line.variante_id) {
                    <div>
                      <span><strong>{{ line.producto_nombre || ('Prenda #' + line.variante_id) }}</strong>
                        @if (line.talla || line.color) { · {{ line.talla }} / {{ line.color }} }</span>
                      <strong>{{ line.cantidad }} {{ line.cantidad === 1 ? 'unidad' : 'unidades' }}</strong>
                    </div>
                  }
                </div>

                @if (reservation.estado === 'CONFIRMADA') {
                  <div class="attention-action-section">
                    <h4>Confirmar retiro</h4>
                    <p>Solicita el código de reserva, comprueba la identidad del cliente y verifica físicamente las prendas antes de continuar.</p>
                    <form [formGroup]="delivery" (ngSubmit)="deliver(reservation)">
                      <label class="attention-check">
                        <input type="checkbox" formControlName="verified" />
                        <span>Confirmo que verifiqué la identidad del cliente y el código de reserva.</span>
                      </label>
                      <label>Descripción de la comprobación
                        <input formControlName="comprobacion" maxlength="180" placeholder="Ej.: Cliente presentó su código y documento" />
                      </label>
                      <button class="attention-primary" type="submit" [disabled]="busy() || delivery.invalid">
                        {{ busy() ? 'Registrando entrega…' : 'Entregar prendas y registrar retiro' }}
                      </button>
                    </form>
                  </div>
                  <details class="attention-cancel">
                    <summary>¿Necesitas cancelar esta reserva?</summary>
                    <p>Si la cancelas, se liberan las unidades comprometidas. No se descuenta inventario físico.</p>
                    <form [formGroup]="cancellation" (ngSubmit)="cancel(reservation)">
                      <label>Motivo obligatorio de cancelación
                        <textarea formControlName="motivo" rows="2" maxlength="300" placeholder="Indica por qué no se realizará el retiro"></textarea>
                      </label>
                      <button class="attention-button--danger" type="submit"
                        [disabled]="busy() || cancellation.invalid">Cancelar reserva y liberar compromiso</button>
                    </form>
                  </details>
                } @else {
                  <p class="attention-closed">Esta reserva ya no admite nuevas entregas ni cancelaciones.</p>
                }
                @if (reservation.eventos?.length) {
                  <details class="attention-events">
                    <summary>Ver historial de eventos ({{ reservation.eventos?.length }})</summary>
                    @for (event of reservation.eventos ?? []; track $index) {
                      <p>{{ event.en | date:'medium' }} · {{ statusLabel(event.estado) }} · {{ event.actor }}
                        @if (event.motivo) { · Motivo: {{ event.motivo }} }
                        @if (event.comprobacion) { · Verificación: {{ event.comprobacion }} }
                      </p>
                    }
                  </details>
                }
              }
            </div>
          }
        </div>
      } @empty {
        @if (!loading()) {
          <p class="attention-empty">{{ search.controls.estado.value === 'CONFIRMADA'
            ? 'No hay reservas confirmadas pendientes de retiro para estos filtros.'
            : 'No se encontraron reservas con los filtros seleccionados.' }}</p>
        }
      }
      @if (rows().length === 100) {
        <p class="attention-hint">Se muestran las 100 reservas más recientes. Filtra por código, cliente o sucursal para localizar otras.</p>
      }
    </section>
  </section>
  `,
  styles: `
    :host{display:block;min-width:0}.attention-page{max-width:1110px;display:grid;gap:22px;color:#25372b}
    .attention-heading h1{font:400 clamp(30px,4vw,45px) Georgia,serif;margin:7px 0 10px}
    .attention-heading p{line-height:1.65;max-width:830px}.attention-eyebrow{color:#126147;text-transform:uppercase;font-size:11px;font-weight:700;letter-spacing:.1em}
    .attention-instructions{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
    .attention-instructions>div{background:#eaf1eb;border:1px solid #d5e3d6;border-radius:9px;padding:15px;display:grid;gap:6px}
    .attention-step{color:#176347;font-size:11px;font-weight:800;letter-spacing:.07em}
    .attention-instructions strong{font-size:14px}.attention-instructions small{font-size:12px;color:#4c6a58;line-height:1.5}
    .attention-card{background:white;padding:26px;border:1px solid #d9e0d8;border-radius:12px}
    .attention-section-heading h2{font:400 27px Georgia,serif;margin:0 0 7px}
    .attention-section-heading p{font-size:13px;line-height:1.6;color:#58685c;margin:0 0 15px}
    .attention-section-heading--inline{display:flex;justify-content:space-between;align-items:start;gap:12px;flex-wrap:wrap}
    .attention-search{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:15px}
    .attention-card label{display:grid;gap:7px;font-size:13px;font-weight:600}
    .attention-card :is(input,select,textarea){width:100%;min-width:0;min-height:43px;padding:10px;border-radius:7px;border:1px solid #b5c2b7;background:white}
    .attention-card input[type=checkbox]{min-height:20px;width:20px;height:20px;flex:0 0 20px;padding:0}
    .attention-card button{min-height:42px;padding:9px 15px;border:1px solid #126147;color:#126147;background:#f0f7f1;border-radius:7px;cursor:pointer;font-weight:600}
    .attention-card button:disabled{opacity:.5;cursor:not-allowed}
    .attention-search-actions{grid-column:1/-1;display:flex;gap:10px;flex-wrap:wrap}
    .attention-search-actions button:first-child{background:#116149;color:white;flex:1}
    .attention-button--secondary{background:#f5f9f5!important}
    .attention-primary{background:#116149!important;color:white!important}
    .attention-entry{border-top:1px solid #e1e8e1}
    .attention-entry:first-of-type{border-top:0}
    .attention-item{padding:20px 0;display:flex;align-items:center;justify-content:space-between;gap:15px;flex-wrap:wrap}
    .attention-item--open{padding-bottom:14px}
    .attention-item__main{min-width:0;flex:1 1 380px}
    .attention-item__title{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:8px}
    .attention-item__title strong{font-size:15px;overflow-wrap:anywhere}
    .attention-item p{margin:5px 0;font-size:13px;color:#57665c;line-height:1.5}
    .attention-item p strong{color:#25372b}
    .attention-item__products{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}
    .attention-item__products span{font-size:12px;background:#f2f5f0;color:#325544;border:1px solid #e0e8df;border-radius:6px;padding:5px 9px}
    .attention-item__action{white-space:nowrap}
    .attention-state{display:inline-block;font-size:11px;font-weight:800;padding:5px 9px;border-radius:5px;white-space:nowrap;background:#edf0ee;color:#4d6153}
    .attention-state--confirmed{background:#e3f3e7;color:#176747}
    .attention-state--closed{background:#f2f0ec;color:#6b6252}
    .attention-detail{background:#f7faf7;border:1px solid #dce9de;border-radius:10px;padding:23px;margin-bottom:18px}
    .attention-detail__heading{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
    .attention-detail h3{font:400 25px Georgia,serif;margin:0 0 13px}
    .attention-detail h4{font-size:14px;margin:20px 0 12px}
    .attention-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px 20px;margin:12px 0}
    .attention-summary div{min-width:0}.attention-summary dt{font-size:11px;color:#647469}.attention-summary dd{margin:4px 0 0;font-size:13px;font-weight:700;overflow-wrap:anywhere}
    .attention-detail__products{background:white;border:1px solid #e2e9e2;border-radius:8px;padding:6px 14px}
    .attention-detail__products>div{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;padding:12px 0;font-size:13px;border-bottom:1px solid #e9eee9}
    .attention-detail__products>div:last-child{border-bottom:0}
    .attention-action-section{margin-top:22px;border-top:1px solid #dae8db;padding-top:6px}
    .attention-action-section p,.attention-cancel p,.attention-closed{font-size:13px;line-height:1.6;color:#58705f}
    .attention-action-section form,.attention-cancel form{display:grid;gap:13px;margin-top:14px}
    .attention-check{display:flex!important;align-items:start;gap:10px!important;line-height:1.55}
    .attention-cancel,.attention-events{margin-top:18px;padding-top:15px;border-top:1px solid #dbe4db}
    .attention-cancel summary,.attention-events summary{color:#285d44;font-size:13px;font-weight:700;cursor:pointer}
    .attention-cancel .attention-button--danger{color:#913c3c;border-color:#cc9797;background:#fff4f3;justify-self:start}
    .attention-events p{font-size:12px;line-height:1.55;color:#54695c}
    .attention-error{color:#96343a;background:#fff0f0;padding:14px;border-radius:7px}
    .attention-notice{color:#24583e;background:#e7f4ea;padding:14px;border-radius:7px}
    .attention-empty,.attention-loading,.attention-hint{color:#596d60;font-size:13px;line-height:1.6}
    .attention-closed{background:#f0f2ef;padding:12px;border-radius:7px}
    @media(max-width:740px){.attention-instructions{grid-template-columns:1fr}.attention-search,.attention-summary{grid-template-columns:1fr}.attention-card{padding:18px}.attention-item__action{width:100%}.attention-search-actions button{flex:1 1 130px}}
  `,
})
export class ReservationAttentionPage {
  private readonly api = inject(ReservationAttentionApi);
  private readonly inventory = inject(InventoryApiService);
  private readonly companies = inject(CompanyService);
  private readonly destroyRef = inject(DestroyRef);
  readonly branches = signal<InventoryBranch[]>([]);
  readonly rows = signal<AttentionResult[]>([]);
  readonly selected = signal<AttentionResult | null>(null);
  readonly selectedId = signal<string | null>(null);
  readonly detailLoading = signal(false);
  readonly detailError = signal<string | null>(null);
  readonly loading = signal(false);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly notice = signal<string | null>(null);
  private revision = 0;

  readonly search = new FormGroup({
    sucursal_id: new FormControl<number | null>(null),
    codigo: new FormControl('', { nonNullable: true }),
    cliente_id: new FormControl<number | null>(null),
    estado: new FormControl<AttentionFilter>('CONFIRMADA', { nonNullable: true }),
  });
  readonly delivery = new FormGroup({
    verified: new FormControl(false, { nonNullable: true, validators: [Validators.requiredTrue] }),
    comprobacion: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.minLength(3)] }),
  });
  readonly cancellation = new FormGroup({
    motivo: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.minLength(5)] }),
  });

  constructor() {
    this.companies.changes$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      ++this.revision;
      this.rows.set([]); this.selected.set(null); this.selectedId.set(null);
      this.detailLoading.set(false); this.detailError.set(null); this.branches.set([]);
      this.loading.set(false); this.busy.set(false);
      this.error.set(null); this.notice.set(null);
      this.search.reset({ sucursal_id: null, codigo: '', cliente_id: null, estado: 'CONFIRMADA' });
      this.delivery.reset({ verified: false, comprobacion: '' });
      this.cancellation.reset({ motivo: '' });
      this.refresh();
    });
    this.refresh();
  }
  private refresh(): void {
    if (!this.companies.active()) return;
    const revision = this.revision;
    this.inventory.branches().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: value => { if (revision === this.revision) this.branches.set(value.filter(x => x.activo)); },
      error: () => { if (revision === this.revision) this.error.set('No fue posible cargar las sucursales.'); },
    });
    this.load();
  }
  statusLabel(state: string): string {
    return ({
      CONFIRMADA: 'Confirmada · pendiente de retiro',
      CANCELADA: 'Cancelada',
      ATENDIDA: 'Entregada',
      VENCIDA: 'Vencida',
    } as Record<string, string>)[state] ?? state;
  }

  totalUnits(row: AttentionResult): number {
    return row.lineas.reduce((sum, line) => sum + line.cantidad, 0);
  }

  resetFilters(): void {
    this.search.reset({ sucursal_id: null, codigo: '', cliente_id: null, estado: 'CONFIRMADA' });
    this.load();
  }

  load(): void {
    if (!this.companies.active()) return;
    const revision = this.revision;
    this.loading.set(true);
    this.error.set(null);
    this.api.list({
      sucursal_id: this.search.controls.sucursal_id.value ?? undefined,
      codigo: this.search.controls.codigo.value.trim() || undefined,
      cliente_id: this.search.controls.cliente_id.value ?? undefined,
      estado: this.search.controls.estado.value,
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: rows => {
        if (revision !== this.revision) return;
        this.rows.set(rows);
        this.loading.set(false);
        if (this.selectedId() && !rows.some(row => row.id === this.selectedId())) {
          this.selectedId.set(null);
          this.selected.set(null);
          this.detailError.set(null);
        }
      },
      error: () => {
        if (revision !== this.revision) return;
        this.loading.set(false);
        this.error.set('No pudimos consultar las reservas de tus sucursales. Intenta actualizar.');
      },
    });
  }

  select(row: AttentionResult): void {
    if (this.busy() || (this.detailLoading() && this.selectedId() === row.id)) return;
    if (this.selectedId() === row.id && !this.detailError()) {
      this.selectedId.set(null);
      this.selected.set(null);
      this.detailError.set(null);
      return;
    }
    const revision = this.revision;
    this.selectedId.set(row.id);
    this.selected.set(null);
    this.detailError.set(null);
    this.detailLoading.set(true);
    this.error.set(null);
    this.notice.set(null);
    this.delivery.reset({ verified: false, comprobacion: '' });
    this.cancellation.reset({ motivo: '' });
    this.api.detail(row.id).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: value => {
        if (revision !== this.revision || this.selectedId() !== row.id) return;
        this.detailLoading.set(false);
        this.selected.set(value);
      },
      error: (cause: unknown) => {
        if (revision !== this.revision || this.selectedId() !== row.id) return;
        this.detailLoading.set(false);
        const status = cause instanceof HttpErrorResponse ? cause.status : 0;
        this.detailError.set(status === 404
          ? 'Esta reserva ya no está disponible en la empresa seleccionada.'
          : status === 403
            ? 'No tienes permiso para atender reservas de esta sucursal.'
            : status === 0
              ? 'No se pudo contactar al servidor. Comprueba la conexión y vuelve a intentarlo.'
              : 'No pudimos consultar el estado central de esta reserva. Intenta nuevamente.');
      },
    });
  }

  deliver(row: AttentionResult): void {
    if (this.delivery.invalid || this.busy()) return;
    const revision = this.revision;
    this.busy.set(true); this.error.set(null);
    this.api.deliver(row.id, this.delivery.controls.comprobacion.value).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => { if (revision !== this.revision) return;
        this.busy.set(false); this.selected.set(result);
        this.notice.set('Entrega confirmada: la reserva quedó ATENDIDA y el inventario se actualizó.');
        this.search.controls.estado.setValue('TODAS');
        this.load(); },
      error: () => { if (revision !== this.revision) return; this.busy.set(false);
        this.error.set('No se completó la entrega. Verifica el estado central antes de repetir.'); },
    });
  }
  cancel(row: AttentionResult): void {
    if (this.cancellation.invalid || this.busy()) return;
    const revision = this.revision;
    this.busy.set(true); this.error.set(null);
    this.api.cancel(row.id, this.cancellation.controls.motivo.value).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => { if (revision !== this.revision) return; this.busy.set(false);
        this.selected.set(result);
        this.notice.set('Reserva cancelada. Se liberó el compromiso sin salida física de stock.');
        this.search.controls.estado.setValue('TODAS');
        this.load(); },
      error: () => { if (revision !== this.revision) return; this.busy.set(false);
        this.error.set('Cancelación no permitida o respuesta incierta. Comprueba el estado central.'); },
    });
  }
}
