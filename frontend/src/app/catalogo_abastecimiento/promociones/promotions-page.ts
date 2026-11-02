import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize, forkJoin } from 'rxjs';
import { CompanyService } from '../../organizacion_empresarial/empresa/company.service';
import { Product } from '../productos/product.model';
import { ProductService } from '../productos/product.service';
import { Promotion, PromotionInput, PromotionService } from './promotion.service';

function localDateTime(value: string): string {
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

@Component({
  selector: 'vn-promotions-page',
  imports: [ReactiveFormsModule, DatePipe],
  templateUrl: './promotions-page.html',
  styleUrl: './promotions-page.css',
})
export class PromotionsPage {
  readonly companies = inject(CompanyService);
  private readonly api = inject(PromotionService);
  private readonly productsApi = inject(ProductService);
  private readonly destroyRef = inject(DestroyRef);
  readonly promotions = signal<Promotion[]>([]);
  readonly products = signal<Product[]>([]);
  readonly selectedProductIds = signal<number[]>([]);
  readonly editing = signal<Promotion | null>(null);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);
  readonly notice = signal<string | null>(null);
  readonly form = new FormGroup({
    nombre: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.minLength(3), Validators.maxLength(120)] }),
    tipo: new FormControl<'PORCENTAJE' | 'PRECIO_FIJO'>('PORCENTAJE', { nonNullable: true, validators: [Validators.required] }),
    valor: new FormControl<number | null>(null, [Validators.required, Validators.min(0.01), Validators.max(99999999.99)]),
    inicio: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
    fin: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
  });

  ngOnInit(): void {
    this.load();
    this.companies.changes$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.promotions.set([]); this.products.set([]); this.reset(); this.load();
    });
  }

  load(): void {
    if (!this.companies.canViewPromotions()) return;
    this.loading.set(true); this.error.set(null);
    forkJoin({
      promotions: this.api.list(),
      products: this.productsApi.list({ activo: true, limit: 100, offset: 0 }),
    }).pipe(finalize(() => this.loading.set(false)), takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => { this.promotions.set(result.promotions); this.products.set(result.products.items); },
      error: error => this.error.set(this.message(error)),
    });
  }

  reset(): void {
    this.editing.set(null); this.selectedProductIds.set([]);
    this.form.reset({ nombre: '', tipo: 'PORCENTAJE', valor: null, inicio: '', fin: '' });
  }

  newPromotion(): void {
    this.notice.set(null); this.error.set(null); this.reset();
  }

  edit(promotion: Promotion): void {
    this.editing.set(promotion);
    this.selectedProductIds.set([...promotion.producto_ids]);
    this.form.setValue({ nombre: promotion.nombre, tipo: promotion.tipo, valor: Number(promotion.valor), inicio: localDateTime(promotion.inicio), fin: localDateTime(promotion.fin) });
    this.form.markAsPristine(); this.notice.set(null); this.error.set(null);
  }

  toggleProduct(id: number, checked: boolean): void {
    this.selectedProductIds.update(ids => checked ? [...new Set([...ids, id])] : ids.filter(value => value !== id));
  }

  selected(id: number): boolean { return this.selectedProductIds().includes(id); }

  submit(): void {
    if (this.saving()) return;
    this.error.set(null);
    if (this.form.invalid || this.selectedProductIds().length === 0) { this.form.markAllAsTouched(); this.error.set('Completa las fechas y selecciona al menos un producto.'); return; }
    const value = this.form.getRawValue();
    const start = new Date(value.inicio); const end = new Date(value.fin);
    if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || end <= start) { this.error.set('La fecha final debe ser posterior a la inicial.'); return; }
    if (value.tipo === 'PORCENTAJE' && (value.valor ?? 0) >= 100) { this.error.set('El descuento debe ser menor al 100 %.'); return; }
    const input: PromotionInput = {
      nombre: value.nombre.trim(), tipo: value.tipo, valor: Number(value.valor).toFixed(2),
      inicio: start.toISOString(), fin: end.toISOString(), producto_ids: [...this.selectedProductIds()],
    };
    const current = this.editing(); this.saving.set(true);
    const request = current ? this.api.update(current.id, input) : this.api.create(input);
    request.pipe(finalize(() => this.saving.set(false)), takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => { this.notice.set(current ? `Se actualizaron los datos de ${result.nombre}.` : `Se registró la promoción ${result.nombre}.`); this.reset(); this.load(); },
      error: error => this.error.set(this.message(error)),
    });
  }

  toggleActive(promotion: Promotion): void {
    if (this.saving()) return;
    this.saving.set(true); this.error.set(null);
    this.api.update(promotion.id, { activo: !promotion.activo }).pipe(finalize(() => this.saving.set(false)), takeUntilDestroyed(this.destroyRef)).subscribe({
      next: value => { this.notice.set(`${value.nombre} quedó ${value.activo ? 'activa' : 'inactiva'}.`); this.load(); },
      error: error => this.error.set(this.message(error)),
    });
  }

  productNames(ids: number[]): string {
    const names = new Map(this.products().map(product => [product.id, product.nombre]));
    return ids.map(id => names.get(id) ?? `Producto ${id}`).join(', ');
  }

  private message(error: unknown): string {
    if (error instanceof HttpErrorResponse && typeof error.error?.detail === 'string') return error.error.detail;
    return 'No pudimos completar la operación. Revisa los datos y vuelve a intentarlo.';
  }
}
