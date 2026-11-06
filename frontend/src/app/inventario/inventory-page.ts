import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, ElementRef, inject, signal, viewChild } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize, forkJoin } from 'rxjs';
import { CategoryService, ProductCategory } from '../catalogo_abastecimiento/categorias/category.service';
import { CompanyService } from '../organizacion_empresarial/empresa/company.service';
import {
  InventoryApiService, InventoryBalance, InventoryBranch,
  InventoryFilters, InventoryMovement, InventoryPageResult,
} from './inventory-api.service';

export function inventoryMessage(error: unknown): string {
  if (!(error instanceof HttpErrorResponse)) return 'No se pudo consultar el inventario. Intenta nuevamente.';
  if (error.status === 0) return 'Sin conexión con el servidor. Comprueba tu conexión e inténtalo nuevamente.';
  if (error.status === 401) return 'Tu sesión expiró. Vuelve a iniciar sesión.';
  if (error.status === 403) return 'No tienes autorización para operar en esta empresa o sucursal.';
  if (error.status === 404) return 'La sucursal o variante no está disponible en esta empresa.';
  if (error.status === 409) return typeof error.error?.detail === 'string'
    ? error.error.detail : 'La operación entra en conflicto con las existencias actuales.';
  if (error.status === 422) return 'Verifica la variante, la cantidad y el motivo del movimiento.';
  return 'No se pudo completar la operación. Intenta nuevamente.';
}

