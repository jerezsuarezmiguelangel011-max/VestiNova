import { HttpErrorResponse } from '@angular/common/http';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { BehaviorSubject, Subject, of, throwError, type Observable } from 'rxjs';
import { CatalogDataService } from './catalog-data.service';
import { CatalogDetailPage } from './catalog-detail';
import { CatalogListPage } from './catalog-list';
import { CatalogLocalError, type CatalogList, type CatalogProduct, type CatalogResult } from './catalog.models';

const DOWNLOADED_AT = '2026-10-25T12:00:00Z';
const PRODUCT: CatalogProduct = {
  id: 7, nombre: 'Camisa de lino', slug: 'camisa-de-lino', descripcion: 'Lino natural.',
  precio: '149.90', moneda: 'BOB', imagen_url: null, activo: true,
  creado_en: DOWNLOADED_AT, actualizado_en: DOWNLOADED_AT,
};
const LIST: CatalogList = { items: [PRODUCT], total: 1, limit: 20, offset: 0 };
const LOCAL_LIST: CatalogResult<CatalogList> = { data: LIST, source: 'local', downloadedAt: DOWNLOADED_AT };
const LOCAL_PRODUCT: CatalogResult<CatalogProduct> = { data: PRODUCT, source: 'local', downloadedAt: DOWNLOADED_AT };

