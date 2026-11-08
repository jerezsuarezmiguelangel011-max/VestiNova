import { TestBed } from '@angular/core/testing';
import { Subject, of } from 'rxjs';
import { CompanyService } from '../../organizacion_empresarial/empresa/company.service';
import { InventoryApiService } from '../../inventario/inventory-api.service';
import {
  ReservationAttentionApi, type AttentionResult,
} from './reservation-attention-api.service';
import { ReservationAttentionPage } from './reservation-attention-page';

const ACTIVE: AttentionResult = {
  id: '4ea17e7a-4522-4dbd-8555-40c2ec3ed65d',
  codigo: 'VN-R-9ED1FD2F2D6E',
  estado: 'CONFIRMADA',
  cliente_id: 1,
  cliente_nombre: 'Cliente Demo Andina',
  sucursal_id: 2,
  sucursal_nombre: 'Andina Centro',
  creada_en: '2026-11-08T08:00:00Z',
  vence_en: '2026-11-09T08:00:00Z',
  actualizada_en: '2026-11-08T08:00:00Z',
  lineas: [{ variante_id: 1, cantidad: 1, producto_nombre: 'Polera clásica',
    talla: 'M', color: 'Blanco' }],
  eventos: [{ estado: 'CONFIRMADA', actor: 'CLIENTE:1', en: '2026-11-08T08:00:00Z' }],
};
const CANCELLED: AttentionResult = {
  ...ACTIVE, id: '354e1a7c-f23b-44d9-a9f1-c9d04c3349a3',
  codigo: 'VN-R-CANCELADA', estado: 'CANCELADA',
  eventos: [{ estado: 'CANCELADA', actor: 'CLIENTE:1', en: '2026-11-08T08:30:00Z' }],
};

describe('CU14 · atención de reservas desde el panel del Cajero', () => {
  async function setup() {
    const scopeChanges = new Subject<number>();
    const requests = {
      list: vi.fn((filters: { estado?: string }) => of(
        filters.estado === 'TODAS' ? [ACTIVE, CANCELLED] :
        filters.estado === 'CANCELADA' ? [CANCELLED] : [ACTIVE])),
      detail: vi.fn(() => of(ACTIVE)),
      deliver: vi.fn(() => of({ ...ACTIVE, estado: 'ATENDIDA' as const })),
      cancel: vi.fn(() => of({ ...ACTIVE, estado: 'CANCELADA' as const })),
    };
    await TestBed.configureTestingModule({
      imports: [ReservationAttentionPage],
      providers: [
        { provide: ReservationAttentionApi, useValue: requests },
        { provide: InventoryApiService, useValue: {
          branches: () => of([{
            id: 2, empresa_id: 1, nombre: 'Andina Centro',
            codigo: 'CENTRO', activo: true,
          }]),
        } },
        { provide: CompanyService, useValue: {
          active: () => ({ id: 1, nombre: 'Moda Andina Demo',
            slug: 'demo-moda-andina', rol: 'CAJERO' }),
          changes$: scopeChanges.asObservable(),
        } },
      ],
    }).compileComponents();
    const fixture = TestBed.createComponent(ReservationAttentionPage);
    fixture.detectChanges();
    return {
      fixture, component: fixture.componentInstance,
      root: fixture.nativeElement as HTMLElement, requests, scopeChanges,
    };
  }

  it('por defecto presenta solo reservas confirmadas con datos legibles', async () => {
    const { root, requests } = await setup();
    expect(requests.list).toHaveBeenCalledWith(expect.objectContaining({
      estado: 'CONFIRMADA',
    }));
    expect(root.textContent).toContain('Pendientes de retiro');
    expect(root.textContent).toContain('Cliente Demo Andina');
    expect(root.textContent).toContain('Polera clásica');
    expect(root.textContent).toContain('Andina Centro');
    expect(root.textContent).not.toContain('VN-R-CANCELADA');
  });

  it('al pulsar Atender reserva abre el detalle justo debajo, sin entregar nada', async () => {
    const { root, requests, fixture } = await setup();
    const action = root.querySelector('.attention-item__action') as HTMLButtonElement;
    expect(action?.textContent).toContain('Atender reserva');
    action.click();
    fixture.detectChanges();
    expect(requests.detail).toHaveBeenCalledExactlyOnceWith(ACTIVE.id);
    const details = root.querySelector('.attention-detail') as HTMLElement;
    expect(details).not.toBeNull();
    expect(details.textContent).toContain('Confirmar retiro');
    expect(details.textContent).toContain('Polera clásica');
    expect(details.textContent).toContain('Entregar prendas y registrar retiro');
    expect(action.getAttribute('aria-expanded')).toBe('true');
    expect(requests.deliver).not.toHaveBeenCalled();

    action.click();
    fixture.detectChanges();
    expect(root.querySelector('.attention-detail')).toBeNull();
    expect(action.getAttribute('aria-expanded')).toBe('false');
  });

  it('no confunde historial de cancelaciones con retiros disponibles', async () => {
    const { fixture, root, component, requests } = await setup();
    component.search.controls.estado.setValue('TODAS');
    component.load();
    fixture.detectChanges();
    expect(requests.list).toHaveBeenLastCalledWith(expect.objectContaining({ estado: 'TODAS' }));
    const cards = [...root.querySelectorAll('.attention-item')];
    expect(cards).toHaveLength(2);
    expect(cards[1].textContent).toContain('Cancelada');
    expect(cards[1].querySelector('button')?.textContent).toContain('Ver historial');
  });

  it('la entrega necesita verificación y conserva el detalle visible al terminar', async () => {
    const { component, fixture, root, requests } = await setup();
    (root.querySelector('.attention-item__action') as HTMLButtonElement).click();
    fixture.detectChanges();
    component.deliver(ACTIVE);
    expect(requests.deliver).not.toHaveBeenCalled();

    component.delivery.setValue({
      verified: true, comprobacion: 'Cliente presentó código y documento',
    });
    component.deliver(ACTIVE);
    expect(requests.deliver).toHaveBeenCalledWith(
      ACTIVE.id, 'Cliente presentó código y documento');
    expect(component.search.controls.estado.value).toBe('TODAS');
    expect(component.selected()?.estado).toBe('ATENDIDA');
  });
});