@Component({
  selector: 'vn-inventory-page',
  imports: [ReactiveFormsModule],
  templateUrl: './inventory-page.html',
  styleUrl: './inventory-page.css',
})
export class InventoryPage {
  readonly companies = inject(CompanyService);
  private readonly api = inject(InventoryApiService);
  private readonly categoryService = inject(CategoryService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly historySection = viewChild<ElementRef<HTMLElement>>('historySection');
  readonly branches = signal<InventoryBranch[]>([]);
  readonly categories = signal<ProductCategory[]>([]);
  readonly activeFilters = signal<InventoryFilters>({});
  readonly filterForm = new FormGroup({
    q: new FormControl('', { nonNullable: true, validators: [Validators.maxLength(120)] }),
    categoria_id: new FormControl<number | null>(null),
    variante_id: new FormControl<number | null>(null, [Validators.min(1)]),
  });
  readonly selectedBranch = signal<number | null>(null);
  readonly selectedHistoryVariant = signal<number | null>(null);
  private pendingAdjustment: { fingerprint: string; id: string } | null = null;
  private pendingReentry: { fingerprint: string; id: string } | null = null;
  readonly balances = signal<InventoryPageResult<InventoryBalance>>({ items: [], total: 0, offset: 0, limit: 100 });
  readonly movements = signal<InventoryPageResult<InventoryMovement>>({ items: [], total: 0, offset: 0, limit: 100 });
  readonly loadingBranches = signal(false);
  readonly loadingInventory = signal(false);
  readonly loadingHistory = signal(false);
  readonly historyError = signal<string | null>(null);
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);
  readonly success = signal<string | null>(null);
  readonly movementForm = new FormGroup({
    variante_id: new FormControl<number | null>(null, [Validators.required, Validators.min(1)]),
    tipo: new FormControl<'INCREMENTO' | 'DISMINUCION'>('INCREMENTO', { nonNullable: true }),
    cantidad: new FormControl<number | null>(null, [Validators.required, Validators.min(1), Validators.max(1_000_000_000)]),
    motivo: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.minLength(3), Validators.maxLength(300)] }),
  });
  readonly reentryForm = new FormGroup({
    solicitud_id: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
    variante_id: new FormControl<number | null>(null, [Validators.required, Validators.min(1)]),
    cantidad: new FormControl<number | null>(null, [Validators.required, Validators.min(1)]),
    motivo: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.minLength(3), Validators.maxLength(300)] }),
    apta_para_venta: new FormControl(false, { nonNullable: true, validators: [Validators.requiredTrue] }),
  });
  private generation = 0;
  private historyRequest = 0;

  ngOnInit(): void {
    this.companies.changes$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.generation++;
      this.historyRequest++;
      this.loadingHistory.set(false);
      this.historyError.set(null);
      this.loadingBranches.set(false);
      this.loadingInventory.set(false);
      this.branches.set([]);
      this.categories.set([]);
      this.activeFilters.set({});
      this.filterForm.reset({ q: '', categoria_id: null, variante_id: null });
      this.selectedBranch.set(null);
      this.selectedHistoryVariant.set(null);
      this.pendingAdjustment = null;
      this.pendingReentry = null;
      this.balances.set({ items: [], total: 0, offset: 0, limit: 100 });
      this.movements.set({ items: [], total: 0, offset: 0, limit: 100 });
      this.error.set(null);
      this.success.set(null);
      if (this.companies.active()) {
        this.loadCategories();
        this.loadBranches();
      }
    });
    this.loadBranches();
    this.loadCategories();
  }

  loadCategories(): void {
    if (!this.companies.active()) return;
    const revision = this.companies.revision();
    this.categoryService.list().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: categories => {
        if (revision === this.companies.revision()) this.categories.set(categories);
      },
      error: error => {
        if (revision === this.companies.revision()) this.error.set(inventoryMessage(error));
      },
    });
  }

  applyFilters(): void {
    if (this.saving() || this.loadingInventory()) return;
    if (this.filterForm.invalid) {
      this.filterForm.markAllAsTouched();
      this.error.set('Revisa el nombre y el identificador de la variante antes de buscar.');
      return;
    }
    const { q, categoria_id, variante_id } = this.filterForm.getRawValue();
    if (
      (categoria_id !== null && (!Number.isSafeInteger(categoria_id) || categoria_id < 1)) ||
      (variante_id !== null && (!Number.isSafeInteger(variante_id) || variante_id < 1))
    ) {
      this.error.set('Los identificadores de categoría y variante deben ser enteros positivos.');
      return;
    }
    const filters: InventoryFilters = {};
    if (q.trim()) filters.q = q.trim();
    if (categoria_id !== null) filters.categoria_id = categoria_id;
    if (variante_id !== null) filters.variante_id = variante_id;
    this.activeFilters.set(filters);
    this.success.set(null);
    this.loadInventory();
  }

  clearFilters(): void {
    if (this.saving() || this.loadingInventory()) return;
    this.filterForm.reset({ q: '', categoria_id: null, variante_id: null });
    this.activeFilters.set({});
    this.success.set(null);
    this.loadInventory();
  }

  loadBranches(): void {
    if (!this.companies.active()) return;
    const current = ++this.generation;
    this.loadingBranches.set(true);
    this.error.set(null);
    this.api.branches().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: branches => {
        if (current !== this.generation) return;
        this.loadingBranches.set(false);
        this.branches.set(branches.filter(branch => branch.activo));
        if (!this.branches().some(branch => branch.id === this.selectedBranch())) {
          this.selectedBranch.set(this.branches()[0]?.id ?? null);
        }
        if (this.selectedBranch() !== null) this.loadInventory();
        else this.loadingInventory.set(false);
      },
      error: error => { if (current === this.generation) { this.error.set(inventoryMessage(error)); this.loadingBranches.set(false); } },
    });
  }

  chooseBranch(raw: string): void {
    const id = Number(raw);
    if (!Number.isSafeInteger(id) || !this.branches().some(branch => branch.id === id)) return;
    this.selectedBranch.set(id);
    this.selectedHistoryVariant.set(null);
    this.historyRequest++;
    this.loadingHistory.set(false);
    this.historyError.set(null);
    this.pendingAdjustment = null;
    this.pendingReentry = null;
    this.success.set(null);
    this.loadInventory();
  }

  loadInventory(): void {
    const branchId = this.selectedBranch();
    if (branchId === null || !this.companies.active()) return;
    const current = ++this.generation;
    this.historyRequest++;
    this.loadingHistory.set(false);
    this.historyError.set(null);
    this.loadingInventory.set(true);
    this.error.set(null);
    forkJoin({
      balances: this.api.balances(branchId, 0, this.activeFilters()),
      movements: this.api.movements(branchId, 0, this.selectedHistoryVariant()),
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        if (current !== this.generation || branchId !== this.selectedBranch()) return;
        this.balances.set(result.balances);
        this.movements.set(result.movements);
        this.loadingInventory.set(false);
      },
      error: error => {
        if (current !== this.generation) return;
        this.error.set(inventoryMessage(error));
        this.loadingInventory.set(false);
      },
    });
  }

  showHistory(variantId: number): void {
    if (this.loadingInventory() || this.selectedBranch() === null) return;
    this.selectedHistoryVariant.set(variantId);
    this.loadSelectedHistory();
    this.historySection()?.nativeElement.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
  }

  showAllHistory(): void {
    if (this.loadingInventory() || this.selectedBranch() === null) return;
    this.selectedHistoryVariant.set(null);
    this.loadSelectedHistory();
  }

  /** Solo refresca el kardex: evita ocultar todo el formulario al consultarlo. */
  private loadSelectedHistory(): void {
    const branchId = this.selectedBranch();
    if (branchId === null || !this.companies.active()) return;
    const variantId = this.selectedHistoryVariant();
    const revision = this.companies.revision();
    const request = ++this.historyRequest;
    this.loadingHistory.set(true);
    this.historyError.set(null);
    this.api.movements(branchId, 0, variantId).pipe(
      takeUntilDestroyed(this.destroyRef),
    ).subscribe({
      next: result => {
        if (request !== this.historyRequest || revision !== this.companies.revision()
            || branchId !== this.selectedBranch() || variantId !== this.selectedHistoryVariant()) return;
        this.movements.set(result);
        this.loadingHistory.set(false);
      },
      error: error => {
        if (request !== this.historyRequest || revision !== this.companies.revision()
            || branchId !== this.selectedBranch()) return;
        this.historyError.set(inventoryMessage(error));
        this.loadingHistory.set(false);
      },
    });
  }

  submit(): void {
    const branchId = this.selectedBranch();
    if (!this.companies.hasPermission('inventario.ajustar') || branchId === null || this.saving() || this.loadingInventory()) return;
    this.error.set(null);
    this.success.set(null);
    if (this.movementForm.invalid) {
      this.movementForm.markAllAsTouched();
      this.error.set('Completa la variante, el tipo de ajuste, una cantidad positiva y el motivo.');
      return;
    }
    const values = this.movementForm.getRawValue();
    const variantId = values.variante_id;
    const quantity = values.cantidad;
    if (!Number.isSafeInteger(variantId) || !Number.isSafeInteger(quantity) ||
      variantId === null || quantity === null || variantId <= 0 || quantity <= 0 ||
      quantity > 1_000_000_000 || values.motivo.trim().length < 3) {
      this.error.set('Los identificadores y cantidades deben ser números enteros positivos.');
      return;
    }
    const revision = this.companies.revision();
    this.saving.set(true);
    const input = {
      sucursal_id: branchId,
      variante_id: variantId,
      tipo: values.tipo,
      cantidad: quantity,
      motivo: values.motivo.trim(),
    };
    const fingerprint = JSON.stringify({ ...input, revision });
    if (this.pendingAdjustment?.fingerprint !== fingerprint) {
      this.pendingAdjustment = { fingerprint, id: crypto.randomUUID() };
    }
    const adjustmentId = this.pendingAdjustment?.id;
    if (!adjustmentId) return;
    this.api.adjust({
      id: adjustmentId,
      sucursal_id: branchId,
      variante_id: variantId,
      tipo: values.tipo,
      cantidad: quantity,
      motivo: values.motivo.trim(),
    }).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.saving.set(false))).subscribe({
      next: () => {
        if (revision !== this.companies.revision() || branchId !== this.selectedBranch()) return;
        this.success.set('Ajuste registrado y existencias recalculadas correctamente.');
        this.pendingAdjustment = null;
        this.movementForm.reset({ variante_id: null, tipo: 'INCREMENTO', cantidad: null, motivo: '' });
        this.loadInventory();
      },
      error: error => {
        if (revision === this.companies.revision()) this.error.set(inventoryMessage(error));
      },
    });
  }

  submitReentry(): void {
    const branchId = this.selectedBranch();
    if (!this.companies.hasPermission('inventario.ajustar') ||
        !this.companies.hasPermission('postventa.consultar') ||
        branchId === null || this.saving() || this.loadingInventory()) return;
    this.error.set(null);
    this.success.set(null);
    if (this.reentryForm.invalid) {
      this.reentryForm.markAllAsTouched();
      this.error.set('Completa la solicitud, variante, cantidad, motivo y confirma la aptitud para venta.');
      return;
    }
    const { solicitud_id, variante_id, cantidad, motivo, apta_para_venta } = this.reentryForm.getRawValue();
    if (!solicitud_id.trim() || !Number.isSafeInteger(variante_id) || !Number.isSafeInteger(cantidad) ||
        variante_id === null || cantidad === null || variante_id < 1 || cantidad < 1 ||
        motivo.trim().length < 3 || !apta_para_venta) {
      this.error.set('Los datos del reingreso no son válidos.');
      return;
    }
    const revision = this.companies.revision();
    const input = {
      solicitud_id: solicitud_id.trim(),
      sucursal_id: branchId,
      variante_id,
      cantidad,
      motivo: motivo.trim(),
      apta_para_venta: true as const,
    };
    const fingerprint = JSON.stringify({ ...input, revision });
    if (this.pendingReentry?.fingerprint !== fingerprint) {
      this.pendingReentry = { fingerprint, id: crypto.randomUUID() };
    }
    const reentryId = this.pendingReentry?.id;
    if (!reentryId) return;
    this.saving.set(true);
    this.api.reenter({
      id: reentryId, ...input,
    }).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.saving.set(false))).subscribe({
      next: () => {
        if (revision !== this.companies.revision() || branchId !== this.selectedBranch()) return;
        this.pendingReentry = null;
        this.success.set('Reingreso vinculado a postventa registrado una única vez.');
        this.reentryForm.reset({ solicitud_id: '', variante_id: null, cantidad: null, motivo: '', apta_para_venta: false });
        this.loadInventory();
      },
      error: error => {
        if (revision === this.companies.revision()) this.error.set(inventoryMessage(error));
      },
    });
  }
}
