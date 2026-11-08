import { TestBed } from '@angular/core/testing';
import { Subject } from 'rxjs';
import { AuthService } from '../../autenticacion_usuarios/autenticacion/auth.service';
import { CompanyService } from '../../organizacion_empresarial/empresa/company.service';
import { InventoryApiService } from '../../inventario/inventory-api.service';
import { CashSaleApi } from './cash-sale-api.service';
import { CashSaleOfflineStore } from './cash-sale-offline-store.service';
import { CashSaleSyncService } from './cash-sale-sync.service';
import { CashSalePage } from './cash-sale.page';

describe('CU15 · ingreso de efectivo en caja', () => {
  async function setup() {
    await TestBed.configureTestingModule({
      imports: [CashSalePage],
      providers: [
        { provide: CompanyService, useValue: {
          active: () => ({ id: 1, nombre: 'Moda Andina Demo', rol: 'CAJERO' }),
          changes$: new Subject<void>(),
        } },
        { provide: AuthService, useValue: { user: () => null } },
        { provide: CashSaleApi, useValue: {} },
        { provide: CashSaleOfflineStore, useValue: {} },
        { provide: CashSaleSyncService, useValue: {
          processing: () => false, message: () => null,
        } },
        { provide: InventoryApiService, useValue: {} },
      ],
    }).compileComponents();
    const fixture = TestBed.createComponent(CashSalePage);
    const page = fixture.componentInstance;
    page.snapshot.set({
      empresa_id: 1, sucursal_id: 2, descargado_en: '2026-11-08T08:30:00Z',
      items: [{ variante_id: 1, producto_id: 1, nombre: 'Polera clásica',
        talla: 'M', color: 'Blanco', precio_unitario: '80.10' }],
    });
    page.lines.set([{ variante_id: 1, cantidad: 1, precio_unitario: '80.10',
      nombre: 'Polera clásica', talla: 'M', color: 'Blanco' }]);
    fixture.detectChanges();
    return { fixture, page, root: fixture.nativeElement as HTMLElement };
  }

  it('100 muestra Bs 19.90 al instante y completa 100.00 al salir del campo', async () => {
    const { fixture, page, root } = await setup();
    const cash = root.querySelector<HTMLInputElement>('#cash-cash')!;
    expect(cash).not.toBeNull();
    cash.value = '100';
    cash.dispatchEvent(new Event('input', { bubbles: true }));
    fixture.detectChanges();
    expect(page.change()).toBe('19.90');
    expect(root.querySelector('.cash-change')?.textContent).toContain('Bs 19.90');

    cash.dispatchEvent(new Event('blur', { bubbles: true }));
    fixture.detectChanges();
    expect(cash.value).toBe('100.00');
    expect(page.form.controls.efectivo.value).toBe('100.00');
  });

  it('respeta una sola cifra decimal y rechaza fracciones de centavo', async () => {
    const { page } = await setup();
    page.form.controls.efectivo.setValue('100,5');
    expect(page.change()).toBe('20.40');
    page.normalizeCash();
    expect(page.form.controls.efectivo.value).toBe('100.50');

    page.form.controls.efectivo.setValue('100.999');
    expect(page.change()).toBeNull();
    page.normalizeCash();
    expect(page.form.controls.efectivo.value).toBe('100.999');
  });
});
