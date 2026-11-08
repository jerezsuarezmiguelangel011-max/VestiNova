import { TestBed } from '@angular/core/testing';
import { IDBFactory as FakeIDBFactory } from 'fake-indexeddb';
import { IDB_FACTORY } from '../../catalogo_publico/catalogo/catalog-offline-store.service';
import type { ReservationDraft } from './reservation-draft';
import { ReservationOfflineStore } from './reservation-offline-store.service';

const DRAFT: ReservationDraft = {
  id: '5b335189-2506-445d-8284-65b0a07a5c3e',
  tienda: 'demo-moda-andina',
  producto_id: 11, producto_nombre: 'Polera',
  producto_slug: 'polera', sucursal_id: 2, sucursal_nombre: 'Andina Centro',
  variante_id: 8, talla: 'M', color: 'Azul', cantidad: 2,
  creado_en: '2026-11-07T14:00:00.000Z', estado: 'BORRADOR_LOCAL',
};

describe('CU10: cola IndexedDB de reservas', () => {
  let factory: IDBFactory;
  let store: ReservationOfflineStore;
  const configure = () => {
    TestBed.configureTestingModule({ providers: [{ provide: IDB_FACTORY, useValue: factory }] });
    return TestBed.inject(ReservationOfflineStore);
  };
  beforeEach(() => { factory = new FakeIDBFactory(); store = configure(); });

  it('conserva UUID, solicitud y estado al reabrir', async () => {
    await store.saveDraft(DRAFT, 4);
    TestBed.resetTestingModule();
    const reopened = configure();
    const list = await reopened.list(DRAFT.tienda, 4);
    expect(list).toHaveLength(1);
    expect(list[0]).toMatchObject({ id: DRAFT.id, cliente_id: 4, estado: 'PENDIENTE' });
    expect(list[0].draft).toEqual(DRAFT);
  });

  it('no mezcla datos de dos tiendas ni de dos cuentas', async () => {
    await store.saveDraft(DRAFT, 4);
    expect(await store.list('demo-moda-urbana', 4)).toHaveLength(0);
    expect(await store.list(DRAFT.tienda, 15)).toHaveLength(0);
    expect(await store.list(DRAFT.tienda, null)).toHaveLength(0);
  });

  it('reenvía un UUID una sola vez cuando hay dos procesadores', async () => {
    await store.saveDraft(DRAFT, 4);
    const second = TestBed.runInInjectionContext(() => new ReservationOfflineStore());
    const claimed = await Promise.all([
      store.claim(DRAFT.id, DRAFT.tienda, 4),
      second.claim(DRAFT.id, DRAFT.tienda, 4),
    ]);
    expect(claimed.filter(Boolean)).toHaveLength(1);
    expect((await store.list(DRAFT.tienda, 4))[0].estado).toBe('ENVIANDO');
  });

  it('retiene errores y luego confirma con el mismo UUID y comprobante', async () => {
    await store.saveDraft(DRAFT, 4);
    await store.claim(DRAFT.id, DRAFT.tienda, 4);
    await store.finish(DRAFT.id, 'ERROR', 'Sin red.');
    expect((await store.list(DRAFT.tienda, 4))[0].id).toBe(DRAFT.id);
    await store.retry(DRAFT.id, DRAFT.tienda, 4);
    await store.claim(DRAFT.id, DRAFT.tienda, 4);
    await store.finish(DRAFT.id, 'CONFIRMADA', null, {
      id: DRAFT.id, codigo: 'VN-R-123', estado: 'CONFIRMADA',
      cliente_id: 4, sucursal_id: 2,
      lineas: [{ variante_id: 8, cantidad: 2 }],
      creada_en: DRAFT.creado_en, vence_en: '2026-11-08T14:00:00Z',
      actualizada_en: DRAFT.creado_en,
    });
    expect((await store.list(DRAFT.tienda, 4))[0]).toMatchObject({
      id: DRAFT.id, estado: 'CONFIRMADA', resultado: { codigo: 'VN-R-123' },
    });
    await expect(store.retry(DRAFT.id, DRAFT.tienda, 4)).rejects.toThrow();
  });

  it('recupera envíos interrumpidos sin eliminar registros', async () => {
    await store.saveDraft(DRAFT, 4);
    await store.claim(DRAFT.id, DRAFT.tienda, 4);
    await store.recoverSending(DRAFT.tienda, 4);
    const rows = await store.list(DRAFT.tienda, 4);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ id: DRAFT.id, estado: 'PENDIENTE' });
  });

  it('resiste reintento con otro contenido en el mismo UUID', async () => {
    await store.saveDraft(DRAFT, 4);
    await expect(store.saveDraft({ ...DRAFT, cantidad: 5 }, 4)).rejects.toThrow('UUID');
    const rows = await store.list(DRAFT.tienda, 4);
    expect(rows[0].draft.cantidad).toBe(2);
  });

  it('permite borrador sin cuenta, pero solo se envía después de asociarse', async () => {
    await store.saveDraft(DRAFT, null);
    expect(await store.list(DRAFT.tienda, null)).toHaveLength(1);
    expect(await store.claim(DRAFT.id, DRAFT.tienda, 4)).toBeNull();
    await store.assign(DRAFT.id, DRAFT.tienda, 4);
    expect(await store.list(DRAFT.tienda, null)).toHaveLength(0);
    expect(await store.list(DRAFT.tienda, 4)).toHaveLength(1);
    expect((await store.claim(DRAFT.id, DRAFT.tienda, 4))?.estado).toBe('ENVIANDO');
  });

  it('impide borrar una reserva ya enviada o pendiente', async () => {
    await store.saveDraft(DRAFT, 4);
    await expect(store.discardDraft(DRAFT.id, DRAFT.tienda)).rejects.toThrow();
    expect(await store.list(DRAFT.tienda, 4)).toHaveLength(1);
  });
});
