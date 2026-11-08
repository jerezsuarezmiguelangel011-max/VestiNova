import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { CompanyService } from '../organizacion_empresarial/empresa/company.service';
import { InventoryApiService, type InventoryBranch } from '../inventario/inventory-api.service';
import { ReportsApi, type CommercialReport, type ReportType } from './reports-api.service';

function utcDate(daysBack: number): string {
  const now = new Date();
  now.setUTCDate(now.getUTCDate() - daysBack);
  return now.toISOString().slice(0, 10);
}

@Component({
  selector: 'vn-commercial-reports',
  imports: [ReactiveFormsModule],
  template: `
    <section class="report-page">
      <p class="report-tag">VestiNova · CU20</p>
      <h1>Reportes comerciales</h1>
      <p>Indicadores de ventas, reservas e inventario según la empresa y las sucursales autorizadas.
        Las operaciones offline pendientes no se suman como ventas confirmadas.</p>
      <form class="report-form" [formGroup]="filters" (ngSubmit)="load()">
        <label>Tipo de reporte
          <select formControlName="tipo">
            <option value="resumen">Resumen general</option>
            <option value="ventas">Ventas confirmadas</option>
            <option value="reservas">Reservas</option>
            <option value="inventario">Inventario actual</option>
          </select>
        </label>
        <label>Desde (UTC)
          <input type="date" formControlName="desde" />
        </label>
        <label>Hasta (UTC)
          <input type="date" formControlName="hasta" />
        </label>
        <label>Sucursal
          <select formControlName="sucursal_id">
            <option [ngValue]="null">Todas mis sucursales</option>
            @for (branch of branches(); track branch.id) {
              <option [ngValue]="branch.id">{{ branch.nombre }}</option>
            }
          </select>
        </label>
        <button type="submit" [disabled]="loading()">
          {{ loading() ? 'Generando…' : 'Consultar reporte' }}
        </button>
      </form>
      @if (error(); as message) { <p class="report-error" role="alert">{{ message }}</p> }
      @if (loading()) { <p role="status">Calculando indicadores con registros centrales…</p> }
      @if (result(); as report) {
        <p class="report-period">Período UTC: <strong>{{ report.desde }}</strong> al
          <strong>{{ report.hasta }}</strong>. {{ report.nota }}</p>
        <div class="report-cards">
          @if (report.tipo === 'resumen' || report.tipo === 'ventas') {
            <article><span>Ventas confirmadas</span><strong>{{ report.totales.ventas_confirmadas }}</strong>
              <small>Digitales {{ report.totales.ventas_digitales }} · Efectivo {{ report.totales.ventas_efectivo }}</small></article>
            <article><span>Importe registrado (BOB)</span><strong>Bs {{ report.totales.ingresos_confirmados }}</strong>
              <small>Incluye {{ report.totales.ventas_demo }} venta(s) ficticia(s) identificada(s) como DEMO, si existen.</small></article>
          }
          @if (report.tipo === 'resumen' || report.tipo === 'reservas') {
            <article><span>Reservas confirmadas</span><strong>{{ report.totales.reservas_confirmadas }}</strong>
              <small>Atendidas {{ report.totales.reservas_atendidas }}</small></article>
            <article><span>Reservas no activas</span>
              <strong>{{ report.totales.reservas_canceladas + report.totales.reservas_vencidas }}</strong>
              <small>Canceladas {{ report.totales.reservas_canceladas }} · Vencidas {{ report.totales.reservas_vencidas }}</small></article>
          }
          @if (report.tipo === 'resumen' || report.tipo === 'inventario') {
            <article><span>Unidades físicas actuales</span><strong>{{ report.totales.stock_fisico_actual }}</strong></article>
            <article><span>Disponibles actualmente</span><strong>{{ report.totales.stock_disponible_actual }}</strong>
              <small>Comprometidas {{ report.totales.stock_comprometido_actual }}</small></article>
          }
        </div>
        @if (report.tipo === 'resumen' || report.tipo === 'ventas') {
          <section class="report-table">
            <h2>Prendas vendidas por color y talla</h2>
            <p>Desglose de unidades y valores de operaciones aceptadas. Los datos
               etiquetados DEMO son ficticios y solo sirven para una exposición.</p>
            <div class="report-scroll">
              <table>
                <thead><tr><th>Prenda</th><th>Categoría</th><th>Sucursal</th><th>Talla</th>
                  <th>Color</th><th>Unidades</th><th>Importe Bs</th><th>Origen</th></tr></thead>
                <tbody>
                  @for (row of report.ventas_por_prenda; track $index) {
                    <tr>
                      <th scope="row">{{ row.producto }}</th>
                      <td>{{ row.categoria }}</td>
                      <td>{{ branchName(row.sucursal_id) }}</td>
                      <td>{{ row.talla }}</td><td>{{ row.color }}</td>
                      <td>{{ row.unidades }}</td><td>{{ row.importe }}</td>
                      <td>{{ row.es_demo ? 'DEMO · ficticia' : 'Operación central' }}</td>
                    </tr>
                  } @empty {
                    <tr><td colspan="8">No hay líneas de venta para este período.</td></tr>
                  }
                </tbody>
              </table>
            </div>
          </section>
        }
        <section class="report-table">
          <h2>Detalle por sucursal</h2>
          <div class="report-scroll">
            <table>
              <thead><tr>
                <th>Sucursal</th>
                @if (report.tipo === 'resumen' || report.tipo === 'ventas') {
                  <th>Ventas</th><th>Importe Bs</th>
                }
                @if (report.tipo === 'resumen' || report.tipo === 'reservas') {
                  <th>Reservas confirmadas</th><th>Atendidas</th>
                }
                @if (report.tipo === 'resumen' || report.tipo === 'inventario') {
                  <th>Stock físico</th><th>Comprometido</th><th>Disponible</th>
                }
              </tr></thead>
              <tbody>
              @for (row of report.por_sucursal; track row.sucursal_id) {
                <tr><th scope="row">{{ row.sucursal }}</th>
                @if (report.tipo === 'resumen' || report.tipo === 'ventas') {
                  <td>{{ row.ventas_confirmadas }}</td><td>{{ row.ingresos_confirmados }}</td>
                }
                @if (report.tipo === 'resumen' || report.tipo === 'reservas') {
                  <td>{{ row.reservas_confirmadas }}</td><td>{{ row.reservas_atendidas }}</td>
                }
                @if (report.tipo === 'resumen' || report.tipo === 'inventario') {
                  <td>{{ row.stock_fisico_actual }}</td><td>{{ row.stock_comprometido_actual }}</td><td>{{ row.stock_disponible_actual }}</td>
                }
                </tr>
              } @empty { <tr><td>No hay sucursales autorizadas para esta consulta.</td></tr> }
              </tbody>
            </table>
          </div>
        </section>
      }
    </section>
  `,
  styles: `
    :host{display:block}.report-page{max-width:1200px;margin:auto;color:#26392d}
    .report-page h1{font:400 clamp(32px,5vw,46px) Georgia,serif;margin:10px 0}
    .report-page>p{line-height:1.7}.report-tag{font-size:11px;text-transform:uppercase;letter-spacing:.1em;color:#146349;font-weight:700}
    .report-form{display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:14px;background:#fff;padding:22px;border:1px solid #d8e2d8;border-radius:12px;margin:22px 0}
    .report-form label{display:grid;gap:8px;font-size:12px;font-weight:700}
    .report-form input,.report-form select{padding:10px;border:1px solid #aabbab;min-height:43px;min-width:0;border-radius:5px}
    .report-form button{background:#e6f2e9;color:#13543c;border:1px solid #accdb7;border-radius:6px;padding:9px;min-height:43px;cursor:pointer}
    .report-form button:disabled{opacity:.55}.report-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:13px;margin:22px 0}
    .report-cards article{background:#fff;border:1px solid #d6e1d7;border-radius:10px;padding:20px;display:grid;gap:9px}
    .report-cards article span{font-size:13px;color:#617564}
    .report-cards article strong{font:400 29px Georgia,serif;color:#154c38}
    .report-cards article small{font-size:11px;color:#617564}
    .report-period{font-size:13px;color:#586d5e}.report-error{color:#a22836;background:#fff0f0;padding:12px}
    .report-table{background:white;border:1px solid #d6e1d7;border-radius:12px;padding:20px;margin:24px 0}
    .report-table h2{font:400 26px Georgia,serif}.report-scroll{overflow:auto}
    .report-table table{width:100%;border-collapse:collapse;min-width:660px;text-align:left}
    .report-table :is(td,th){padding:12px;border-bottom:1px solid #e5ece5;font-size:13px}
  `,
})
export class ReportsPage {
  private readonly api = inject(ReportsApi);
  private readonly inventory = inject(InventoryApiService);
  private readonly company = inject(CompanyService);
  private readonly destroyRef = inject(DestroyRef);
  readonly branches = signal<InventoryBranch[]>([]);
  readonly result = signal<CommercialReport | null>(null);
  readonly error = signal<string | null>(null);
  readonly loading = signal(false);
  readonly filters = new FormGroup({
    tipo: new FormControl<ReportType>('resumen', { nonNullable: true }),
    desde: new FormControl(utcDate(29), { nonNullable: true }),
    hasta: new FormControl(utcDate(0), { nonNullable: true }),
    sucursal_id: new FormControl<number | null>(null),
  });
  private revision = 0;

