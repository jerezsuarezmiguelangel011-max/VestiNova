import { HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { CustomerAuthService } from '../clientes/customer-auth.service';
import { ReservationOnlineApiService } from './reservation-online-api.service';
import { shortageMessage } from './reservation-stock-error';
import {
  ReservationOfflineStore, type OfflineReservation, type OfflineReservationState,
} from './reservation-offline-store.service';

function explanation(error: HttpErrorResponse): { state: OfflineReservationState; message: string } {
  if (error.status === 409) {
    return { state: 'CONFLICTO', message: shortageMessage(error) ?? 'La reserva no pudo confirmarse: disponibilidad o UUID en conflicto. Requiere revisión.' };
  }
  if (error.status === 400 || error.status === 404 || error.status === 422) {
    return { state: 'RECHAZADA', message: 'La solicitud fue rechazada por sus datos o referencias. El registro queda conservado.' };
  }
  if (error.status === 401 || error.status === 403) {
    return { state: 'REQUIERE_ACCESO', message: 'Debes renovar el acceso o revisar permisos de esta tienda.' };
  }
  return { state: 'ERROR', message: 'Sin respuesta definitiva del servidor. Conservamos el UUID para reintentar.' };
}

@Injectable({ providedIn: 'root' })
export class ReservationOfflineSyncService {
  private readonly store = inject(ReservationOfflineStore);
  private readonly online = inject(ReservationOnlineApiService);
  private readonly auth = inject(CustomerAuthService);
  readonly processing = signal(false);
  readonly message = signal<string | null>(null);

  /** Solo se envían operaciones del cliente autenticado en esta tienda. */
  async process(tienda: string, clienteId: number): Promise<void> {
    if (this.processing()) return;
    if (this.auth.customer()?.id !== clienteId ||
        this.auth.customer()?.empresa.slug !== tienda ||
        !this.auth.token(tienda)) {
      this.message.set('Primero confirma tu sesión de cliente de esta tienda para sincronizar.');
      return;
    }
    this.processing.set(true);
    this.message.set(null);
    const run = async () => {
      // El bloqueo se mantiene durante el HTTP para evitar dos envíos en pestañas diferentes.
      await this.store.recoverSending(tienda, clienteId);
      const pending = (await this.store.list(tienda, clienteId))
        .filter(item => ['PENDIENTE', 'ERROR', 'REQUIERE_ACCESO'].includes(item.estado));
      for (const item of pending.reverse()) {
        if (this.auth.customer()?.id !== clienteId ||
            this.auth.customer()?.empresa.slug !== tienda || !this.auth.token(tienda)) break;
        const claimed = await this.store.claim(item.id, tienda, clienteId);
        if (!claimed) continue;
        await this.submit(claimed);
      }
    };
    try {
      const locks = typeof navigator !== 'undefined' ? navigator.locks : undefined;
      if (locks) {
        await locks.request('vn-cu10-reservas-' + tienda + '-' + clienteId,
          { mode: 'exclusive', ifAvailable: true }, async lock => {
            if (lock) await run();
            else this.message.set('Otra pestaña está sincronizando estas reservas.');
          });
      } else {
        // El backend valida el UUID de modo idempotente incluso sin Web Locks.
        await run();
      }
    } catch {
      this.message.set('Falló el almacenamiento local. No se eliminó ninguna reserva pendiente.');
    } finally {
      this.processing.set(false);
    }
  }

  private async submit(item: OfflineReservation): Promise<void> {
    try {
      const result = await firstValueFrom(this.online.create(item.tienda, {
        id: item.id,
        sucursal_id: item.draft.sucursal_id,
        lineas: (item.draft.lineas ?? [{
          variante_id: item.draft.variante_id, cantidad: item.draft.cantidad,
        }]).map(line => ({ variante_id: line.variante_id, cantidad: line.cantidad })),
        solicitado_en: item.creado_en,
        origen: 'WEB_OFFLINE',
      }));
      await this.store.finish(item.id, result.estado, 'Estado confirmado por el servidor.', result);
    } catch (cause: unknown) {
      const outcome = cause instanceof HttpErrorResponse ? explanation(cause)
        : { state: 'ERROR' as const, message: 'No se recibió confirmación. Reintentar con el mismo UUID.' };
      // No borrar aunque se haya perdido la respuesta después de un commit en PostgreSQL.
      await this.store.finish(item.id,
        outcome.state as 'ERROR' | 'RECHAZADA' | 'CONFLICTO' | 'REQUIERE_ACCESO', outcome.message);
    }
  }
}
