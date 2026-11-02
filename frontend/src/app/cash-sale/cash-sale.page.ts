import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { forkJoin } from 'rxjs';
import { CompanyService } from '../company/company.service';
import { InventoryApiService, type InventoryBranch } from '../inventory/inventory-api.service';
import { ProductService } from '../products/product.service';
import type { Product } from '../products/product.model';
import { VariantService } from '../products/variant.service';
import type { Variant } from '../products/variant.model';
import { formatCents, quoteCashSale, type CashQuote } from './cash-sale.domain';

export interface CashSalePreview {
  id: string;
  empresa_id: number;
  sucursal_id: number;
  producto_id: number;
  variante_id: number;
  cantidad: number;
  precio_unitario: string;
  total: string;
  efectivo_propuesto: string;
  cambio: string;
  creado_en: string;
  estado: 'BORRADOR_SIN_COBRO';
}

@Component({
  selector: 'vn-cash-sale-page',
  imports: [ReactiveFormsModule],
  templateUrl: './cash-sale.page.html',
  styleUrl: './cash-sale.page.css',
})
export class CashSalePage implements OnInit {
  readonly companies = inject(CompanyService);
  private readonly inventory = inject(InventoryApiService);
  private readonly productsApi = inject(ProductService);
  private readonly variantApi = inject(VariantService);
  private readonly destroyRef = inject(DestroyRef);
  readonly branches = signal<InventoryBranch[]>([]);
  readonly products = signal<Product[]>([]);
  readonly variants = signal<Variant[]>([]);
  readonly loading = signal(false);
  readonly variantsLoading = signal(false);
  readonly error = signal<string | null>(null);
  readonly draft = signal<CashSalePreview | null>(null);
  readonly form = new FormGroup({
    sucursal_id: new FormControl<number | null>(null, [Validators.required, Validators.min(1)]),
    producto_id: new FormControl<number | null>(null, [Validators.required, Validators.min(1)]),
    variante_id: new FormControl<number | null>(null, [Validators.required, Validators.min(1)]),
    cantidad: new FormControl<number>(1, { nonNullable: true, validators: [Validators.required, Validators.min(1), Validators.max(100)] }),
    efectivo: new FormControl<string>('0.00', { nonNullable: true, validators: [Validators.required, Validators.pattern(/^(?:0|[1-9]\d{0,7})\.\d{2}$/)] }),
  });
  readonly product = computed(() => this.products().find(p => p.id === this.form.controls.producto_id.value));
  private revision = 0;
  private variantsRequest = 0;

  ngOnInit(): void {
    this.companies.changes$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.revision++;
      this.variantsRequest++;
      this.branches.set([]);
      this.products.set([]);
      this.variants.set([]);
      this.draft.set(null);
      this.form.reset({ sucursal_id: null, producto_id: null, variante_id: null, cantidad: 1, efectivo: '0.00' });
      this.loading.set(false);
      this.variantsLoading.set(false);
      this.error.set(null);
      this.load();
    });
    this.load();
  }

  load(): void {
    if (!this.companies.active()) return;
    const token = ++this.revision;
    this.loading.set(true);
    this.error.set(null);
    forkJoin({
      branches: this.inventory.branches(),
      products: this.productsApi.list({ activo: true, limit: 100, offset: 0 }),
    }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: ({ branches, products }) => {
        if (token !== this.revision) return;
        this.branches.set(branches.filter(b => b.activo));
        this.products.set(products.items.filter(p => p.activo));
        this.loading.set(false);
      },
      error: () => {
        if (token !== this.revision) return;
        this.error.set('No fue posible consultar las sucursales o las prendas de tu empresa.');
        this.loading.set(false);
      },
    });
  }

  chooseProduct(value: string): void {
    const id = Number(value);
    const token = ++this.variantsRequest;
    this.variants.set([]);
    this.draft.set(null);
    this.form.controls.variante_id.setValue(null);
    this.form.controls.producto_id.setValue(Number.isSafeInteger(id) && this.products().some(p => p.id === id) ? id : null);
    const selected = this.form.controls.producto_id.value;
    if (selected === null) { this.variantsLoading.set(false); return; }
    this.variantsLoading.set(true);
    this.variantApi.list(selected).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: variants => {
        if (token !== this.variantsRequest) return;
        this.variants.set(variants.filter(v => v.activo && v.producto_id === selected));
        this.variantsLoading.set(false);
      },
      error: () => {
        if (token !== this.variantsRequest) return;
        this.error.set('No fue posible cargar las tallas y colores de esta prenda.');
        this.variantsLoading.set(false);
      },
    });
  }

  quote(): CashQuote | null {
    const product = this.products().find(p => p.id === this.form.controls.producto_id.value);
    if (!product) return null;
    return quoteCashSale(product.precio, this.form.controls.cantidad.value, this.form.controls.efectivo.value);
  }

  preview(): void {
    this.error.set(null);
    this.draft.set(null);
    const company = this.companies.active();
    const values = this.form.getRawValue();
    const product = this.products().find(p => p.id === values.producto_id);
    const variant = this.variants().find(v => v.id === values.variante_id && v.producto_id === values.producto_id);
    const branch = this.branches().find(b => b.id === values.sucursal_id);
    const quote = this.quote();
    if (!company || !['CAJERO', 'ENCARGADO_SUCURSAL'].includes(company.rol) || this.form.invalid
      || !branch || !product || !variant || !quote) {
      this.form.markAllAsTouched();
      this.error.set('Verifica sucursal, prenda, variante, cantidad y efectivo. El importe debe cubrir el total.');
      return;
    }
    this.draft.set({
      id: crypto.randomUUID(),
      empresa_id: company.id,
      sucursal_id: branch.id,
      producto_id: product.id,
      variante_id: variant.id,
      cantidad: quote.quantity,
      precio_unitario: formatCents(quote.unitCents),
      total: formatCents(quote.totalCents),
      efectivo_propuesto: formatCents(quote.receivedCents),
      cambio: formatCents(quote.changeCents),
      creado_en: new Date().toISOString(),
      estado: 'BORRADOR_SIN_COBRO',
    });
  }

  invalidate(): void { this.draft.set(null); }
}
