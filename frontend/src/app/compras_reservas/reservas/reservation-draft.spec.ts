import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { IDBFactory as FakeIDBFactory } from 'fake-indexeddb';
import { of } from 'rxjs';
import { IDB_FACTORY } from '../../catalogo_publico/catalogo/catalog-offline-store.service';
import { CatalogShopService } from '../../catalogo_publico/catalogo/catalog-shop.service';
import { ReservationOfflineStore } from './reservation-offline-store.service';
import { CustomerAuthService } from '../clientes/customer-auth.service';
import { ReservationDraftPage } from './reservation-draft';

const SHOP = 'demo-moda-andina';
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
    hay_existencias_fisicas: true, hay_disponibilidad: true, saldo_registrado: true,
  }],
};

describe('CU10 - solicitudes de reserva persistentes en IndexedDB', () => {
  let http: HttpTestingController;

  async function setup(slug: string | null = PRODUCT.slug) {
    await TestBed.configureTestingModule({
      imports: [ReservationDraftPage],
      providers: [
        provideHttpClient(), provideHttpClientTesting(), provideRouter([]),
        { provide: IDB_FACTORY, useValue: new FakeIDBFactory() },
        { provide: ActivatedRoute, useValue: { queryParamMap: of(convertToParamMap(slug ? { slug } : {})) } },
      ],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
    const shop = TestBed.inject(CatalogShopService);
    shop.setTienda(SHOP);
    const offline = TestBed.inject(ReservationOfflineStore);
    const fixture = TestBed.createComponent(ReservationDraftPage);
    fixture.detectChanges();
    return { fixture, page: fixture.componentInstance, root: fixture.nativeElement as HTMLElement, offline };
  }

  function flushInitial(hasAvailability: boolean, withSecondVariant = false): void {
    const product = http.expectOne(req =>
      req.method === 'GET' &&
      req.url === '/api/catalogo/productos/camisa-de-lino' &&
      req.params.get('tienda') === SHOP,
    );
    const availability = http.expectOne(req =>
      req.method === 'GET' &&
      req.url === '/api/catalogo/productos/camisa-de-lino/disponibilidad' &&
      req.params.get('tienda') === SHOP,
    );
    const policy = http.expectOne(req =>
      req.method === 'GET' &&
      req.url === `/api/tiendas/${SHOP}/reservas/politica`,
    );
    product.flush(PRODUCT);
    availability.flush({
      ...AVAILABILITY,
      items: [{
        ...AVAILABILITY.items[0],
        hay_disponibilidad: hasAvailability,
        hay_existencias_fisicas: hasAvailability,
      }, ...(withSecondVariant ? [{ ...AVAILABILITY.items[0],
        variante_id: 10, talla: 'L', color: 'AZUL',
        hay_disponibilidad: true, hay_existencias_fisicas: true }] : [])],
    });
    policy.flush({ vigencia_horas: 24, requiere_conexion: true });
  }

  beforeEach(() => sessionStorage.clear());
  afterEach(() => { http?.verify(); sessionStorage.clear(); });

  it('guarda un borrador en IndexedDB sin crear reserva central ni comprometer stock', async () => {
    const { fixture, page, root, offline } = await setup();
    flushInitial(true);
    fixture.detectChanges();
    expect(page.loading()).toBe(false);
    expect(page.policyHours()).toBe(24);
    expect(root.textContent).toContain('Todavía no separa prendas.');
    expect(root.textContent).toContain('2 · Confirmada');
    expect(root.textContent).toContain('3 · Conflicto');

    page.form.setValue({ key: '3:9', cantidad: 2 });
    await page.saveDraft();
    fixture.detectChanges();

    expect(page.draft()?.estado).toBe('BORRADOR_LOCAL');
    expect(page.draft()?.cantidad).toBe(2);
    expect(page.draft()?.sucursal_id).toBe(3);
    const stored = await offline.list(SHOP, null);
    expect(stored).toHaveLength(1);
    expect(stored[0]).toMatchObject({
      tienda: SHOP, cliente_id: null, estado: 'BORRADOR_LOCAL',
      draft: { cantidad: 2, variante_id: 9, sucursal_id: 3 },
    });
    expect(root.textContent).toContain('Borrador de reserva');
    expect(root.textContent).toContain('2');
    const loginLink = root.querySelector('.reservation-draft-actions a') as HTMLAnchorElement;
    expect(loginLink?.getAttribute('href')).toContain('/tienda/demo-moda-andina/acceso');
    expect(loginLink?.getAttribute('href')).toContain('continuar=reserva');
    expect(loginLink?.getAttribute('href')).toContain('producto=camisa-de-lino');
    expect(root.textContent).not.toContain('Confirmar y enviar reserva');
    http.expectNone(req => req.method !== 'GET');

    await page.clearDraft();
    fixture.detectChanges();
    expect(page.draft()).toBeNull();
    expect(await offline.list(SHOP, null)).toHaveLength(0);
  });

  it('guarda varias variantes de la misma sucursal y rechaza duplicados', async () => {
    const { page, offline } = await setup();
    flushInitial(true, true);
    page.form.setValue({ key: '3:9', cantidad: 2 });
    page.addLine();
    page.form.setValue({ key: '3:10', cantidad: 1 });
    page.addLine();
    expect(page.selectedLines()).toHaveLength(2);
    page.form.setValue({ key: '3:10', cantidad: 3 });
    page.addLine();
    expect(page.selectedLines()).toHaveLength(2);
    expect(page.error()).toContain('ya está añadida');
    await page.saveDraft();
    const rows = await offline.list(SHOP, null);
    expect(rows).toHaveLength(1);
    expect(rows[0].draft.lineas).toMatchObject([
      { variante_id: 9, cantidad: 2, sucursal_id: 3 },
      { variante_id: 10, cantidad: 1, sucursal_id: 3 },
    ]);
    http.expectNone(req => req.method === 'POST');
  });

  it('no crea una solicitud cuando ninguna variante tiene disponibilidad verificable', async () => {
    const { fixture, page, root, offline } = await setup();
    flushInitial(false);
    fixture.detectChanges();

    expect(page.selectable()).toHaveLength(0);
    expect(root.textContent).toContain('no contiene variantes disponibles');
    await page.saveDraft();

    expect(page.draft()).toBeNull();
    expect(await offline.list(SHOP, null)).toHaveLength(0);
    http.expectNone(req => req.method === 'POST');
  });
  it('tras iniciar sesión conserva el borrador y exige un clic para confirmarlo', async () => {
    const { fixture, page, root } = await setup();
    flushInitial(true);
    page.form.setValue({ key: '3:9', cantidad: 2 });
    await page.saveDraft();
    const originalId = page.draft()?.id;
    expect(originalId).toBeTruthy();

    const auth = TestBed.inject(CustomerAuthService);
    auth.login(SHOP, { correo: 'cliente@prueba.test', password: 'clave-demo' }).subscribe();
    const login = http.expectOne(req => req.method === 'POST' &&
      req.url === `/api/tiendas/${SHOP}/cuenta/login`);
    login.flush({
      access_token: 'token-de-prueba', token_type: 'bearer',
      expires_at: '2026-11-09T12:00:00Z',
      cliente: { id: 42, nombre: 'Cliente de prueba', correo: 'cliente@prueba.test',
        rol: 'CLIENTE', empresa: { slug: SHOP, nombre: 'Moda Andina' } },
    });
    await page.refreshOffline();
    fixture.detectChanges();

    expect(page.draft()?.id).toBe(originalId);
    expect(root.textContent).toContain('Confirmar y enviar reserva');
    expect(root.textContent).toContain('No se han separado prendas');
    http.expectNone(req => req.method === 'POST' && req.url.endsWith('/reservas'));
  });

  it('al regresar muestra el borrador de la prenda exacta, no el de otra', async () => {
    const { page, offline } = await setup();
    flushInitial(true);
    page.form.setValue({ key: '3:9', cantidad: 2 });
    await page.saveDraft();
    const original = page.draft();
    expect(original).not.toBeNull();
    await offline.saveDraft({
      ...original!,
      id: 'd661b905-668c-4ea7-8c43-1ac314672efe',
      producto_slug: 'otra-prenda',
      producto_nombre: 'Otra prenda',
      creado_en: '2099-12-31T23:59:59Z',
    }, null);
    page.draft.set(null);
    await page.refreshOffline();
    expect(page.draft()?.id).toBe(original?.id);
    expect(page.draft()?.producto_slug).toBe('camisa-de-lino');
  });

});
