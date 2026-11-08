import { TestBed } from '@angular/core/testing';
import { of, Subject } from 'rxjs';
import { CompanyService } from '../../organizacion_empresarial/empresa/company.service';
import { InventoryApiService } from '../../inventario/inventory-api.service';
import { ReconciliationApi, type SyncConflictDetail } from './reconciliation-api.service';
import { ReconciliationPage } from './reconciliation-page';

const sample: SyncConflictDetail = {
  id: 'fba72911-c1d5-5ac4-95ad-1969d2dda661',
  operacion_id: 'ce290315-b0e4-5023-8ab3-876f169e686a',
  tipo: 'RESERVA',
  estado: 'CONFLICTO',
  motivo: 'DEMO CU13 (PRUEBA SIN COBRO): stock insuficiente para la reserva.',
  sucursal_id: 2,
  creada_en: '2026-11-08T10:30:00Z',
  decision: null,
  observacion: null,
  responsable_id: null,
  resuelta_en: null,
  datos_originales: {
    id: 'ce290315-b0e4-5023-8ab3-876f169e686a',
    origen: 'WEB_OFFLINE',
    cliente_id: 1,
    sucursal_id: 2,
    lineas: [{ variante_id: 3, cantidad: 1 }],
  },
};

describe('CU13 · revisión y conciliación de conflictos', () => {
  async function setup() {
    const api = {
      list: vi.fn(() => of([sample])),
      detail: vi.fn(() => of(sample)),
      resolve: vi.fn(() => of({
        ...sample, estado: 'RESUELTO' as const,
        decision: 'ACUERDO_DOCUMENTADO',
        observacion: 'PRUEBA-CU13-001: Solicitud ficticia sin pago real.',
        responsable_id: 7,
        resuelta_en: '2026-11-08T10:38:00Z',
      })),
    };
    await TestBed.configureTestingModule({
      imports: [ReconciliationPage],
      providers: [
        { provide: ReconciliationApi, useValue: api },
        { provide: CompanyService, useValue: {
          active: () => ({ id: 1, nombre: 'Moda Andina Demo', rol: 'ENCARGADO_SUCURSAL' }),
          changes$: new Subject<void>(),
        } },
        { provide: InventoryApiService, useValue: {
          branches: () => of([{ id: 2, empresa_id: 1,
            nombre: 'Andina Centro', codigo: 'CENTRO', activo: true }]),
        } },
      ],
    }).compileComponents();
    const fixture = TestBed.createComponent(ReconciliationPage);
    fixture.detectChanges();
    return { fixture, page: fixture.componentInstance,
      root: fixture.nativeElement as HTMLElement, api };
  }

  it('muestra los datos preservados al pulsar Revisar, sin resolver el conflicto', async () => {
    const { fixture, root, api } = await setup();
    const button = [...root.querySelectorAll<HTMLButtonElement>('button')]
      .find(item => item.textContent?.trim() === 'Revisar');
    expect(button).toBeDefined();
    button!.click();
    fixture.detectChanges();
    expect(api.detail).toHaveBeenCalledExactlyOnceWith(sample.id);
    expect(root.textContent).toContain('Datos originales capturados sin conexión');
    expect(root.textContent).toContain('Andina Centro');
    expect(root.textContent).toContain('WEB_OFFLINE');
    expect(root.textContent).toContain('Variante #3');
    expect(root.textContent).toContain('1 unidad');
    expect(api.resolve).not.toHaveBeenCalled();
  });

  it('exige referencia y observaciones antes de registrar la resolución', async () => {
    const { fixture, root, page, api } = await setup();
    const review = [...root.querySelectorAll<HTMLButtonElement>('button')]
      .find(item => item.textContent?.trim() === 'Revisar')!;
    review.click();
    fixture.detectChanges();
    expect(page.resolution.invalid).toBe(true);
    const submit = [...root.querySelectorAll<HTMLButtonElement>('button')]
      .find(item => item.textContent?.includes('Registrar resolución trazable'))!;
    expect(submit.disabled).toBe(true);

    page.resolution.patchValue({
      decision: 'ACUERDO_DOCUMENTADO',
      referencia_constancia: 'PRUEBA-CU13-001',
      observacion: 'Solicitud ficticia sin pago ni entrega de prendas.',
    });
    fixture.detectChanges();
    expect(submit.disabled).toBe(false);
    submit.click();
    fixture.detectChanges();
    expect(api.resolve).toHaveBeenCalledExactlyOnceWith(sample.id, {
      decision: 'ACUERDO_DOCUMENTADO',
      referencia_constancia: 'PRUEBA-CU13-001',
      observacion: 'Solicitud ficticia sin pago ni entrega de prendas.',
    });
    expect(page.selected()?.estado).toBe('RESUELTO');
    expect(root.textContent).toContain('Responsable #7');
    expect(root.textContent).toContain('PRUEBA-CU13-001');
  });

  it('muestra el efectivo original de una venta sin presentar una devolución realizada', async () => {
    const { page } = await setup();
    const sale: SyncConflictDetail = {
      ...sample, tipo: 'VENTA_CONTADO',
      datos_originales: {
        origen: 'WEB_OFFLINE', efectivo: '100.00',
        efectivo_cobrado: true, entrega_local: false,
        lineas: [{ variante_id: 1, cantidad: 1, precio_unitario: '80.10' }],
      },
    };
    expect(page.originalText(sale, 'efectivo')).toBe('100.00');
    expect(page.originalFlag(sale, 'efectivo_cobrado')).toBe('Sí');
    expect(page.originalFlag(sale, 'entrega_local')).toBe('No');
    expect(page.originalLines(sale)).toEqual([
      { variante_id: 1, cantidad: 1, precio_unitario: '80.10' },
    ]);
  });
});