describe('Información de la copia local del catálogo', () => {
  async function listSetup(response: () => Observable<CatalogResult<CatalogList>> = () => of(LOCAL_LIST)) {
    const list = vi.fn(response);
    const revision = signal(0);
    await TestBed.configureTestingModule({
      imports: [CatalogListPage],
      providers: [provideRouter([]), { provide: CatalogDataService, useValue: { list, revision } }],
    }).compileComponents();
    const fixture = TestBed.createComponent(CatalogListPage);
    fixture.detectChanges();
    return { fixture, component: fixture.componentInstance, root: fixture.nativeElement as HTMLElement, list, revision };
  }

  async function detailSetup(response: () => Observable<CatalogResult<CatalogProduct>> = () => of(LOCAL_PRODUCT)) {
    const get = vi.fn(response);
    const revision = signal(0);
    const params = new BehaviorSubject(convertToParamMap({ slug: PRODUCT.slug }));
    await TestBed.configureTestingModule({
      imports: [CatalogDetailPage],
      providers: [
        provideRouter([]), { provide: CatalogDataService, useValue: { get, revision } },
        { provide: ActivatedRoute, useValue: { paramMap: params.asObservable() } },
      ],
    }).compileComponents();
    const fixture = TestBed.createComponent(CatalogDetailPage);
    fixture.detectChanges();
    return { fixture, component: fixture.componentInstance, root: fixture.nativeElement as HTMLElement, get, params, revision };
  }

  function expectLocalNotice(root: HTMLElement): void {
    const notice = root.querySelector('.catalog-local-notice');
    expect(notice?.textContent).toContain('Copia local');
    expect(notice?.textContent).toContain('puede estar desactualizada');
    expect(notice?.querySelector('time')?.getAttribute('datetime')).toBe(DOWNLOADED_AT);
    expect(notice?.querySelector('time')?.textContent).toBe('25/10/2026 08:00');
  }

  it('identifica la lista local y su fecha de descarga sin alterar el precio', async () => {
    const { root } = await listSetup();
    expectLocalNotice(root);
    expect(root.querySelector('.catalog-card')?.textContent).toContain(PRODUCT.nombre);
    expect(root.querySelector('.catalog-price')?.textContent).toBe('Bs 149.90');
  });

  it('retira el aviso local cuando una nueva consulta obtiene datos de red', async () => {
    const { fixture, component, root, list } = await listSetup();
    expectLocalNotice(root);
    list.mockReturnValueOnce(of({ data: LIST, source: 'network', downloadedAt: null }));
    component.reload();
    fixture.detectChanges();
    expect(component.source()).toBe('network');
    expect(component.downloadedAt()).toBeNull();
    expect(root.querySelector('.catalog-local-notice')).toBeNull();
  });

  it('distingue la ausencia de copia de un catálogo sin prendas', async () => {
    const { root } = await listSetup(vi.fn(() => throwError(() => new CatalogLocalError('no-copy'))));
    expect(root.querySelector('[role="alert"]')?.textContent).toContain('No hay un catálogo descargado');
    expect(root.textContent).not.toContain('No hay prendas publicadas');
    expect(root.querySelector('.catalog-card')).toBeNull();
    expect(root.querySelector('.catalog-local-notice')).toBeNull();
  });

  it('reconoce una copia descargada vacía y mantiene su fecha', async () => {
    const { root } = await listSetup(vi.fn(() => of({ ...LOCAL_LIST, data: { ...LIST, items: [], total: 0 } })));
    expectLocalNotice(root);
    expect(root.textContent).toContain('La copia descargada no contiene prendas');
    expect(root.textContent).not.toContain('No hay un catálogo descargado');
    expect(root.textContent).not.toContain('No hay prendas publicadas');
  });

  it('identifica el detalle local con la fecha que corresponde a su respuesta', async () => {
    const { root } = await detailSetup();
    expectLocalNotice(root);
    expect(root.querySelector('h1')?.textContent).toBe(PRODUCT.nombre);
    expect(root.querySelector('.catalog-detail__price')?.textContent).toContain('Bs 149.90');
  });

  it('no presenta una prenda ausente en la copia como despublicada en el servidor', async () => {
    const { root, component } = await detailSetup(vi.fn(() => throwError(
      () => new CatalogLocalError('missing-product', DOWNLOADED_AT),
    )));
    expectLocalNotice(root);
    expect(component.notFound()).toBe(false);
    expect(component.product()).toBeNull();
    expect(root.querySelector('[role="alert"]')?.textContent).toContain('no está incluida en la copia local');
    expect(root.textContent).not.toContain('ya no esté publicado');
    expect(root.querySelector('article')).toBeNull();
  });

  it('explica que no existe copia para el detalle y permite volver al catálogo', async () => {
    const { root, component } = await detailSetup(vi.fn(() => throwError(() => new CatalogLocalError('no-copy'))));
    expect(component.notFound()).toBe(false);
    expect(root.querySelector('[role="alert"]')?.textContent).toContain('Descargar catálogo');
    expect(root.querySelector('a')?.getAttribute('href')).toBe('/catalogo');
    expect(root.querySelector('time')).toBeNull();
  });

  it.each([401, 403])('presenta un permiso denegado %s en lista sin aviso local', async status => {
    const { root } = await listSetup(vi.fn(() => throwError(() => new HttpErrorResponse({ status }))));
    expect(root.querySelector('[role="alert"]')?.textContent).toContain('No tienes permiso');
    expect(root.querySelector('.catalog-local-notice')).toBeNull();
    expect(root.querySelector('.catalog-card')).toBeNull();
  });

  it.each([401, 403])('presenta un permiso denegado %s en detalle sin aviso local', async status => {
    const { root, component } = await detailSetup(vi.fn(() => throwError(() => new HttpErrorResponse({ status }))));
    expect(component.notFound()).toBe(false);
    expect(root.querySelector('[role="alert"]')?.textContent).toContain('No tienes permiso');
    expect(root.querySelector('.catalog-local-notice')).toBeNull();
    expect(root.querySelector('article')).toBeNull();
  });

  it('limpia la procedencia anterior al cambiar de slug y usa la de la respuesta nueva', async () => {
    const { fixture, component, root, params, get } = await detailSetup();
    expectLocalNotice(root);
    const next = new Subject<CatalogResult<CatalogProduct>>();
    get.mockReturnValueOnce(next);
    params.next(convertToParamMap({ slug: 'falda-plisada' }));
    fixture.detectChanges();
    expect(component.source()).toBeNull();
    expect(component.downloadedAt()).toBeNull();
    expect(root.querySelector('.catalog-local-notice')).toBeNull();
    next.next({
      data: { ...PRODUCT, id: 8, nombre: 'Falda plisada', slug: 'falda-plisada' },
      source: 'network', downloadedAt: null,
    });
    next.complete();
    fixture.detectChanges();
    expect(root.querySelector('h1')?.textContent).toBe('Falda plisada');
    expect(root.querySelector('.catalog-local-notice')).toBeNull();
  });

  it('refresca la consulta de lista vigente tras finalizar una descarga', async () => {
    const { fixture, component, list, revision } = await listSetup();
    component.filters.controls.q.setValue('lino');
    component.search();
    fixture.detectChanges();
    list.mockClear();
    revision.set(1);
    fixture.detectChanges();
    expect(list).toHaveBeenCalledExactlyOnceWith({ q: 'lino', limit: 20, offset: 0 });
  });

  it('refresca el mismo slug tras finalizar una descarga aunque el detalle ya esté cargado', async () => {
    const { fixture, get, revision } = await detailSetup();
    get.mockClear();
    revision.set(1);
    fixture.detectChanges();
    expect(get).toHaveBeenCalledExactlyOnceWith(PRODUCT.slug);
  });
});
