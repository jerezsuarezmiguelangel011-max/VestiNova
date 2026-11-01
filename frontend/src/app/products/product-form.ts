import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { AbstractControl, FormControl, FormGroup, ReactiveFormsModule, ValidationErrors, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Subject, catchError, defer, finalize, of, switchMap, takeUntil } from 'rxjs';
import { CompanyService } from '../company/company.service';
import { IMAGE_URL_ERROR, validImageUrl } from './image-url';
import { productError } from './product-errors';
import { Product, ProductInput } from './product.model';
import { ProductService } from './product.service';

function productName(control: AbstractControl): ValidationErrors | null {
  return String(control.value ?? '').trim().length >= 3 ? null : { nameLength: true };
}

export function productPrice(control: AbstractControl): ValidationErrors | null {
  const price = String(control.value ?? '').trim();
  return /^\d{1,8}(?:[.,]\d{1,2})?$/.test(price) && /[1-9]/.test(price)
    ? null : { productPrice: true };
}

function productSlug(control: AbstractControl): ValidationErrors | null {
  const slug = String(control.value ?? '').trim();
  return slug === '' || (slug.length >= 3 && slug.length <= 140 && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug))
    ? null : { productSlug: true };
}

function imageUrl(control: AbstractControl): ValidationErrors | null {
  const value = String(control.value ?? '').trim();
  if (!value) return null;
  return validImageUrl(value) ? null : { imageUrl: true };
}

/** Normaliza el separador y los centavos sin convertir el importe a float. */
export function decimalPrice(value: string): string {
  const [integer, fraction = ''] = value.trim().replace(',', '.').split('.');
  return `${integer.replace(/^0+(?=\d)/, '')}.${fraction.padEnd(2, '0')}`;
}

