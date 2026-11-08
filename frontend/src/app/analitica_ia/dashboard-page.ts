import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { finalize } from 'rxjs';
import { CompanyService } from '../organizacion_empresarial/empresa/company.service';
import { AnalyticsService, PredictiveDashboard, ReportOptions, analyticsError, formFilters } from './analytics.service';
import { ModelEvaluation } from './model-evaluation';

@Component({ selector: 'vn-predictive-dashboard', imports: [ReactiveFormsModule, ModelEvaluation], templateUrl: './dashboard-page.html', styleUrls: ['./analytics.css','./dashboard-page.css'] })
export class DashboardPage {
  readonly companies = inject(CompanyService);
  private readonly api = inject(AnalyticsService);
  private readonly destroyRef = inject(DestroyRef);
  readonly options = signal<ReportOptions | null>(null);
  readonly data = signal<PredictiveDashboard | null>(null);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly registeredUnits = computed(() => this.data()?.filas.reduce((sum,row)=>sum+row.unidades_reales_7d,0) ?? 0);
  readonly estimatedUnits = computed(() => this.data()?.filas.reduce((sum,row)=>sum+(row.demanda_estimada_7d ?? 0),0) ?? 0);
  readonly groups = computed(() => {
    const data=this.data(); if (!data || data.analisis==='prediccion') return [];
    const labels=data.modelo.no_supervisado.etiquetas ?? [...new Set(data.filas.flatMap(row=>row.agrupacion_estimada ? [row.agrupacion_estimada] : []))];
    return labels.map(name=>({name,count:data.filas.filter(row=>row.agrupacion_estimada===name).length}));
  });
  readonly populatedGroups = computed(() => this.groups().filter(group=>group.count>0).length);
  private revision = 0;
  readonly form = new FormGroup({ desde: new FormControl('', {nonNullable:true}), hasta: new FormControl('', {nonNullable:true}), sucursal_id: new FormControl('', {nonNullable:true}), categoria_id: new FormControl('', {nonNullable:true}), producto_id: new FormControl('', {nonNullable:true}), analisis: new FormControl('ambos', {nonNullable:true}) });
  constructor() { this.companies.changes$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => { this.revision++; this.data.set(null); this.options.set(null); this.loading.set(false); this.form.reset(); this.error.set('La empresa cambió. Actualiza el módulo para consultar el nuevo contexto.'); }); }
  ngOnInit(): void { this.loadOptions(); this.consult(); }
  loadOptions(): void { this.api.options().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({ next: value => this.options.set(value), error: error => this.error.set(analyticsError(error)) }); }
  consult(): void {
    if (this.loading()) return;
    this.data.set(null); this.error.set(null); this.loading.set(true); const revision = ++this.revision;
    const value = this.form.getRawValue();
    this.api.dashboard(formFilters(value), value.analisis).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => { if (revision === this.revision) this.loading.set(false); })).subscribe({ next: result => { if (revision === this.revision) this.data.set(result); }, error: error => { if (revision === this.revision) this.error.set(analyticsError(error)); } });
  }
  chartWidth(value: number): number { const maximum = Math.max(1, ...(this.data()?.filas.flatMap(row => [row.unidades_reales_7d, row.demanda_estimada_7d ?? 0]) ?? [])); return 100 * value / maximum; }
  format(value:number,digits=0): string { return new Intl.NumberFormat('es-BO',{maximumFractionDigits:digits}).format(value); }
  shortDate(value:string|undefined):string { if (!value) return ''; const [year,month,day]=value.split('-'); return `${day}/${month}/${year}`; }
}