  constructor() {
    this.company.changes$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.revision++;
      this.result.set(null);
      this.branches.set([]);
      this.loadAll();
    });
    this.loadAll();
  }
  private loadAll(): void {
    if (!this.company.active()) return;
    const revision = this.revision;
    this.inventory.branches().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: items => { if (revision === this.revision) this.branches.set(items.filter(item => item.activo)); },
      error: () => { if (revision === this.revision) this.error.set('No se pudieron consultar las sucursales.'); },
    });
    this.load();
  }
  branchName(id: number): string {
    return this.branches().find(branch => branch.id === id)?.nombre ?? ('Sucursal #' + id);
  }

  load(): void {
    if (!this.company.active()) return;
    const filters = this.filters.getRawValue();
    if (!filters.desde || !filters.hasta || filters.desde > filters.hasta) {
      this.error.set('Elige un intervalo de fechas válido.');
      return;
    }
    const revision = this.revision;
    this.loading.set(true); this.error.set(null); this.result.set(null);
    this.api.load(filters).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: data => { if (revision === this.revision) { this.loading.set(false); this.result.set(data); } },
      error: () => { if (revision === this.revision) {
        this.loading.set(false);
        this.error.set('No se pudo consultar el reporte. Verifica fechas, empresa y permisos.');
      } },
    });
  }
}
