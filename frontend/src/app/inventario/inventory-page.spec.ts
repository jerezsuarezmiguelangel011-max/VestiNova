import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { of, Subject } from 'rxjs';
import { describe, expect, it, vi } from 'vitest';

import { CategoryService } from '../catalogo_abastecimiento/categorias/category.service';
import { CompanyService } from '../organizacion_empresarial/empresa/company.service';
import { InventoryApiService } from './inventory-api.service';
import { InventoryPage } from './inventory-page';

describe('CU07: navegación hacia el kardex', () => {
  it('filtra solo movimientos y conserva las existencias visibles al abrir el historial', async () => {
    const company = {
      active: signal({ id: 1, nombre: 'Moda Andina Demo' }),
      revision: signal(1),
      changes$: new Subject<void>().asObservable(),
      hasPermission: (code: string) => code === 'inventario.consultar',
    };
    const balances = vi.fn(() => of({
      items: [{
        empresa_id: 1, sucursal_id: 2, variante_id: 2,
        cantidad: 4, cantidad_comprometida: 0, cantidad_disponible: 4,
        actualizado_en: '2026-11-03T10:00:00Z',
        producto_nombre: 'Jeans azul', talla: 'M', color: 'Azul',
      }],
      total: 1, limit: 100, offset: 0,
    }));
    const movements = vi.fn((_branch: number, _offset: number, variant: number | null) => of({
      items: variant === null ? [{
        id: '1', empresa_id: 1, sucursal_id: 2, variante_id: 2, usuario_id: 1,
        tipo: 'ENTRADA', clase: 'MOVIMIENTO', delta: 4, saldo_resultante: 4,
        motivo: 'Carga inicial', creado_en: '2026-11-03T10:00:00Z',
      }] : [],
      total: variant === null ? 1 : 0, limit: 100, offset: 0,
    }));

    TestBed.configureTestingModule({
      imports: [InventoryPage],
      providers: [
        { provide: CompanyService, useValue: company },
        { provide: CategoryService, useValue: { list: () => of([]) } },
        { provide: InventoryApiService, useValue: {
          branches: () => of([{ id: 2, empresa_id: 1, codigo: 'CENTRO', nombre: 'Andina Centro', activo: true }]),
          balances, movements,
        } },
      ],
    });

    const fixture = TestBed.createComponent(InventoryPage);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const button = fixture.nativeElement.querySelector('.inventory-kardex-link') as HTMLButtonElement;
    const history = fixture.nativeElement.querySelector('.inventory-history') as HTMLElement;
    expect(button).not.toBeNull();
    expect(button.tagName).toBe('BUTTON');
    expect(button.type).toBe('button');
    expect(button.hasAttribute('href')).toBe(false);
    expect(button.hasAttribute('routerLink')).toBe(false);
    history.scrollIntoView = vi.fn();
    expect(balances).toHaveBeenCalledTimes(1);
    expect(movements).toHaveBeenCalledWith(2, 0, null);

    button.click();
    fixture.detectChanges();
    expect(history.scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' });
    expect(fixture.componentInstance.selectedHistoryVariant()).toBe(2);
    expect(movements).toHaveBeenCalledWith(2, 0, 2);
    expect(balances).toHaveBeenCalledTimes(1);
    expect(fixture.nativeElement.textContent).toContain('Kardex de la variante 2');
    expect(fixture.nativeElement.textContent).toContain('Esta variante todavía no tiene movimientos');

    const allHistoryButton = [...fixture.nativeElement.querySelectorAll('button')]
      .find((element: HTMLButtonElement) => element.textContent?.trim() === 'Ver todo el kardex') as HTMLButtonElement | undefined;
    expect(allHistoryButton).toBeDefined();
    allHistoryButton?.click();
    fixture.detectChanges();
    expect(fixture.componentInstance.selectedHistoryVariant()).toBeNull();
    expect(movements).toHaveBeenCalledWith(2, 0, null);
    expect(fixture.nativeElement.textContent).toContain('Carga inicial');
  });
});
