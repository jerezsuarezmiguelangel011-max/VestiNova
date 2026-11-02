import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { ReservationDraftPage } from './reservation-draft';

const PRODUCT = {
  id: 7, nombre: 'Camisa de lino', slug: 'camisa-de-lino',
  descripcion: 'Lino natural.', precio: '149.90', moneda: 'BOB',
  imagen_url: null, activo: true,
  creado_en: '2026-10-25T12:00:00Z', actualizado_en: '2026-10-25T12:00:00Z',
};

const AVAILABILITY = {
  producto_id: 7,
  alcance: 'STOCK_FISICO_REFERENCIAL',
  consultado_en: '2026-11-02T00:00:00Z',
  items: [{
    sucursal_id: 3, sucursal: 'Central', variante_id: 9,
    talla: 'M', color: 'VERDE',
    hay_existencias_fisicas: true, saldo_registrado: true,
  }],
};

describe('CU11 - borrador de reserva no confirmado', () => {
  let http: HttpTestingController;

  async function setup(slug: string | null = PRODUCT.slug) {
    await TestBed.configureTestingModule({
      imports: [ReservationDraftPage],
      providers: [
        provideHttpClient(), provideHttpClientTesting(), provideRouter([]),
        { provide: ActivatedRoute, useValue: { queryParamMap: of(convertToParamMap(slug ? { slug } : {})) } },
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(ReservationDraftPage);
    fixture.detectChanges();
    return { fixture, page: fixture.componentInstance, root: fixture.nativeElement as HTMLElement };
  }

  afterEach(() => {
    http?.verify();
    sessionStorage.removeItem('vestinova_reserva_borrador_v1');
  });

  it('guarda solo un borrador en la pestaña y no registra reservas ni modifica stock', async () => {
    const { fixture, page, root } = await setup();
    const detail = http.expectOne('/api/catalogo/productos/camisa-de-lino');
    const availability = http.expectOne('/api/catalogo/productos/camisa-de-lino/disponibilidad');
    expect(detail.request.method).toBe('GET');
    expect(availability.request.method).toBe('GET');
    detail.flush(PRODUCT);
    availability.flush(AVAILABILITY);
    fixture.detectChanges();
    expect(page.loading()).toBe(false);
    expect(root.textContent).toContain('no confirma ni separa unidades');
    page.form.setValue({ key: '3:9', cantidad: 2 });
    page.saveDraft();
    fixture.detectChanges();
    expect(page.draft()?.estado).toBe('BORRADOR_LOCAL');
    expect(page.draft()?.cantidad).toBe(2);
    expect(page.draft()?.sucursal_id).toBe(3);
    expect(JSON.parse(sessionStorage.getItem('vestinova_reserva_borrador_v1') ?? '{}').estado).toBe('BORRADOR_LOCAL');
    expect(root.textContent).toContain('No confirmado');
    http.expectNone(request => request.method !== 'GET');
    page.clearDraft();
    expect(page.draft()).toBeNull();
    expect(sessionStorage.getItem('vestinova_reserva_borrador_v1')).toBeNull();
  });

  it('no inventa una reserva cuando la prenda carece de variantes con existencias', async () => {
    const { fixture, page, root } = await setup();
    http.expectOne('/api/catalogo/productos/camisa-de-lino').flush(PRODUCT);
    http.expectOne('/api/catalogo/productos/camisa-de-lino/disponibilidad').flush({
      ...AVAILABILITY, items: [{ ...AVAILABILITY.items[0], hay_existencias_fisicas: false }],
    });
    fixture.detectChanges();
    expect(root.textContent).toContain('no hay variantes con existencias físicas');
    page.saveDraft();
    expect(page.draft()).toBeNull();
    http.expectNone(request => request.method === 'POST');
  });
});
