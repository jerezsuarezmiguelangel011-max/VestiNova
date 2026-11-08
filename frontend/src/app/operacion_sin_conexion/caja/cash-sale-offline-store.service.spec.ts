import { TestBed } from '@angular/core/testing';
import { IDBFactory as FakeIDBFactory } from 'fake-indexeddb';
import { IDB_FACTORY } from '../../catalogo_publico/catalogo/catalog-offline-store.service';
import { CashSaleOfflineStore, type CashLocalSale } from './cash-sale-offline-store.service';

const ID = 'd34ef0ef-3fbb-4f6d-8d63-4d0982112121';
const ROW: CashLocalSale = {
  id: ID, empresa_id: 2, usuario_id: 5, sucursal_id: 7,
  creado_en: '2026-11-07T22:00:00.000Z',
  actualizado_en: '2026-11-07T22:00:00.000Z',
  estado: 'PENDIENTE', total: '160.20', cambio: '39.80',
  motivo: null, incidencia_id: null, resultado: null,
  solicitud: {
    id: ID, sucursal_id: 7, cliente_id: null,
    lineas: [{ variante_id: 13, cantidad: 2, precio_unitario: '80.10' }],
    efectivo: '200.00', origen: 'WEB_OFFLINE', creada_local_en: '2026-11-07T22:00:00.000Z',
    efectivo_cobrado: true, entrega_local: false,
  },
};

describe('CU15: persistencia de cobros de caja en IndexedDB', () => {
  let factory: IDBFactory;
  let store: CashSaleOfflineStore;
  const configure = () => {
    TestBed.configureTestingModule({ providers: [{ provide: IDB_FACTORY, useValue: factory }] });
    return TestBed.inject(CashSaleOfflineStore);
  };
  beforeEach(() => { factory = new FakeIDBFactory(); store = configure(); });

  it('conserva evidencia de efectivo, UUID y sucursal al reabrir', async () => {
    await store.enqueue(ROW);
    TestBed.resetTestingModule();
    store = configure();
    const rows = await store.list(2, 5);
    expect(rows).toHaveLength(1);
    expect(rows[0].solicitud.efectivo).toBe('200.00');
    expect(rows[0].id).toBe(ID);
  });

  it('separa cuentas y empresas', async () => {
    await store.enqueue(ROW);
    expect(await store.list(2, 15)).toHaveLength(0);
    expect(await store.list(3, 5)).toHaveLength(0);
    expect(await store.list(2, 5)).toHaveLength(1);
  });

  it('reconstruye envíos interrumpidos y reintenta sin modificar UUID', async () => {
    await store.enqueue(ROW);
    const claimed = await store.claim(ID, 2, 5);
    expect(claimed?.estado).toBe('ENVIANDO');
    await store.recover(2, 5);
    const again = await store.list(2, 5);
    expect(again[0].estado).toBe('PENDIENTE');
    expect(again[0].id).toBe(ID);
    await store.claim(ID, 2, 5);
    await store.finish(ID, 'CONFLICTO', 'Stock insuficiente.', null, 'inc-12');
    expect((await store.list(2, 5))[0]).toMatchObject({
      estado: 'CONFLICTO', incidencia_id: 'inc-12', solicitud: { efectivo: '200.00' },
    });
    await expect(store.retry(ID, 2, 5)).rejects.toThrow();
  });

  it('confirma una sola vez la operación local', async () => {
    await store.enqueue(ROW);
    expect(await store.claim(ID, 2, 5)).not.toBeNull();
    expect(await store.claim(ID, 2, 5)).toBeNull();
    await store.finish(ID, 'CONFIRMADA', 'Servidor confirmó.');
    expect((await store.list(2, 5))[0].estado).toBe('CONFIRMADA');
    expect(await store.claim(ID, 2, 5)).toBeNull();
  });

  it('guarda copia de catálogo asociada a empresa, cajero y sucursal', async () => {
    await store.saveCatalog({
      empresa_id: 2, sucursal_id: 7, descargado_en: ROW.creado_en,
      items: [{ variante_id: 13, producto_id: 1, nombre: 'Polera', talla: 'M',
        color: 'Rojo', precio_unitario: '80.10' }],
    }, 5);
    expect((await store.catalog(2, 5, 7))?.items).toHaveLength(1);
    expect(await store.catalog(2, 8, 7)).toBeNull();
    expect(await store.catalog(3, 5, 7)).toBeNull();
  });
});
