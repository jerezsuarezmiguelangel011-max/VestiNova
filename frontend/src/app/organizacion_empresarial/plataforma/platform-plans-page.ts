import { HttpErrorResponse } from '@angular/common/http';
import { DatePipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize, forkJoin } from 'rxjs';
import { PlatformCompany, PlatformCompanyService } from './company.service';
import { PlatformPlanService, SaaSPlan, SaaSPlanInput, SubscriptionInput, SubscriptionView } from './plan.service';

function localDateTime(value = new Date()): string {
  return new Date(value.getTime() - value.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

@Component({
  selector: 'vn-platform-plans-page',
  imports: [ReactiveFormsModule, DatePipe],
  templateUrl: './platform-plans-page.html',
  styleUrl: './platform.css',
})
export class PlatformPlansPage {
  private readonly api = inject(PlatformPlanService);
  private readonly companyApi = inject(PlatformCompanyService);
  private readonly destroyRef = inject(DestroyRef);
  readonly plans = signal<SaaSPlan[]>([]);
  readonly subscriptions = signal<SubscriptionView[]>([]);
  readonly companies = signal<PlatformCompany[]>([]);
  readonly editing = signal<SaaSPlan | null>(null);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);
  readonly notice = signal<string | null>(null);
  readonly planForm = new FormGroup({
    codigo: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.minLength(2), Validators.maxLength(40), Validators.pattern(/^[A-Z0-9][A-Z0-9_-]*$/)] }),
    nombre: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.minLength(2), Validators.maxLength(100)] }),
    descripcion: new FormControl('', { nonNullable: true, validators: [Validators.maxLength(500)] }),
    precio_mensual: new FormControl<number | null>(null, [Validators.min(0), Validators.max(99999999.99)]),
    max_sucursales: new FormControl<number | null>(2, [Validators.required, Validators.min(1), Validators.max(10000)]),
    max_productos: new FormControl<number | null>(null, [Validators.min(1), Validators.max(1000000)]),
    max_usuarios: new FormControl<number | null>(null, [Validators.min(1), Validators.max(1000000)]),
    prestaciones: new FormControl('', { nonNullable: true, validators: [Validators.maxLength(2000)] }),
    activo: new FormControl(true, { nonNullable: true }),
  });
  readonly subscriptionForm = new FormGroup({
    empresa_id: new FormControl<number | null>(null, [Validators.required, Validators.min(1)]),
    plan_id: new FormControl<number | null>(null, [Validators.required, Validators.min(1)]),
    estado: new FormControl<SubscriptionInput['estado']>('ACTIVA', { nonNullable: true, validators: [Validators.required] }),
    inicia_en: new FormControl(localDateTime(), { nonNullable: true, validators: [Validators.required] }),
    renueva_en: new FormControl('', { nonNullable: true }),
  });

  ngOnInit(): void { this.load(); }

  load(): void {
    this.loading.set(true); this.error.set(null);
    forkJoin({ plans: this.api.plans(), subscriptions: this.api.subscriptions(), companies: this.companyApi.companies() })
      .pipe(finalize(() => this.loading.set(false)), takeUntilDestroyed(this.destroyRef)).subscribe({
        next: result => { this.plans.set(result.plans); this.subscriptions.set(result.subscriptions); this.companies.set(result.companies); },
        error: error => this.error.set(this.message(error)),
      });
  }

  newPlan(): void {
    this.editing.set(null); this.planForm.enable({ emitEvent: false });
    this.planForm.reset({ codigo: '', nombre: '', descripcion: '', precio_mensual: null, max_sucursales: 2, max_productos: null, max_usuarios: null, prestaciones: '', activo: true });
    this.error.set(null); this.notice.set(null);
  }

  edit(plan: SaaSPlan): void {
    this.editing.set(plan);
    this.planForm.setValue({ codigo: plan.codigo, nombre: plan.nombre, descripcion: plan.descripcion, precio_mensual: plan.precio_mensual === null ? null : Number(plan.precio_mensual), max_sucursales: plan.max_sucursales, max_productos: plan.max_productos, max_usuarios: plan.max_usuarios, prestaciones: plan.prestaciones.join('\n'), activo: plan.activo });
    this.planForm.controls.codigo.disable({ emitEvent: false }); this.planForm.markAsPristine(); this.error.set(null); this.notice.set(null);
  }

  savePlan(): void {
    if (this.saving() || this.planForm.invalid) { this.planForm.markAllAsTouched(); return; }
    const value = this.planForm.getRawValue();
    const input: SaaSPlanInput = {
      codigo: value.codigo.trim().toUpperCase(), nombre: value.nombre.trim(), descripcion: value.descripcion.trim(),
      precio_mensual: value.precio_mensual === null ? null : Number(value.precio_mensual).toFixed(2),
      max_sucursales: Number(value.max_sucursales), max_productos: value.max_productos === null ? null : Number(value.max_productos),
      max_usuarios: value.max_usuarios === null ? null : Number(value.max_usuarios),
      prestaciones: value.prestaciones.split('\n').map(item => item.trim()).filter(Boolean), activo: value.activo,
    };
    const current = this.editing(); this.saving.set(true); this.error.set(null);
    const { codigo: _codigo, ...changes } = input;
    const request = current ? this.api.updatePlan(current.id, changes) : this.api.createPlan(input);
    request.pipe(finalize(() => this.saving.set(false)), takeUntilDestroyed(this.destroyRef)).subscribe({
      next: plan => { this.notice.set(current ? `Plan ${plan.nombre} actualizado.` : `Plan ${plan.nombre} creado.`); this.newPlan(); this.load(); },
      error: error => this.error.set(this.message(error)),
    });
  }

  assign(): void {
    if (this.saving() || this.subscriptionForm.invalid) { this.subscriptionForm.markAllAsTouched(); return; }
    const value = this.subscriptionForm.getRawValue();
    if (!value.empresa_id || !value.plan_id) return;
    const start = new Date(value.inicia_en); const renewal = value.renueva_en ? new Date(value.renueva_en) : null;
    if (!Number.isFinite(start.getTime()) || (renewal && (!Number.isFinite(renewal.getTime()) || renewal < start))) { this.error.set('Revisa las fechas de inicio y renovación.'); return; }
    this.saving.set(true); this.error.set(null);
    this.api.assign(value.empresa_id, { plan_id: value.plan_id, estado: value.estado, inicia_en: start.toISOString(), renueva_en: renewal ? renewal.toISOString() : null })
      .pipe(finalize(() => this.saving.set(false)), takeUntilDestroyed(this.destroyRef)).subscribe({
        next: row => { this.notice.set(`Suscripción de ${row.empresa_nombre} actualizada al plan ${row.plan.nombre}.`); this.load(); },
        error: error => this.error.set(this.message(error)),
      });
  }

  editSubscription(row: SubscriptionView): void {
    this.subscriptionForm.setValue({ empresa_id: row.empresa_id, plan_id: row.plan.id, estado: row.estado === 'PROGRAMADA' ? 'ACTIVA' : row.estado, inicia_en: localDateTime(new Date(row.inicia_en)), renueva_en: row.renueva_en ? localDateTime(new Date(row.renueva_en)) : '' });
    this.subscriptionForm.markAsPristine(); this.error.set(null);
  }

  private message(error: unknown): string {
    if (error instanceof HttpErrorResponse && typeof error.error?.detail === 'string') return error.error.detail;
    return 'No se pudo completar la operación de planes. Revisa los datos y vuelve a intentarlo.';
  }
}
