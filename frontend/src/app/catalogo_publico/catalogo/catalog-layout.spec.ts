import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { CatalogDataService } from './catalog-data.service';
import { CatalogLayout } from './catalog-layout';
import { CatalogPwaService, type CatalogPwaState } from './catalog-pwa.service';
import type { CatalogSnapshotMetadata } from './catalog.models';

const SAVED: CatalogSnapshotMetadata = {
  schemaVersion: 1, scope: 'public-catalog', downloadedAt: '2026-10-25T12:00:00Z', total: 0,
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((accept, fail) => { resolve = accept; reject = fail; });
  return { promise, resolve, reject };
}

describe('Descarga del catálogo desde el layout público', () => {
  async function setup(options: {
    saved?: CatalogSnapshotMetadata | null;
    preparation?: Promise<CatalogPwaState>;
  } = {}) {
    const data = {
      saved: signal<CatalogSnapshotMetadata | null>(options.saved ?? null),
      downloading: signal(false),
      progress: signal<{ received: number; total: number } | null>(null),
      downloadError: signal<string | null>(null),
      downloadNotice: signal<string | null>(null),
      storageError: signal<string | null>(null),
      refreshSavedStatus: vi.fn().mockResolvedValue(undefined),
      download: vi.fn<() => Promise<boolean>>().mockResolvedValue(true),
    };
    const prepare = vi.fn(() => options.preparation ?? Promise.resolve<CatalogPwaState>('unavailable'));
    await TestBed.configureTestingModule({
      imports: [CatalogLayout],
      providers: [
        provideRouter([]), { provide: CatalogDataService, useValue: data },
        { provide: CatalogPwaService, useValue: { prepare } },
      ],
    }).compileComponents();
    const fixture = TestBed.createComponent(CatalogLayout);
    fixture.detectChanges();
    await Promise.resolve();
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;
    const button = root.querySelector('.catalog-download button') as HTMLButtonElement;
    return { fixture, component: fixture.componentInstance, root, button, data, prepare };
  }

  it('ofrece una descarga explícita y comprueba si el navegador ya tiene copia', async () => {
    const { root, button, data } = await setup();
    expect(data.refreshSavedStatus).toHaveBeenCalledExactlyOnceWith();
    expect(root.textContent).toContain('Todavía no hay un catálogo descargado');
    expect(button.textContent?.trim()).toBe('Descargar catálogo');
    expect(button.disabled).toBe(false);
    expect(data.download).not.toHaveBeenCalled();
    button.click();
    expect(data.download).toHaveBeenCalledExactlyOnceWith();
  });

  it('reconoce una copia vacía válida y permite actualizarla conservando fecha y total', async () => {
    const { root, button } = await setup({ saved: SAVED });
    expect(button.textContent?.trim()).toBe('Actualizar catálogo local');
    expect(root.querySelector('.catalog-download time')?.getAttribute('datetime')).toBe(SAVED.downloadedAt);
    expect(root.querySelector('.catalog-download time')?.textContent).toBe('25/10/2026 08:00');
    expect(root.querySelector('.catalog-download')?.textContent).toContain('0 prendas');
    expect(root.textContent).not.toContain('Todavía no hay un catálogo descargado');
  });

  it('muestra progreso y desactiva el botón mientras la descarga continúa', async () => {
    const { fixture, root, button, data } = await setup();
    const transfer = deferred<boolean>();
    data.download.mockImplementation(() => {
      data.downloading.set(true);
      data.progress.set({ received: 100, total: 205 });
      return transfer.promise.finally(() => data.downloading.set(false));
    });
    button.click();
    fixture.detectChanges();
    expect(button.disabled).toBe(true);
    expect(button.textContent).toContain('Descargando');
    expect(root.querySelector('.catalog-download')?.getAttribute('aria-busy')).toBe('true');
    expect(root.textContent).toContain('100 de 205 prendas recibidas');
    expect(root.textContent).toContain('Espera la confirmación antes de desconectarte');
    button.click();
    expect(data.download).toHaveBeenCalledTimes(1);
    transfer.resolve(true);
    await fixture.whenStable();
    fixture.detectChanges();
    expect(button.disabled).toBe(false);
  });

  it('mantiene visible la fecha de la copia anterior si falla la actualización', async () => {
    const { fixture, root, button, data } = await setup({ saved: { ...SAVED, total: 2 } });
    data.download.mockImplementation(async () => {
      data.downloadError.set('No se pudo completar la descarga. La copia anterior se conserva.');
      return false;
    });
    button.click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(root.querySelector('[role="alert"]')?.textContent).toContain('La copia anterior se conserva');
    expect(root.querySelector('.catalog-download time')?.getAttribute('datetime')).toBe(SAVED.downloadedAt);
    expect(root.querySelector('.catalog-download')?.textContent).toContain('2 prendas');
    expect(button.textContent?.trim()).toBe('Actualizar catálogo local');
  });

  it('muestra la confirmación de descarga y los errores de almacenamiento del servicio', async () => {
    const { fixture, root, data } = await setup();
    data.downloadNotice.set('Catálogo local actualizado: 2 prendas guardadas.');
    data.storageError.set('No se pudo acceder al catálogo local.');
    fixture.detectChanges();
    expect(root.querySelector('.catalog-download')?.textContent).toContain('2 prendas guardadas');
    expect(root.querySelector('[role="alert"]')?.textContent).toContain('No se pudo acceder al catálogo local');
  });

  it('confirma la apertura offline únicamente cuando finaliza la verificación de los recursos', async () => {
    const preparation = deferred<CatalogPwaState>();
    const { fixture, component, root, prepare } = await setup({ preparation: preparation.promise });
    expect(prepare).toHaveBeenCalledExactlyOnceWith();
    expect(component.pwaState()).toBe('preparing');
    expect(root.querySelector('.catalog-pwa-status')?.textContent).toContain('Preparando la aplicación');
    expect(root.textContent).not.toContain('Apertura sin conexión preparada.');
    preparation.resolve('ready');
    await fixture.whenStable();
    fixture.detectChanges();
    expect(component.pwaState()).toBe('ready');
    expect(root.querySelector('.catalog-pwa-status')?.textContent).toContain('Apertura sin conexión preparada.');
    expect(root.querySelector('.catalog-pwa-status')?.textContent).toContain('Conserva también una descarga del catálogo');
  });

  it('no promete apertura offline si falla la comprobación del worker', async () => {
    const preparation = deferred<CatalogPwaState>();
    const { fixture, component, root } = await setup({ preparation: preparation.promise });
    preparation.reject(new Error('No disponible'));
    await fixture.whenStable();
    fixture.detectChanges();
    expect(component.pwaState()).toBe('error');
    expect(root.querySelector('.catalog-pwa-status')?.textContent).toContain('No se pudo confirmar la preparación');
    expect(root.textContent).not.toContain('Apertura sin conexión preparada.');
    expect(root.textContent).not.toContain('Error: No disponible');
  });

  it('no promete apertura offline cuando el worker está deshabilitado en desarrollo', async () => {
    const { root, component } = await setup({ preparation: Promise.resolve('unavailable') });
    expect(component.pwaState()).toBe('unavailable');
    expect(root.querySelector('.catalog-pwa-status')?.textContent).toContain('La apertura sin conexión aún no está preparada');
    expect(root.querySelector('.catalog-pwa-status')?.textContent).toContain('mientras la aplicación permanezca abierta');
    expect(root.textContent).not.toContain('Apertura sin conexión preparada.');
  });

  it('mantiene la descarga disponible cuando no puede preparar la apertura offline', async () => {
    const { root, component } = await setup();
    expect(component.pwaState()).toBe('unavailable');
    expect(root.querySelector('.catalog-pwa-status')?.textContent).toContain('La apertura sin conexión aún no está preparada');
    expect(root.querySelector('button')?.disabled).toBe(false);
  });

  it('explica que la aplicación ya abrió offline sin afirmar una nueva preparación', async () => {
    const { root, component } = await setup({ preparation: Promise.resolve('offline') });
    expect(component.pwaState()).toBe('offline');
    expect(root.querySelector('.catalog-pwa-status')?.textContent).toContain('Aplicación abierta con recursos guardados');
    expect(root.querySelector('.catalog-pwa-status')?.textContent).toContain('no se pudo comprobar una nueva preparación');
    expect(root.textContent).not.toContain('Apertura sin conexión preparada.');
  });

  it('no confirma preparación cuando la verificación devuelve error', async () => {
    const { root, component } = await setup({ preparation: Promise.resolve('error') });
    expect(component.pwaState()).toBe('error');
    expect(root.querySelector('.catalog-pwa-status')?.textContent).toContain('No se pudo confirmar la preparación');
    expect(root.textContent).not.toContain('Apertura sin conexión preparada.');
  });
});
