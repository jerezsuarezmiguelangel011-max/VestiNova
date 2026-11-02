import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize, forkJoin } from 'rxjs';
import { CompanyService } from '../company/company.service';
import {
  InventoryApiService, InventoryBalance, InventoryBranch,
  InventoryMovement, InventoryPageResult,
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
  private readonly destroyRef = inject(DestroyRef);
  readonly branches = signal<InventoryBranch[]>([]);
  readonly selectedBranch = signal<number | null>(null);
  readonly balances = signal<InventoryPageResult<InventoryBalance>>({ items: [], total: 0, offset: 0, limit: 100 });
  readonly movements = signal<InventoryPageResult<InventoryMovement>>({ items: [], total: 0, offset: 0, limit: 100 });
  readonly loadingBranches = signal(false);
  readonly loadingInventory = signal(false);
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);
  readonly success = signal<string | null>(null);
  readonly movementForm = new FormGroup({
    variante_id: new FormControl<number | null>(null, [Validators.required, Validators.min(1)]),
    tipo: new FormControl<'ENTRADA' | 'SALIDA'>('ENTRADA', { nonNullable: true }),
    cantidad: new FormControl<number | null>(null, [Validators.required, Validators.min(1), Validators.max(1_000_000_000)]),
    motivo: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.minLength(3), Validators.maxLength(300)] }),
  });
  private generation = 0;

  ngOnInit(): void {
    this.companies.changes$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.generation++;
      this.loadingBranches.set(false);
      this.loadingInventory.set(false);
      this.branches.set([]);
      this.selectedBranch.set(null);
      this.balances.set({ items: [], total: 0, offset: 0, limit: 100 });
      this.movements.set({ items: [], total: 0, offset: 0, limit: 100 });
      this.error.set(null);
      this.success.set(null);
      if (this.companies.active()) this.loadBranches();
    });
    this.loadBranches();
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
    this.success.set(null);
    this.loadInventory();
  }

  loadInventory(): void {
    const branchId = this.selectedBranch();
    if (branchId === null || !this.companies.active()) return;
    const current = ++this.generation;
    this.loadingInventory.set(true);
    this.error.set(null);
    forkJoin({
      balances: this.api.balances(branchId),
      movements: this.api.movements(branchId),
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

  submit(): void {
    const branchId = this.selectedBranch();
    if (!this.companies.canManage() || branchId === null || this.saving() || this.loadingInventory()) return;
    this.error.set(null);
    this.success.set(null);
    if (this.movementForm.invalid) {
      this.movementForm.markAllAsTouched();
      this.error.set('Completa la variante, el tipo, una cantidad positiva y el motivo.');
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
    this.api.register({
      id: crypto.randomUUID(),
      sucursal_id: branchId,
      variante_id: variantId,
      tipo: values.tipo,
      cantidad: quantity,
      motivo: values.motivo.trim(),
    }).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.saving.set(false))).subscribe({
      next: () => {
        if (revision !== this.companies.revision() || branchId !== this.selectedBranch()) return;
        this.success.set('Movimiento registrado y saldo actualizado correctamente.');
        this.movementForm.reset({ variante_id: null, tipo: 'ENTRADA', cantidad: null, motivo: '' });
        this.loadInventory();
      },
      error: error => {
        if (revision === this.companies.revision()) this.error.set(inventoryMessage(error));
      },
    });
  }
}
