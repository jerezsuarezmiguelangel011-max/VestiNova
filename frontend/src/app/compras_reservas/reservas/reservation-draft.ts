import { DatePipe, isPlatformBrowser } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, PLATFORM_ID, effect, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';
import {
  CatalogApiService, type CatalogAvailability, type CatalogAvailabilityItem,
} from '../../catalogo_publico/catalogo/catalog-api.service';
import { CatalogShopService } from '../../catalogo_publico/catalogo/catalog-shop.service';
import type { CatalogProduct } from '../../catalogo_publico/catalogo/catalog.models';
import { CustomerAuthService } from '../clientes/customer-auth.service';
import { ReservationOfflineStore, type OfflineReservation } from './reservation-offline-store.service';
import { ReservationOfflineSyncService } from './reservation-offline-sync.service';
import { ReservationOnlineApiService, type ReservationResult } from './reservation-online-api.service';

export interface ReservationDraftLine {
  variante_id: number;
  cantidad: number;
  sucursal_id: number;
  sucursal_nombre: string;
  talla: string;
  color: string;
}

export interface ReservationDraft {
  tienda: string;
  id: string;
  producto_id: number;
  producto_nombre: string;
  producto_slug: string;
  sucursal_id: number;
  sucursal_nombre: string;
  variante_id: number;
  talla: string;
  color: string;
  cantidad: number;
  /** Variantes de una sola sucursal; formato anterior sin lineas se mantiene legible. */
  lineas?: ReservationDraftLine[];
  creado_en: string;
  estado: 'BORRADOR_LOCAL';
}

