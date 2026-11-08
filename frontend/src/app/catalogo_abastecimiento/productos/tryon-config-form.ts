import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, Input, OnChanges, OnDestroy, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { Subject, finalize, of, switchMap, takeUntil } from 'rxjs';
import { CompanyService } from '../../organizacion_empresarial/empresa/company.service';
import { Variant } from './variant.model';
import { AnchorKey, GarmentAnchors, anchorLabels, calibrationError, initialAnchors } from './garment-anchors';

interface FittingConfig {
  recurso_url: string; tipo_prenda: 'POLERA' | 'CAMISA'; factor_ancho: number; factor_alto: number;
  offset_x: number; offset_y: number; activo: boolean; anclajes?: GarmentAnchors | null;
}
interface ConfigResponse { configuracion: FittingConfig | null; }
const defaults = { tipo_prenda: 'POLERA' as 'POLERA' | 'CAMISA', factor_ancho: 1.9, factor_alto: 1.2, offset_x: 0, offset_y: 0, activo: true };

@Component({
  selector: 'vn-tryon-config-form',
  imports: [ReactiveFormsModule],
  templateUrl: './tryon-config-form.html',
  styleUrl: './tryon-config-form.css',
})
export class TryOnConfigForm implements OnChanges, OnDestroy {
  @Input({ required: true }) productId!: number;
  @Input({ required: true }) variant!: Variant;
  private readonly http = inject(HttpClient);
  private readonly companies = inject(CompanyService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly changed = new Subject<void>();
  private revision = 0;
  private file: File | null = null;
  private objectUrl: string | null = null;
  private resource: string | null = null;
  readonly loading = signal(false);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly notice = signal<string | null>(null);
  readonly preview = signal<string | null>(null);
  readonly anchors = signal<GarmentAnchors | null>(null);
  readonly anchorLabels = anchorLabels;
  readonly selectedAnchor = signal<AnchorKey>('hombro_izq');
  readonly form = new FormGroup({
    tipo_prenda: new FormControl(defaults.tipo_prenda, { nonNullable: true }),
    factor_ancho: new FormControl(1.9, { nonNullable: true, validators: [Validators.required, Validators.min(.5), Validators.max(2.5)] }),
    factor_alto: new FormControl(1.2, { nonNullable: true, validators: [Validators.required, Validators.min(.5), Validators.max(2.5)] }),
    offset_x: new FormControl(0, { nonNullable: true, validators: [Validators.required, Validators.min(-.5), Validators.max(.5)] }),
    offset_y: new FormControl(0, { nonNullable: true, validators: [Validators.required, Validators.min(-.5), Validators.max(.5)] }),
    activo: new FormControl(true, { nonNullable: true }),
  });

  get endpoint(): string { return `/api/admin/productos/${this.productId}/variantes/${this.variant.id}/vestidor`; }

  ngOnChanges(): void {
    this.changed.next();
    const revision = ++this.revision;
    this.file = null; this.resource = null; this.releasePreview(); this.form.reset(defaults);
    this.anchors.set(null); this.selectedAnchor.set('hombro_izq');
    this.error.set(null); this.notice.set(null); this.loading.set(true); this.busy.set(false);
    this.companies.scoped(company => this.http.get<ConfigResponse>(this.endpoint, { headers: { 'X-Empresa-Id': String(company.id) } }))
      .pipe(takeUntil(this.changed), takeUntilDestroyed(this.destroyRef), finalize(() => { if (revision === this.revision) this.loading.set(false); }))
      .subscribe({ next: result => {
        if (revision !== this.revision || !result.configuracion) return;
        const { recurso_url, anclajes, ...configuration } = result.configuracion;
        this.anchors.set(anclajes ?? null);
        this.resource = recurso_url; this.preview.set(recurso_url);
        this.form.reset({ ...defaults, ...configuration });
      }, error: error => this.fail(error) });
  }

  selectFile(event: Event): void {
    if (this.busy()) return;
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    this.error.set(null); this.notice.set(null);
    if (file.type !== 'image/png' || file.size > 6 * 1024 * 1024 || file.size === 0) {
      this.error.set('Selecciona un PNG con fondo transparente, de hasta 6 MiB.');
      (event.target as HTMLInputElement).value = ''; return;
    }
    this.file = file; this.releasePreview();
    this.anchors.set(null);
    this.objectUrl = URL.createObjectURL(file); this.preview.set(this.objectUrl); this.form.markAsDirty();
  }

  toggleCalibration(): void {
    if (this.busy()) return;
    this.anchors.set(this.anchors() ? null : initialAnchors()); this.form.markAsDirty();
  }
  setSleeves(event: Event): void {
    const current = this.anchors(); if (!current || this.busy()) return;
    const manga = (event.target as HTMLSelectElement).value;
    if (manga === 'LARGA' || manga === 'CORTA') { this.anchors.set({ ...current, manga }); this.form.markAsDirty(); }
  }
  setCoordinate(key: AnchorKey, axis: 'x' | 'y', event: Event): void {
    const current = this.anchors(); if (!current || this.busy()) return;
    const text = (event.target as HTMLInputElement).value;
    this.anchors.set({ ...current, [key]: { ...current[key], [axis]: text === '' ? NaN : Number(text) } }); this.form.markAsDirty();
  }
  markPoint(event: PointerEvent): void {
    const current = this.anchors(); if (!current || this.busy()) return;
    const box = (event.currentTarget as HTMLElement).getBoundingClientRect();
    if (!box.width || !box.height) return;
    const key = this.selectedAnchor();
    this.anchors.set({ ...current, [key]: { x: +Math.min(1,Math.max(0,(event.clientX-box.left)/box.width)).toFixed(3),
      y: +Math.min(1,Math.max(0,(event.clientY-box.top)/box.height)).toFixed(3) } });
    this.form.markAsDirty();
  }

  save(): void {
    if (this.busy() || this.loading() || !this.companies.canManage()) return;
    this.error.set(null); this.notice.set(null);
    if (this.form.invalid || (!this.file && !this.resource)) {
      this.form.markAllAsTouched(); this.error.set('Selecciona el PNG y revisa los valores de calibración.'); return;
    }
    const anchors = this.anchors();
    const invalid = anchors && calibrationError(anchors);
    if (invalid) { this.error.set(invalid); return; }
    const revision = this.revision;
    const endpoint = this.endpoint;
    const values = { ...this.form.getRawValue(), anclajes: anchors };
    this.busy.set(true); this.form.disable();
    this.companies.scoped(company => {
      const headers = { 'X-Empresa-Id': String(company.id) };
      const upload = this.file
        ? this.http.put<{ recurso_url: string }>(endpoint + '/recurso', this.file, { headers: { ...headers, 'Content-Type': 'image/png' } })
        : of({ recurso_url: this.resource! });
      return upload.pipe(switchMap(asset => this.http.put<ConfigResponse>(endpoint, { ...values, recurso_url: asset.recurso_url }, { headers })));
    }).pipe(takeUntil(this.changed), takeUntilDestroyed(this.destroyRef), finalize(() => {
      if (revision === this.revision) { this.busy.set(false); this.form.enable(); }
    })).subscribe({ next: result => {
      if (revision !== this.revision || !result.configuracion) return;
      this.resource = result.configuracion.recurso_url; this.file = null; this.releasePreview(); this.preview.set(this.resource);
      this.anchors.set(result.configuracion.anclajes ?? null);
      this.form.markAsPristine(); this.notice.set('Configuración guardada. Vuelve a abrir el detalle en la app para probar esta variante.');
    }, error: error => this.fail(error) });
  }

  canLeave(): boolean { return !this.busy() && (!this.form.dirty || window.confirm('Hay cambios del vestidor sin guardar. ¿Quieres descartarlos?')); }
  private fail(error: unknown): void {
    this.error.set(error instanceof HttpErrorResponse && typeof error.error?.detail === 'string'
      ? error.error.detail : 'No se pudo consultar o guardar el vestidor. Revisa tu acceso y vuelve a intentar.');
  }
  private releasePreview(): void { if (this.objectUrl) URL.revokeObjectURL(this.objectUrl); this.objectUrl = null; this.preview.set(null); }
  ngOnDestroy(): void { this.revision++; this.changed.next(); this.changed.complete(); this.releasePreview(); }
}
