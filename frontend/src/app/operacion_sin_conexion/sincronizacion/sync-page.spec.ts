import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import type { SyncOperation, SyncState } from './sync.models';
import { SyncPage } from './sync-page';
import { SyncService } from './sync.service';

const CREATED_AT = '2026-10-25T12:00:00Z';
const UPDATED_AT = '2026-10-25T12:15:00Z';

function operation(state: SyncState = 'PENDIENTE', id = '10000000-0000-4000-8000-000000000001'): SyncOperation {
  return {
    id, scope: 'public-catalog', type: 'ACTUALIZAR_CATALOGO', expectedDownloadedAt: '2026-10-24T14:00:00Z',
    state, createdAt: CREATED_AT, updatedAt: UPDATED_AT, message: null,
  };
}

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>(accept => { resolve = accept; });
  return { promise, resolve };
}

describe('Control manual de operaciones de sincronización', () => {
  async function setup(options: { operations?: SyncOperation[]; pendingRefresh?: Promise<void> } = {}) {
    const sync = {
      operations: signal<SyncOperation[]>(options.operations ?? []),
      processing: signal(false), enqueuing: signal(false), error: signal<string | null>(null),
      refresh: vi.fn<() => Promise<void>>().mockImplementation(() => options.pendingRefresh ?? Promise.resolve()),
      enqueueCatalogUpdate: vi.fn<() => Promise<void>>().mockResolvedValue(undefined),
      processPending: vi.fn<() => Promise<void>>().mockResolvedValue(undefined),
      retry: vi.fn<(id: string) => Promise<void>>().mockResolvedValue(undefined),
    };
    await TestBed.configureTestingModule({
      imports: [SyncPage],
      providers: [provideRouter([]), { provide: SyncService, useValue: sync }],
    }).compileComponents();
    const fixture = TestBed.createComponent(SyncPage);
    fixture.detectChanges();
    return { fixture, component: fixture.componentInstance, root: fixture.nativeElement as HTMLElement, sync };
  }

  it('consulta las operaciones al abrir y no registra ni procesa nada automáticamente', async () => {
    const pending = deferred();
    const { root, sync, fixture } = await setup({ pendingRefresh: pending.promise });
    expect(sync.refresh).toHaveBeenCalledExactlyOnceWith();
    expect(root.textContent).toContain('Cargando operaciones guardadas');
    expect(root.textContent).not.toContain('Todavía no hay operaciones');
    expect(sync.enqueueCatalogUpdate).not.toHaveBeenCalled();
    expect(sync.processPending).not.toHaveBeenCalled();
    expect(sync.retry).not.toHaveBeenCalled();
    pending.resolve();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(root.textContent).toContain('Todavía no hay operaciones');
    expect(root.querySelector('.sync-scope')?.textContent).toContain('Por ahora se actualiza únicamente el catálogo público. La sincronización de compras y reservas todavía no está disponible.');
  });

  it('registra únicamente una actualización de catálogo al pulsar el botón explícito', async () => {
    const { fixture, root, sync } = await setup();
    await fixture.whenStable();
    const pending = deferred();
    sync.enqueueCatalogUpdate.mockImplementation(() => {
      sync.enqueuing.set(true);
      return pending.promise.finally(() => sync.enqueuing.set(false));
    });
    const button = root.querySelector('.sync-enqueue') as HTMLButtonElement;
    expect(button.textContent).toContain('Registrar actualización pendiente');
    button.click();
    fixture.detectChanges();
    expect(sync.enqueueCatalogUpdate).toHaveBeenCalledExactlyOnceWith();
    expect(button.disabled).toBe(true);
    expect(button.textContent).toContain('Registrando');
    button.click();
    expect(sync.enqueueCatalogUpdate).toHaveBeenCalledTimes(1);
    expect(sync.processPending).not.toHaveBeenCalled();
    pending.resolve();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(button.disabled).toBe(false);
  });

  it('procesa pendientes solo a petición y desactiva el botón durante el procesamiento', async () => {
    const { fixture, root, component, sync } = await setup({ operations: [operation()] });
    await fixture.whenStable();
    const pending = deferred();
    sync.processPending.mockImplementation(() => {
      sync.processing.set(true);
      return pending.promise.finally(() => sync.processing.set(false));
    });
    const button = root.querySelector('.sync-process') as HTMLButtonElement;
    button.click();
    fixture.detectChanges();
    expect(sync.processPending).toHaveBeenCalledExactlyOnceWith();
    expect(button.disabled).toBe(true);
    expect(root.textContent).toContain('Procesando las operaciones pendientes');
    await component.process();
    expect(sync.processPending).toHaveBeenCalledTimes(1);
    pending.resolve();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(button.disabled).toBe(false);
  });

  it('muestra todos los estados, identidad y fechas de las operaciones en hora de Bolivia', async () => {
    const states: SyncState[] = ['PENDIENTE', 'PROCESANDO', 'SINCRONIZADA', 'CONFLICTO', 'ERROR'];
    const operations = states.map((state, index) => operation(state, `10000000-0000-4000-8000-00000000000${index}`));
    const { fixture, root } = await setup({ operations });
    await fixture.whenStable();
    fixture.detectChanges();
    expect([...root.querySelectorAll('.sync-state')].map(element => element.textContent)).toEqual(states);
    const first = root.querySelector('.sync-operation')!;
    expect(first.textContent).toContain(operations[0].id);
    expect(first.querySelector(`time[datetime="${CREATED_AT}"]`)?.textContent).toBe('25/10/2026 08:00');
    expect(first.querySelector(`time[datetime="${UPDATED_AT}"]`)?.textContent).toBe('25/10/2026 08:15');
    expect(first.textContent).toContain('24/10/2026 10:00');
    expect(first.textContent).toContain('Fechas en hora de Bolivia');
    expect(root.querySelector('.sync-operation[data-state="PROCESANDO"]')?.getAttribute('aria-busy')).toBe('true');
  });

  it('reintenta un error devolviéndolo a pendiente sin iniciar su procesamiento', async () => {
    const failed = { ...operation('ERROR'), message: 'No se pudo descargar el catálogo.' };
    const { fixture, root, sync } = await setup({ operations: [failed] });
    await fixture.whenStable();
    sync.retry.mockImplementation(async id => {
      sync.operations.update(operations => operations.map(item => item.id === id ? { ...item, state: 'PENDIENTE' as const, message: null } : item));
    });
    fixture.detectChanges();
    expect(root.textContent).toContain('No se pudo descargar el catálogo');
    expect(root.textContent).toContain('devuelve esta operación a pendiente');
    (root.querySelector('.sync-retry') as HTMLButtonElement).click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(sync.retry).toHaveBeenCalledExactlyOnceWith(failed.id);
    expect(sync.processPending).not.toHaveBeenCalled();
    expect(root.querySelector('.sync-state')?.textContent).toBe('PENDIENTE');
    expect(root.querySelector('.sync-retry')).toBeNull();
  });

  it('requiere revisar un conflicto y registrar otra operación sin ofrecer sobrescritura', async () => {
    const conflicted = operation('CONFLICTO');
    const { fixture, root, component, sync } = await setup({ operations: [conflicted] });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(root.querySelector('.sync-conflict')?.textContent).toContain('registra una nueva operación');
    expect(root.querySelector('.sync-retry')).toBeNull();
    expect(root.querySelector('.sync-operation a')?.getAttribute('href')).toBe('/catalogo');
    await component.retry(conflicted);
    expect(sync.retry).not.toHaveBeenCalled();
    expect(sync.processPending).not.toHaveBeenCalled();
  });

  it('muestra un error del servicio sin fingir que la lista está vacía', async () => {
    const { fixture, root, sync } = await setup();
    await fixture.whenStable();
    sync.error.set('No se pudo acceder al registro local de operaciones.');
    fixture.detectChanges();
    expect(root.querySelector('[role="alert"]')?.textContent).toContain('No se pudo acceder');
    expect(root.textContent).not.toContain('Todavía no hay operaciones');
  });

  it('controla un fallo al registrar sin mostrar trazas internas', async () => {
    const { fixture, root, component, sync } = await setup();
    await fixture.whenStable();
    sync.enqueueCatalogUpdate.mockRejectedValue(new Error('Detalle interno de IndexedDB'));
    await component.enqueue();
    fixture.detectChanges();
    expect(root.querySelector('[role="alert"]')?.textContent).toContain('No se pudo registrar la actualización pendiente');
    expect(root.textContent).not.toContain('Detalle interno');
    expect(sync.processPending).not.toHaveBeenCalled();
  });

  it('identifica que una operación fue registrada sin una copia previa del catálogo', async () => {
    const { fixture, root } = await setup({ operations: [{ ...operation(), expectedDownloadedAt: null }] });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(root.textContent).toContain('Sin copia previa');
    expect(root.textContent).toContain('Se procesará cuando pulses');
  });
});
