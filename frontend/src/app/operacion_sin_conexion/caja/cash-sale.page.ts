import { DatePipe, isPlatformBrowser } from '@angular/common';
import { Component, DestroyRef, OnInit, PLATFORM_ID, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { AuthService } from '../../autenticacion_usuarios/autenticacion/auth.service';
import { CompanyService } from '../../organizacion_empresarial/empresa/company.service';
import { InventoryApiService, type InventoryBranch } from '../../inventario/inventory-api.service';
import { CashSaleApi, type CashLine, type CashSnapshot, type CashVariant } from './cash-sale-api.service';
import { CashSaleOfflineStore, type CashLocalSale } from './cash-sale-offline-store.service';
import { CashSaleSyncService } from './cash-sale-sync.service';
import { formatCents, moneyToCents, normalizeCashReceived } from './cash-sale.domain';

interface SelectedCashLine extends CashLine {
  nombre: string; talla: string; color: string;
}

@Component({
  selector: 'vn-cash-sale-page',
  imports: [ReactiveFormsModule, DatePipe],
  templateUrl: './cash-sale.page.html',
  styleUrl: './cash-sale.page.css',
})
export class CashSalePage implements OnInit {
  readonly companies = inject(CompanyService);
  readonly auth = inject(AuthService);
  readonly sync = inject(CashSaleSyncService);
  private readonly api = inject(CashSaleApi);
  private readonly local = inject(CashSaleOfflineStore);
  private readonly inventory = inject(InventoryApiService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly browser = isPlatformBrowser(inject(PLATFORM_ID));
  readonly branches = signal<InventoryBranch[]>([]);
  readonly snapshot = signal<CashSnapshot | null>(null);
  readonly localCopy = signal(false);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);
  readonly notice = signal<string | null>(null);
  readonly lines = signal<SelectedCashLine[]>([]);
  readonly operations = signal<CashLocalSale[]>([]);
  readonly chosenBranch = signal<number | null>(null);
  private revision = 0;

  readonly form = new FormGroup({
    variante_id: new FormControl<number | null>(null, Validators.required),
    cantidad: new FormControl(1, { nonNullable: true, validators: [Validators.required, Validators.min(1), Validators.max(100)] }),
    cliente_id: new FormControl<number | null>(null),
    efectivo: new FormControl('0.00', { nonNullable: true, validators: [Validators.required] }),
    cobrado: new FormControl(false, { nonNullable: true, validators: Validators.requiredTrue }),
    entregado_local: new FormControl(false, { nonNullable: true }),
  });

  constructor() {
    this.companies.changes$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      ++this.revision;
      this.branches.set([]); this.snapshot.set(null); this.lines.set([]);
      this.chosenBranch.set(null); this.operations.set([]);
      this.localCopy.set(false); this.error.set(null); this.notice.set(null);
      this.form.reset({ variante_id: null, cantidad: 1, cliente_id: null,
        efectivo: '0.00', cobrado: false, entregado_local: false });
      void this.load();
    });
    if (this.browser) {
      const connected = () => { void this.synchronize(); };
      window.addEventListener('online', connected);
      this.destroyRef.onDestroy(() => window.removeEventListener('online', connected));
    }
  }
  ngOnInit(): void { void this.load(); }

  async load(): Promise<void> {
    const company = this.companies.active();
    const user = this.auth.user();
    if (!company || !user) return;
    const revision = this.revision;
    this.loading.set(true);
    try {
      const cached = await this.local.catalogs(company.id, user.id);
      if (revision !== this.revision) return;
      this.branches.set(cached.map(row => ({ id: row.sucursal_id, empresa_id: company.id,
        codigo: String(row.sucursal_id), nombre: 'Sucursal #' + row.sucursal_id,
        activo: true })));
      const fresh = await firstValueFrom(this.inventory.branches());
      if (revision === this.revision) this.branches.set(fresh.filter(row => row.activo));
    } catch {
      if (revision === this.revision) this.notice.set('Modo local: solo sucursales preparadas previamente.');
    } finally {
      if (revision === this.revision) {
        this.loading.set(false);
        await this.refreshOperations();
      }
    }
  }

  async chooseBranch(value: string): Promise<void> {
    const branch = Number(value);
    const company = this.companies.active();
    const user = this.auth.user();
    this.chosenBranch.set(null);
    this.snapshot.set(null);
    this.lines.set([]);
    this.form.controls.variante_id.setValue(null);
    this.error.set(null);
    if (!company || !user || !Number.isSafeInteger(branch) || branch < 1 ||
        !this.branches().some(row => row.id === branch)) return;
    this.chosenBranch.set(branch);
    this.loading.set(true);
    const revision = this.revision;
    try {
      const snapshot = await firstValueFrom(this.api.catalog(branch));
      if (revision !== this.revision || this.chosenBranch() !== branch) return;
      await this.local.saveCatalog(snapshot, user.id);
      this.snapshot.set(snapshot);
      this.localCopy.set(false);
      this.notice.set('Catálogo de caja actualizado y preparado en IndexedDB.');
    } catch {
      try {
        const snapshot = await this.local.catalog(company.id, user.id, branch);
        if (revision !== this.revision || this.chosenBranch() !== branch) return;
        if (snapshot) {
          this.snapshot.set(snapshot);
          this.localCopy.set(true);
          this.notice.set('Se utiliza copia local; precios y stock se revalidarán al sincronizar.');
        } else this.error.set('No hay datos de caja preparados para esta sucursal. Conéctate y descarga el catálogo.');
      } catch {
        if (revision === this.revision) this.error.set('No se pudo leer el catálogo local.');
      }
    } finally {
      if (revision === this.revision) this.loading.set(false);
    }
  }

  selectedVariant(): CashVariant | null {
    return this.snapshot()?.items.find(item => item.variante_id === this.form.controls.variante_id.value) ?? null;
  }

  addLine(): void {
    const selected = this.selectedVariant();
    const quantity = this.form.controls.cantidad.value;
    if (!selected || !Number.isSafeInteger(quantity) || quantity < 1 || quantity > 100) {
      this.error.set('Selecciona una variante y una cantidad válida.');
      return;
    }
    if (this.lines().some(item => item.variante_id === selected.variante_id) || this.lines().length >= 30) {
      this.error.set('No se puede duplicar una variante ni superar 30 líneas.');
      return;
    }
    this.lines.update(items => [...items, { variante_id: selected.variante_id,
      cantidad: quantity, precio_unitario: selected.precio_unitario,
      nombre: selected.nombre, talla: selected.talla, color: selected.color }]);
    this.form.patchValue({ variante_id: null, cantidad: 1 });
    this.error.set(null);
  }

  removeLine(id: number): void { if (!this.saving()) this.lines.update(rows => rows.filter(row => row.variante_id !== id)); }
  totalCents(): number {
    return this.lines().reduce((sum, row) =>
      sum + (moneyToCents(row.precio_unitario) ?? 0) * row.cantidad, 0);
  }
  total(): string { return formatCents(this.totalCents()); }

  /** Solo formatea al salir del campo, para no interrumpir la escritura. */
  normalizeCash(): void {
    const normalized = normalizeCashReceived(this.form.controls.efectivo.value);
    if (normalized !== null && normalized !== this.form.controls.efectivo.value) {
      this.form.controls.efectivo.setValue(normalized);
    }
  }

  change(): string | null {
    const normalized = normalizeCashReceived(this.form.controls.efectivo.value);
    const received = normalized === null ? null : moneyToCents(normalized);
    return received !== null && received >= this.totalCents()
      ? formatCents(received - this.totalCents()) : null;
  }

  async register(): Promise<void> {
    if (this.saving()) return;
    // Nunca enviar efectivo sin centavos a IndexedDB o al backend:
    // el UUID y la huella se basan en el importe canónico.
    this.normalizeCash();
    const company = this.companies.active();
    const user = this.auth.user();
    const branch = this.chosenBranch();
    const received = moneyToCents(this.form.controls.efectivo.value);
    const cash = this.form.controls.cobrado.value;
    const client = this.form.controls.cliente_id.value;
    if (!this.browser || !company || !user || !branch || !this.snapshot() ||
        !this.lines().length || !cash || !this.form.controls.cobrado.valid ||
        received === null || received < this.totalCents() ||
        (client !== null && (!Number.isSafeInteger(client) || client < 1))) {
      this.error.set('Revisa sucursal, artículos, efectivo recibido y confirma que el cobro realmente ocurrió.');
      return;
    }
    const revision = this.revision;
    this.saving.set(true); this.error.set(null);
    const now = new Date().toISOString();
    const id = crypto.randomUUID();
    const row: CashLocalSale = {
      id, empresa_id: company.id, usuario_id: user.id, sucursal_id: branch,
      creado_en: now, actualizado_en: now, estado: 'PENDIENTE',
      total: this.total(), cambio: this.change() ?? '0.00',
      motivo: null, incidencia_id: null, resultado: null,
      solicitud: {
        id, sucursal_id: branch, cliente_id: client,
        lineas: this.lines().map(item => ({
          variante_id: item.variante_id, cantidad: item.cantidad, precio_unitario: item.precio_unitario,
        })),
        efectivo: this.form.controls.efectivo.value,
        origen: 'WEB_OFFLINE', creada_local_en: now,
        efectivo_cobrado: true, entrega_local: this.form.controls.entregado_local.value,
      },
    };
    try {
      await this.local.enqueue(row);
      if (revision !== this.revision) return;
      this.lines.set([]);
      this.form.reset({ variante_id: null, cantidad: 1, cliente_id: null,
        efectivo: '0.00', cobrado: false, entregado_local: false });
      this.notice.set('Comprobante PROVISIONAL ' + id + ' guardado. El efectivo consta localmente, no hay venta central confirmada.');
      await this.refreshOperations();
      if (typeof navigator !== 'undefined' && navigator.onLine) await this.synchronize();
    } catch {
      this.error.set('No se pudo guardar el comprobante en IndexedDB; no asumas que existe una venta registrada.');
    } finally {
      this.saving.set(false);
    }
  }

  async refreshOperations(): Promise<void> {
    const company = this.companies.active();
    const user = this.auth.user();
    if (!company || !user) return;
    const revision = this.revision;
    try {
      const rows = await this.local.list(company.id, user.id);
      if (revision === this.revision) this.operations.set(rows);
    } catch {
      if (revision === this.revision) this.error.set('No se pudieron recuperar los comprobantes locales de caja.');
    }
  }

  async synchronize(): Promise<void> {
    await this.sync.process();
    await this.refreshOperations();
    if (this.sync.message()) this.notice.set(this.sync.message());
  }

  async retry(id: string): Promise<void> {
    const company = this.companies.active();
    const user = this.auth.user();
    if (!company || !user) return;
    try {
      await this.local.retry(id, company.id, user.id);
      await this.synchronize();
    } catch { this.error.set('Este registro no permite reintento; revisa su estado.'); }
  }
}
