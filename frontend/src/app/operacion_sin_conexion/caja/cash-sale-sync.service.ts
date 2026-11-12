import { HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { AuthService } from '../../autenticacion_usuarios/autenticacion/auth.service';
import { CompanyService } from '../../organizacion_empresarial/empresa/company.service';
import { CashSaleApi } from './cash-sale-api.service';
import { CashSaleOfflineStore, type CashLocalSale } from './cash-sale-offline-store.service';

@Injectable({ providedIn: 'root' })
export class CashSaleSyncService {
  private readonly store = inject(CashSaleOfflineStore);
  private readonly api = inject(CashSaleApi);
  private readonly auth = inject(AuthService);
  private readonly companies = inject(CompanyService);
  readonly processing = signal(false);
  readonly message = signal<string | null>(null);

  async process(): Promise<void> {
    if (this.processing()) return;
    const company = this.companies.active();
    const user = this.auth.user();
    if (!company || !user || !this.auth.token() ||
        !['CAJERO', 'ENCARGADO_SUCURSAL'].includes(company.rol)) {
      this.message.set('Inicia sesión como cajero o encargado para sincronizar.');
      return;
    }
    const revision = this.companies.revision();
    this.processing.set(true);
    this.message.set(null);
    const run = async () => {
      await this.store.recover(company.id, user.id);
      const pending = (await this.store.list(company.id, user.id)).reverse().filter(
        item => ['PENDIENTE', 'ERROR', 'REQUIERE_ACCESO'].includes(item.estado));
      for (const item of pending) {
        if (revision !== this.companies.revision() ||
            this.auth.user()?.id !== user.id ||
            this.companies.active()?.id !== company.id) break;
        const claimed = await this.store.claim(item.id, company.id, user.id);
        if (claimed) await this.submit(claimed);
      }
    };
    try {
      const locks = typeof navigator !== 'undefined' ? navigator.locks : undefined;
      if (locks) await locks.request(`vn-cu15-${company.id}-${user.id}`,
        { mode: 'exclusive', ifAvailable: true },
        async lock => {
          if (lock) await run();
          else this.message.set('Otra pestaña está sincronizando ventas de esta cuenta.');
        });
      else await run();
    } catch {
      this.message.set('No fue posible leer o actualizar IndexedDB. Los cobros locales no fueron eliminados.');
    } finally {
      this.processing.set(false);
    }
  }

  private async submit(item: CashLocalSale): Promise<void> {
    try {
      const result = await firstValueFrom(this.api.create(item.solicitud));
      await this.store.finish(item.id, 'CONFIRMADA', 'Venta y stock verificados por el servidor.', result);
    } catch (cause: unknown) {
      if (!(cause instanceof HttpErrorResponse)) {
        await this.store.finish(item.id, 'ERROR', 'Respuesta incierta. Reintentar con el mismo UUID.');
        return;
      }
      const detail = cause.error?.detail;
      const incidentId = detail && typeof detail === 'object' &&
        typeof detail.incidencia_id === 'string' ? detail.incidencia_id : null;
      const reason = detail && typeof detail === 'object' && typeof detail.mensaje === 'string'
        ? detail.mensaje.slice(0, 350) : 'La venta no fue confirmada centralmente.';
      if (cause.status === 409 && incidentId)
        await this.store.finish(item.id, 'CONFLICTO', reason, null, incidentId);
      else if (cause.status === 409)
        await this.store.finish(item.id, 'RECHAZADA', reason);
      else if ([400, 404, 422].includes(cause.status))
        await this.store.finish(item.id, 'RECHAZADA', 'Solicitud rechazada. Conserva el comprobante provisional.');
      else if ([401, 403].includes(cause.status))
        await this.store.finish(item.id, 'REQUIERE_ACCESO', 'Sesión vencida o permisos insuficientes.');
      else await this.store.finish(item.id, 'ERROR', 'Respuesta incierta; se conserva el UUID y el efectivo capturado.');
    }
  }
}
