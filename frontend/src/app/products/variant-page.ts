import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { AbstractControl, FormControl, FormGroup, ReactiveFormsModule, ValidationErrors, Validators } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { Subject, catchError, defer, finalize, forkJoin, of, switchMap, takeUntil } from 'rxjs';
import { CompanyService } from '../company/company.service';
import { Product } from './product.model';
import { ProductService } from './product.service';
import { Variant, VariantInput } from './variant.model';
import { VariantService } from './variant.service';

export function normalizeVariantText(value: string): string { return value.trim().toUpperCase(); }

function variantText(max: number) {
  return (control: AbstractControl): ValidationErrors | null => {
    const value = normalizeVariantText(String(control.value ?? ''));
    if (value.length === 0) return { required: true };
    return Array.from(value).length > max ? { variantLength: { max } } : null;
  };
}

export function variantError(error: unknown): string {
  if (!(error instanceof HttpErrorResponse)) return 'No pudimos completar la operación. Intenta nuevamente.';
  if (error.status === 0) return 'No hay conexión con el servidor. Revisa la conexión e inténtalo nuevamente.';
  if (error.status === 401) return 'La sesión terminó. Vuelve a iniciar sesión.';
  if (error.status === 403) return 'Tu cuenta no tiene permiso para gestionar variantes en esta empresa.';
  if (error.status === 404) return 'La prenda o variante no está disponible en esta empresa.';
  if (error.status === 409) {
    if (error.error?.detail === 'No se puede cambiar la talla o el color de una variante con existencias o movimientos registrados. Desactívala y crea otra variante.') {
      return 'Esta variante ya tiene existencias o movimientos registrados. Conserva su talla y color; puedes desactivarla y registrar otra variante.';
    }
    return 'Ya existe esa combinación de talla y color para esta prenda. Revisa también las variantes inactivas o vuelve a consultar la lista.';
  }
  if (error.status === 422) return 'Revisa la talla, el color y el estado: el servidor no pudo validar los datos.';
  return 'No pudimos completar la operación. Intenta nuevamente.';
}

@Component({
  selector: 'vn-variant-page',
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './variant-page.html',
  styleUrls: ['./products.css', './variant-page.css'],
})
export class VariantPage {
  readonly companies = inject(CompanyService);
  private readonly products = inject(ProductService);
  private readonly api = inject(VariantService);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  private readonly requests = new Subject<number>();
  private readonly productChanged = new Subject<void>();
  private productRevision = 0;
  private readonly initialRevision = this.companies.revision();
  private productId: number | null = null;
  readonly product = signal<Product | null>(null);
  readonly variants = signal<Variant[]>([]);
  readonly editing = signal<Variant | null>(null);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly loadError = signal<string | null>(null);
  readonly error = signal<string | null>(null);
  readonly notice = signal<string | null>(null);
  readonly contextChanged = signal(false);
  readonly form = new FormGroup({
    talla: new FormControl('', { nonNullable: true, validators: [Validators.required, variantText(30)] }),
    color: new FormControl('', { nonNullable: true, validators: [Validators.required, variantText(60)] }),
    activo: new FormControl(true, { nonNullable: true }),
  });

  ngOnInit(): void {
    this.requests.pipe(switchMap(id => defer(() => {
      this.loading.set(true); this.loadError.set(null); this.product.set(null); this.variants.set([]);
      return forkJoin({ product: this.products.get(id), variants: this.api.list(id) }).pipe(
        takeUntil(this.productChanged),
        catchError(error => { this.loadError.set(variantError(error)); return of(null); }),
        finalize(() => this.loading.set(false)),
      );
    })), takeUntilDestroyed(this.destroyRef)).subscribe(result => {
      if (!result || this.contextChanged()) return;
      this.product.set(result.product); this.variants.set(result.variants);
      this.resetEditor();
    });
    this.companies.changes$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(revision => {
      if (revision === this.initialRevision) return;
      this.contextChanged.set(true); this.product.set(null); this.variants.set([]);
      this.editing.set(null); this.notice.set(null); this.error.set(null);
      this.form.reset(); this.form.disable();
    });
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(params => {
      this.productRevision++;
      this.productChanged.next();
      const rawId = params.get('id') ?? '';
      const id = Number(rawId);
      this.notice.set(null); this.error.set(null); this.product.set(null); this.variants.set([]);
      this.resetEditor();
      if (!/^[1-9]\d*$/.test(rawId) || !Number.isSafeInteger(id)) {
        this.productId = null; this.loadError.set('La dirección de la prenda no es válida.'); return;
      }
      this.productId = id;
      this.requests.next(id);
    });
  }

