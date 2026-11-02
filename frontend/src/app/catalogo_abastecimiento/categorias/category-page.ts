import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize } from 'rxjs';
import { CompanyService } from '../../organizacion_empresarial/empresa/company.service';
import { CategoryService, ProductCategory } from './category.service';

@Component({
  selector: 'vn-category-page',
  imports: [ReactiveFormsModule],
  templateUrl: './category-page.html',
  styleUrl: './category-page.css',
})
export class CategoryPage {
  readonly companies = inject(CompanyService);
  private readonly api = inject(CategoryService);
  private readonly destroyRef = inject(DestroyRef);
  readonly categories = signal<ProductCategory[]>([]);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);
  readonly notice = signal<string | null>(null);
  readonly editing = signal<ProductCategory | null>(null);
  readonly form = new FormGroup({
    nombre: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.minLength(2), Validators.maxLength(100)] }),
    descripcion: new FormControl('', { nonNullable: true, validators: [Validators.maxLength(500)] }),
  });

  ngOnInit(): void {
    this.reload();
    this.companies.changes$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.categories.set([]);
      this.newCategory();
      this.reload();
    });
  }

  reload(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.list().pipe(finalize(() => this.loading.set(false)), takeUntilDestroyed(this.destroyRef)).subscribe({
      next: rows => this.categories.set(rows),
      error: () => this.error.set('No pudimos cargar las categorías de esta empresa.'),
    });
  }

  newCategory(): void {
    this.editing.set(null);
    this.form.reset({ nombre: '', descripcion: '' });
    this.error.set(null);
  }

  edit(category: ProductCategory): void {
    this.editing.set(category);
    this.form.setValue({ nombre: category.nombre, descripcion: category.descripcion });
    this.error.set(null);
  }

  submit(): void {
    if (this.saving()) return;
    this.error.set(null);
    if (this.form.invalid) { this.form.markAllAsTouched(); return; }
    const value = { nombre: this.form.controls.nombre.value.trim(), descripcion: this.form.controls.descripcion.value.trim() };
    const current = this.editing();
    this.saving.set(true);
    const request = current ? this.api.update(current.id, value) : this.api.create(value);
    request.pipe(finalize(() => this.saving.set(false)), takeUntilDestroyed(this.destroyRef)).subscribe({
      next: category => {
        this.notice.set(current ? `Se actualizó ${category.nombre}.` : `Se creó la categoría ${category.nombre}.`);
        this.newCategory();
        this.reload();
      },
      error: error => this.error.set(error?.status === 409 ? 'Ya existe una categoría con ese nombre en esta empresa.' : 'No pudimos guardar la categoría. Revisa los datos e inténtalo nuevamente.'),
    });
  }

  toggleActive(category: ProductCategory): void {
    if (this.saving()) return;
    this.saving.set(true);
    this.error.set(null);
    this.api.update(category.id, { activo: !category.activo }).pipe(finalize(() => this.saving.set(false)), takeUntilDestroyed(this.destroyRef)).subscribe({
      next: updated => { this.notice.set(`${updated.nombre} quedó ${updated.activo ? 'activa' : 'inactiva'}.`); this.reload(); },
      error: () => this.error.set('No pudimos cambiar el estado de la categoría.'),
    });
  }
}