@Component({
  selector: 'vn-reservation-draft',
  imports: [ReactiveFormsModule, RouterLink, DatePipe],
  templateUrl: './reservation-draft.html',
  styleUrl: './reservation-draft.css',
})
export class ReservationDraftPage {
  readonly shop = inject(CatalogShopService);
  readonly customers = inject(CustomerAuthService);
  readonly sync = inject(ReservationOfflineSyncService);
  private readonly offline = inject(ReservationOfflineStore);
  private readonly online = inject(ReservationOnlineApiService);
  private readonly catalog = inject(CatalogApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  private readonly browser = isPlatformBrowser(inject(PLATFORM_ID));

  readonly product = signal<CatalogProduct | null>(null);
  readonly availability = signal<CatalogAvailability | null>(null);
  readonly cachedAt = signal<string | null>(null);
  readonly policyHours = signal<number | null>(null);
  readonly loading = signal(false);
  readonly submitting = signal(false);
  readonly historyLoading = signal(false);
  readonly error = signal<string | null>(null);
  readonly notice = signal<string | null>(null);
  readonly returnedFromLogin = signal(false);
  readonly draft = signal<ReservationDraft | null>(null);
  readonly selectedLines = signal<ReservationDraftLine[]>([]);
  readonly confirmed = signal<ReservationResult | null>(null);
  readonly reservations = signal<ReservationResult[]>([]);
  readonly offlineOperations = signal<OfflineReservation[]>([]);
  readonly form = new FormGroup({
    key: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
    cantidad: new FormControl(1, {
      nonNullable: true, validators: [Validators.required, Validators.min(1), Validators.max(100)],
    }),
  });
  private requestVersion = 0;
  private historyRevision = 0;
  private selectedProductSlug: string | null = null;
  // La tienda puede estar seleccionada antes de que Angular ejecute el primer
  // effect. No debemos invalidar la carga inicial al reconocer ese mismo ámbito.
  private activeShop: string | null = this.shop.tienda();

  constructor() {
    effect(() => {
      const shop = this.shop.tienda();
      if (shop !== this.activeShop) {
        this.activeShop = shop;
        this.requestVersion++;
        this.historyRevision++;
        this.confirmed.set(null);
        this.reservations.set([]);
        this.offlineOperations.set([]);
        this.draft.set(null);
        this.selectedLines.set([]);
        this.cachedAt.set(null);
        this.policyHours.set(null);
        void this.refreshOffline();
      }
    });
    if (this.browser) {
      const handler = () => { void this.synchronize(); };
      window.addEventListener('online', handler);
      this.destroyRef.onDestroy(() => window.removeEventListener('online', handler));
    }
  }

  ngOnInit(): void {
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(params => {
      this.requestVersion++;
      const slug = params.get('slug');
      this.selectedProductSlug = slug;
      const returned = params.get('acceso') === 'reserva';
      this.returnedFromLogin.set(returned);
      this.product.set(null);
      this.availability.set(null);
      this.cachedAt.set(null);
      this.policyHours.set(null);
      this.form.reset({ key: '', cantidad: 1 });
      this.selectedLines.set([]);
      this.notice.set(null);
      this.error.set(null);
      void this.refreshOffline();
      const tienda = this.shop.tienda();
      if (tienda && this.customers.token(tienda)) {
        this.customers.ensureSession(tienda).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
          next: async customer => {
            await this.refreshOffline();
            if (returned && customer?.empresa.slug === tienda &&
                tienda === this.shop.tienda() && slug === this.selectedProductSlug) {
              const waiting = this.draft();
              if (waiting?.tienda === tienda && waiting.producto_slug === slug) {
                this.notice.set('Sesión iniciada. Recuperamos tu borrador: revísalo y pulsa «Confirmar y enviar reserva». No se ha enviado automáticamente.');
              } else {
                this.notice.set('Sesión iniciada. No encontramos un borrador pendiente para esta prenda; puedes preparar uno nuevo.');
              }
            }
          },
          error: () => { /* Las operaciones locales persisten aunque falle la red. */ },
        });
      }
      if (!slug || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)) {
        this.loading.set(false);
        this.error.set('Selecciona una prenda del catálogo para preparar una reserva.');
        return;
      }
      void this.load(slug);
    });
  }

  private async load(slug: string): Promise<void> {
    const revision = ++this.requestVersion;
    const tienda = this.shop.tienda();
    if (!tienda) {
      this.error.set('Selecciona una empresa antes de reservar una prenda.');
      return;
    }
    this.loading.set(true);
    forkJoin({ product: this.catalog.get(slug), availability: this.catalog.availability(slug),
      policy: this.online.policy(tienda) })
      .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: ({ product, availability, policy }) => {
          if (revision !== this.requestVersion || tienda !== this.shop.tienda()) return;
          this.product.set(product);
          this.availability.set(availability);
          this.cachedAt.set(null);
          this.policyHours.set(policy.vigencia_horas);
          this.loading.set(false);
          void this.offline.remember(tienda, slug, product, availability, policy.vigencia_horas).catch(() => {
            this.notice.set('No fue posible guardar una copia para trabajar sin conexión.');
          });
        },
        error: (cause: unknown) => {
          if (revision !== this.requestVersion || tienda !== this.shop.tienda()) return;
          const code = cause instanceof HttpErrorResponse ? cause.status : -1;
          if (![0, 503, 504].includes(code)) {
            this.loading.set(false);
            this.error.set('La prenda no está publicada o no puede consultarse en esta tienda.');
            return;
          }
          void this.offline.cached(tienda, slug).then(copy => {
            if (revision !== this.requestVersion || tienda !== this.shop.tienda()) return;
            this.loading.set(false);
            if (!copy) {
              this.error.set('Sin conexión y sin copia local de esta prenda. Descarga su información al estar en línea.');
              return;
            }
            this.product.set(copy.producto);
            this.availability.set(copy.disponibilidad);
            this.cachedAt.set(copy.guardado_en);
            this.policyHours.set(copy.vigencia_horas);
            this.notice.set('Usando datos descargados. La disponibilidad puede haber cambiado.');
          }).catch(() => {
            if (revision === this.requestVersion) {
              this.loading.set(false);
              this.error.set('No se pudo abrir el catálogo guardado en el dispositivo.');
            }
          });
        },
      });
  }

  selectable(): CatalogAvailabilityItem[] {
    return this.availability()?.items.filter(row => row.hay_disponibilidad) ?? [];
  }

  private currentId(): number | null {
    const tienda = this.shop.tienda();
    const customer = this.customers.customer();
    return tienda && customer?.empresa.slug === tienda ? customer.id : null;
  }

  async refreshOffline(): Promise<void> {
    const tienda = this.shop.tienda();
    if (!tienda) return;
    const clienteId = this.currentId();
    try {
      const rows = await this.offline.list(tienda, clienteId);
      // Los borradores sin cuenta se recuperan aun despues de iniciar sesión:
      // deben asociarse explícitamente al cliente antes de enviarlos.
      const anonymous = clienteId === null ? rows : await this.offline.list(tienda, null);
      if (tienda !== this.shop.tienda() || clienteId !== this.currentId()) return;
      this.offlineOperations.set(rows.filter(row => row.estado !== 'BORRADOR_LOCAL'));
      const selectedSlug = this.selectedProductSlug;
      // Al regresar del acceso recuperamos la prenda de origen, no el último
      // borrador de otra prenda guardada en el mismo navegador.
      if (!this.draft() || this.draft()?.producto_slug !== selectedSlug) {
        this.draft.set(anonymous.find(row =>
          row.estado === 'BORRADOR_LOCAL' && row.draft.producto_slug === selectedSlug)?.draft ?? null);
      }
    } catch {
      this.error.set('No se pudo consultar la cola persistente de reservas de este navegador.');
    }
  }

  addLine(): void {
    this.error.set(null);
    const { key, cantidad } = this.form.getRawValue();
    const candidate = this.selectable().find(row => key === `${row.sucursal_id}:${row.variante_id}`);
    if (!candidate || !Number.isSafeInteger(cantidad) || cantidad < 1 || cantidad > 100) {
      this.error.set('Selecciona una variante disponible y una cantidad entera válida.');
      return;
    }
    const current = this.selectedLines();
    if (current.some(line => line.variante_id === candidate.variante_id)) {
      this.error.set('Esta variante ya está añadida a la reserva.');
      return;
    }
    if (current.length >= 30) {
      this.error.set('Puedes incluir como máximo 30 variantes distintas por reserva.');
      return;
    }
    if (current.length && current[0].sucursal_id !== candidate.sucursal_id) {
      this.error.set('Todas las variantes de una reserva deben retirarse en la misma sucursal.');
      return;
    }
    this.selectedLines.update(lines => [...lines, {
      variante_id: candidate.variante_id, cantidad, sucursal_id: candidate.sucursal_id,
      sucursal_nombre: candidate.sucursal, talla: candidate.talla, color: candidate.color,
    }]);
    this.form.reset({ key: '', cantidad: 1 });
  }

  removeLine(varianteId: number): void {
    if (this.submitting()) return;
    this.selectedLines.update(lines => lines.filter(line => line.variante_id !== varianteId));
  }

  draftLines(draft: ReservationDraft): ReservationDraftLine[] {
    return draft.lineas?.length ? draft.lineas : [{
      variante_id: draft.variante_id, cantidad: draft.cantidad,
      sucursal_id: draft.sucursal_id, sucursal_nombre: draft.sucursal_nombre,
      talla: draft.talla, color: draft.color,
    }];
  }

  draftQuantity(draft: ReservationDraft): number {
    return this.draftLines(draft).reduce((total, line) => total + line.cantidad, 0);
  }

  async saveDraft(): Promise<void> {
    this.error.set(null);
    this.notice.set(null);
    const product = this.product();
    const tienda = this.shop.tienda();
    if (!this.browser || !product || !tienda || !this.availability() || this.loading()) return;
    const { key, cantidad } = this.form.getRawValue();
    const selection = this.selectedLines();
    const variant = this.selectable().find(row => key === `${row.sucursal_id}:${row.variante_id}`);
    const chosen: ReservationDraftLine[] = selection.length ? selection : variant &&
      Number.isSafeInteger(cantidad) && cantidad >= 1 && cantidad <= 100
      ? [{ variante_id: variant.variante_id, cantidad,
           sucursal_id: variant.sucursal_id, sucursal_nombre: variant.sucursal,
           talla: variant.talla, color: variant.color }] : [];
    if (!chosen.length || chosen.length > 30 ||
        chosen.some(line => !this.selectable().some(item => item.sucursal_id === line.sucursal_id &&
          item.variante_id === line.variante_id)) ||
        new Set(chosen.map(line => line.sucursal_id)).size !== 1 ||
        new Set(chosen.map(line => line.variante_id)).size !== chosen.length) {
      this.form.markAllAsTouched();
      this.error.set('Selecciona variantes válidas de una misma sucursal antes de guardar.');
      return;
    }
    const first = chosen[0];
    const draft: ReservationDraft = {
      tienda, id: crypto.randomUUID(), producto_id: product.id, producto_nombre: product.nombre,
      producto_slug: product.slug, sucursal_id: first.sucursal_id, sucursal_nombre: first.sucursal_nombre,
      variante_id: first.variante_id, talla: first.talla, color: first.color,
      cantidad: first.cantidad, lineas: chosen, creado_en: new Date().toISOString(), estado: 'BORRADOR_LOCAL',
    };
    this.submitting.set(true);
    try {
      const clienteId = this.currentId();
      await this.offline.saveDraft(draft, clienteId);
      this.selectedLines.set([]);
      if (clienteId === null) {
        this.draft.set(draft);
        this.notice.set('Borrador guardado en este dispositivo. Inicia sesión para volver aquí y confirmar el envío.');
      } else {
        this.draft.set(null);
        this.notice.set('Solicitud guardada en IndexedDB con su UUID; pendiente de confirmación central.');
      }
      await this.refreshOffline();
    } catch {
      this.error.set('No se guardó la solicitud. Revisa el espacio y permisos de IndexedDB.');
    } finally {
      this.submitting.set(false);
    }
  }

  async confirmDraft(): Promise<void> {
    const tienda = this.shop.tienda();
    const draft = this.draft();
    const clienteId = this.currentId();
    this.error.set(null);
    if (!tienda || !draft || draft.tienda !== tienda || clienteId === null) {
      this.error.set('Inicia sesión con una cuenta de cliente de esta misma tienda.');
      return;
    }
    this.submitting.set(true);
    try {
      const row = await this.offline.get(draft.id);
      if (!row) await this.offline.saveDraft(draft, clienteId);
      else if (row.estado === 'BORRADOR_LOCAL') await this.offline.assign(draft.id, tienda, clienteId);
      this.draft.set(null);
      await this.refreshOffline();
      this.notice.set('Solicitud enviada a la cola con el mismo UUID. Comprobaremos su confirmación con el servidor.');
    } catch {
      this.error.set('No pudimos convertir el borrador en una solicitud pendiente.');
    } finally { this.submitting.set(false); }
    if (!this.error()) await this.synchronize();
  }

  async clearDraft(): Promise<void> {
    const draft = this.draft();
    if (!draft) return;
    try {
      await this.offline.discardDraft(draft.id, draft.tienda);
      this.draft.set(null);
      this.notice.set('Borrador no enviado eliminado.');
    } catch {
      this.error.set('No se pudo eliminar el borrador local.');
    }
  }

  async synchronize(): Promise<void> {
    const tienda = this.shop.tienda();
    const clienteId = this.currentId();
    if (!tienda || clienteId === null) {
      this.notice.set('Inicia sesión como cliente para enviar tus solicitudes pendientes.');
      return;
    }
    await this.sync.process(tienda, clienteId);
    await this.refreshOffline();
    const last = this.offlineOperations().find(row => row.resultado?.estado === 'CONFIRMADA');
    if (last?.resultado) this.confirmed.set(last.resultado);
    if (this.offlineOperations().some(row => row.estado === 'CONFIRMADA')) {
      this.notice.set('La reserva fue confirmada por el servidor. Ya puedes consultar su código.');
      this.loadMyReservations();
    } else if (this.sync.message()) {
      this.notice.set(this.sync.message());
    } else {
      this.notice.set('La cola se actualizó. Comprueba el estado de cada solicitud.');
    }
  }

  async retryReservation(id: string): Promise<void> {
    const tienda = this.shop.tienda();
    const clienteId = this.currentId();
    if (!tienda || clienteId === null) return;
    try {
      await this.offline.retry(id, tienda, clienteId);
      await this.synchronize();
    } catch {
      this.error.set('No se pudo dejar la operación lista para otro intento.');
    }
  }

  loadMyReservations(): void {
    const tienda = this.shop.tienda();
    if (!tienda || !this.customers.token(tienda) || this.historyLoading()) return;
    const revision = ++this.historyRevision;
    this.historyLoading.set(true);
    this.online.list(tienda).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: rows => {
        if (revision !== this.historyRevision || tienda !== this.shop.tienda()) return;
        this.reservations.set(rows);
        this.historyLoading.set(false);
      },
      error: () => {
        if (revision !== this.historyRevision || tienda !== this.shop.tienda()) return;
        this.historyLoading.set(false);
        this.error.set('No se pudo consultar el historial central. Tus operaciones locales siguen guardadas.');
      },
    });
  }

  cancelReservation(id: string): void {
    const tienda = this.shop.tienda();
    if (!tienda || !this.customers.token(tienda) || this.submitting()) return;
    this.submitting.set(true);
    this.error.set(null);
    this.online.cancel(tienda, id).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        this.submitting.set(false);
        if (tienda !== this.shop.tienda()) return;
        this.reservations.update(rows => rows.map(row => row.id === id ? result : row));
        if (this.confirmed()?.id === id) this.confirmed.set(result);
        this.notice.set('Reserva cancelada en el servidor. Compromiso liberado.');
      },
      error: () => {
        this.submitting.set(false);
        this.error.set('No se pudo cancelar la reserva. Revisa su estado central.');
      },
    });
  }
}