  load(): void {
    if (this.productId === null || this.contextChanged() || this.saving()) return;
    if (this.form.dirty && !window.confirm('Tienes cambios sin guardar. ¿Quieres descartarlos y volver a consultar?')) return;
    this.notice.set(null); this.error.set(null); this.resetEditor();
    this.requests.next(this.productId);
  }

  private resetEditor(): void {
    this.editing.set(null);
    this.form.reset({ talla: '', color: '', activo: true });
    if (this.companies.canManage() && !this.contextChanged()) this.form.enable({ emitEvent: false });
    else this.form.disable({ emitEvent: false });
  }

  newVariant(): void {
    if (!this.companies.canManage() || this.contextChanged() || !this.canLeave()) return;
    this.error.set(null); this.notice.set(null); this.resetEditor();
  }

  edit(variant: Variant): void {
    if (!this.companies.canManage() || this.contextChanged() || this.editing()?.id === variant.id || !this.canLeave()) return;
    const current = this.variants().find(item => item.id === variant.id);
    if (!current) return;
    this.editing.set(current); this.error.set(null); this.notice.set(null);
    this.form.setValue({ talla: current.talla, color: current.color, activo: current.activo });
    this.form.markAsPristine(); this.form.markAsUntouched();
  }

  canLeave(): boolean {
    if (this.contextChanged() || !this.companies.active()) return true;
    if (this.saving()) return false;
    return !this.form.dirty || window.confirm('Tienes cambios sin guardar. ¿Quieres salir y descartarlos?');
  }

  fieldError(field: 'talla' | 'color'): string | null {
    const control = this.form.controls[field];
    if (!control.touched || !control.errors) return null;
    if (control.hasError('required')) return 'Este campo es obligatorio y no puede contener solo espacios.';
    return `Usa como máximo ${field === 'talla' ? 30 : 60} caracteres, incluyendo la normalización a mayúsculas.`;
  }

  submit(): void {
    if (this.saving() || this.loading() || this.loadError() || this.contextChanged() || !this.companies.canManage() || !this.product()) return;
    this.error.set(null); this.notice.set(null);
    if (this.form.invalid) { this.form.markAllAsTouched(); this.error.set('Revisa los campos indicados antes de guardar.'); return; }
    const value = this.form.getRawValue();
    const input: VariantInput = { talla: normalizeVariantText(value.talla), color: normalizeVariantText(value.color), activo: value.activo };
    const current = this.editing();
    if (this.variants().some(item => item.id !== current?.id && normalizeVariantText(item.talla) === input.talla && normalizeVariantText(item.color) === input.color)) {
      this.error.set('Ya existe esa combinación de talla y color para esta prenda. Revisa también las variantes inactivas.'); return;
    }
    const changes: Partial<VariantInput> = {};
    if (current) {
      for (const field of ['talla', 'color', 'activo'] as const) if (input[field] !== current[field]) Object.assign(changes, { [field]: input[field] });
      if (Object.keys(changes).length === 0) { this.error.set('No hay cambios para guardar.'); return; }
    }
    this.saving.set(true); this.form.disable({ emitEvent: false });
    const productId = this.product()!.id;
    const revision = this.productRevision;
    const request = current ? this.api.update(current.id, changes) : this.api.create(productId, input);
    request.pipe(takeUntil(this.productChanged), takeUntilDestroyed(this.destroyRef), finalize(() => this.saving.set(false))).subscribe({
      next: variant => {
        if (revision !== this.productRevision || productId !== this.productId || this.contextChanged()) return;
        this.variants.update(items => [...items.filter(item => item.id !== variant.id), variant].sort((a, b) => a.id - b.id));
        this.resetEditor();
        this.notice.set(current ? 'Cambios guardados en la variante.' : 'Variante registrada correctamente.');
      },
      error: error => {
        if (revision !== this.productRevision || productId !== this.productId || this.contextChanged()) return;
        if (this.companies.canManage()) this.form.enable({ emitEvent: false });
        this.error.set(variantError(error));
      },
    });
  }
}