@Component({
  selector: 'app-product-form',
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './product-form.html',
  styleUrl: './products.css',
})
export class ProductFormPage {
  readonly companies = inject(CompanyService);
  private readonly products = inject(ProductService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  private rawId: string | null = null;
  editing = false;
  private readonly loads = new Subject<number>();
  private readonly productChanged = new Subject<void>();
  private productRevision = 0;
  private readonly initialRevision = this.companies.revision();
  readonly contextChanged = signal(false);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly loadError = signal<string | null>(null);
  readonly error = signal<string | null>(null);
  readonly original = signal<Product | null>(null);
  readonly saved = signal<Product | null>(null);
  readonly form = new FormGroup({
    nombre: new FormControl('', { nonNullable: true, validators: [Validators.required, productName, Validators.maxLength(120)] }),
    descripcion: new FormControl('', { nonNullable: true, validators: [Validators.maxLength(3000)] }),
    precio: new FormControl('', { nonNullable: true, validators: [Validators.required, productPrice] }),
    slug: new FormControl('', { nonNullable: true, validators: [productSlug] }),
    imagen_url: new FormControl('', { nonNullable: true, validators: [imageUrl, Validators.maxLength(2048)] }),
    activo: new FormControl(true, { nonNullable: true }),
  });

  ngOnInit(): void {
    this.products.notice.set(null);
    this.loads.pipe(switchMap(id => defer(() => {
      this.loading.set(true); this.loadError.set(null);
      return this.products.get(id).pipe(
        takeUntil(this.productChanged),
        catchError(error => { this.loadError.set(productError(error)); return of(null); }),
        finalize(() => this.loading.set(false)),
      );
    })), takeUntilDestroyed(this.destroyRef)).subscribe(product => {
      if (!product || this.contextChanged()) return;
      this.original.set(product);
      this.form.setValue({ nombre: product.nombre, descripcion: product.descripcion, precio: product.precio,
        slug: product.slug, imagen_url: product.imagen_url ?? '', activo: product.activo });
      this.form.markAsPristine();
    });
    this.companies.changes$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(revision => {
      if (revision === this.initialRevision) return;
      this.productRevision++;
      this.productChanged.next();
      this.saving.set(false);
      this.contextChanged.set(true);
      this.original.set(null);
      this.saved.set(null);
      this.form.reset();
      this.form.disable();
      this.products.notice.set(null);
    });
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(params => {
      this.productRevision++;
      this.productChanged.next();
      this.saving.set(false);
      this.rawId = params.get('id');
      this.editing = this.rawId !== null;
      this.original.set(null); this.saved.set(null); this.error.set(null); this.loadError.set(null);
      this.form.reset();
      if (!this.contextChanged() && this.companies.canManage()) this.form.enable({ emitEvent: false });
      this.form.controls.slug.setValidators(this.editing ? [Validators.required, productSlug] : [productSlug]);
      this.form.controls.slug.updateValueAndValidity();
      if (this.editing) this.load();
    });
  }

  load(): void {
    if (this.contextChanged() || !this.companies.canManage()) return;
    const id = Number(this.rawId);
    if (!/^[1-9]\d*$/.test(this.rawId ?? '') || !Number.isSafeInteger(id)) { this.loadError.set('La dirección del producto no es válida.'); return; }
    this.loads.next(id);
  }

  canLeave(): boolean {
    if (!this.companies.active() || this.contextChanged()) return true;
    if (this.saving()) return false;
    return this.saved() !== null || !this.form.dirty || window.confirm('Tienes cambios sin guardar. ¿Quieres salir y descartarlos?');
  }

  fieldError(name: keyof typeof this.form.controls): string | null {
    const control = this.form.controls[name];
    if (!control.touched || !control.errors) return null;
    if (control.hasError('required')) return 'Este campo es obligatorio.';
    if (control.hasError('nameLength')) return 'Escribe al menos 3 caracteres.';
    if (control.hasError('maxlength')) return `El límite es ${control.errors['maxlength'].requiredLength} caracteres.`;
    if (control.hasError('productPrice')) return 'Usa un precio mayor a 0, hasta 99999999.99, con dos decimales como máximo.';
    if (control.hasError('productSlug')) return 'Usa de 3 a 140 letras minúsculas, números y guiones entre palabras.';
    if (control.hasError('imageUrl')) return IMAGE_URL_ERROR;
    return 'Revisa este campo.';
  }

  submit(): void {
    if (this.saving() || this.loading() || this.loadError() || this.saved() || this.contextChanged() || !this.companies.canManage()) return;
    this.error.set(null);
    if (this.form.invalid) { this.form.markAllAsTouched(); this.error.set('Revisa los campos indicados antes de guardar.'); return; }
    const value = this.form.getRawValue();
    const input: ProductInput = {
      nombre: value.nombre.trim(), descripcion: value.descripcion.trim(),
      precio: decimalPrice(value.precio), imagen_url: value.imagen_url.trim() || null,
      activo: value.activo,
      ...(value.slug.trim() ? { slug: value.slug.trim() } : {}),
    };
    const original = this.original();
    if (this.editing && original === null) return;
    const changes: Partial<ProductInput> = {};
    if (original !== null) {
      for (const key of Object.keys(input) as (keyof ProductInput)[]) {
        if (input[key] !== original[key]) Object.assign(changes, { [key]: input[key] });
      }
      if (Object.keys(changes).length === 0) { this.error.set('No hay cambios para guardar.'); return; }
    }
    this.saving.set(true);
    this.form.disable({ emitEvent: false });
    const revision = this.productRevision;
    const request = original !== null ? this.products.update(original.id, changes) : this.products.create(input);
    request.pipe(takeUntil(this.productChanged), takeUntilDestroyed(this.destroyRef), finalize(() => {
      if (revision === this.productRevision) this.saving.set(false);
    })).subscribe({
      next: product => {
        if (revision !== this.productRevision || this.contextChanged()) return;
        this.saved.set(product);
        this.form.markAsPristine();
        this.saving.set(false);
        this.products.notice.set(this.editing ? 'Cambios guardados en el producto.' : 'Producto registrado correctamente.');
        void this.router.navigate(['/admin/productos']).then(navigated => {
          if (revision !== this.productRevision || this.contextChanged()) return;
          if (!navigated) this.error.set('El producto se guardó. Vuelve al listado para consultarlo.');
        }).catch(() => {
          if (revision === this.productRevision && !this.contextChanged()) this.error.set('El producto se guardó. Vuelve al listado para consultarlo.');
        });
      },
      error: error => {
        if (revision !== this.productRevision || this.contextChanged()) return;
        this.form.enable({ emitEvent: false }); this.error.set(productError(error));
      },
    });
  }
}
