import { isPlatformBrowser } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, PLATFORM_ID, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';
import { CatalogApiService, type CatalogAvailability, type CatalogAvailabilityItem } from '../../catalogo_publico/catalogo/catalog-api.service';
import { CatalogShopService } from '../../catalogo_publico/catalogo/catalog-shop.service';
import type { CatalogProduct } from '../../catalogo_publico/catalogo/catalog.models';

const DRAFT_KEY = 'vestinova_reserva_borrador_v1';

export interface ReservationDraft {
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
  creado_en: string;
  estado: 'BORRADOR_LOCAL';
}

function isDraft(value: unknown): value is ReservationDraft {
  if (!value || typeof value !== 'object') return false;
  const d = value as Partial<ReservationDraft>;
  return typeof d.id === 'string' && /^[0-9a-f-]{36}$/i.test(d.id)
    && Number.isSafeInteger(d.producto_id) && (d.producto_id ?? 0) > 0
    && Number.isSafeInteger(d.sucursal_id) && (d.sucursal_id ?? 0) > 0
    && Number.isSafeInteger(d.variante_id) && (d.variante_id ?? 0) > 0
    && Number.isSafeInteger(d.cantidad) && (d.cantidad ?? 0) > 0
    && typeof d.producto_nombre === 'string' && typeof d.producto_slug === 'string'
    && typeof d.sucursal_nombre === 'string' && typeof d.talla === 'string'
    && typeof d.color === 'string' && typeof d.creado_en === 'string'
    && d.estado === 'BORRADOR_LOCAL';
}

@Component({
  selector: 'vn-reservation-draft',
  imports: [ReactiveFormsModule, RouterLink],
  templateUrl: './reservation-draft.html',
  styleUrl: './reservation-draft.css',
})
export class ReservationDraftPage {
  readonly shop = inject(CatalogShopService);
  private readonly catalog = inject(CatalogApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  private readonly browser = isPlatformBrowser(inject(PLATFORM_ID));
  readonly product = signal<CatalogProduct | null>(null);
  readonly availability = signal<CatalogAvailability | null>(null);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly notice = signal<string | null>(null);
  readonly draft = signal<ReservationDraft | null>(null);
  readonly form = new FormGroup({
    key: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
    cantidad: new FormControl(1, { nonNullable: true, validators: [Validators.required, Validators.min(1), Validators.max(100)] }),
  });
  private requestVersion = 0;

  ngOnInit(): void {
    this.restoreDraft();
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(params => {
      this.requestVersion++;
      const slug = params.get('slug');
      this.product.set(null);
      this.availability.set(null);
      this.form.reset({ key: '', cantidad: 1 });
      this.notice.set(null);
      this.error.set(null);
      if (!slug || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)) {
        this.loading.set(false);
        this.error.set('Selecciona una prenda del catálogo para preparar un borrador de reserva.');
        return;
      }
      this.load(slug);
    });
  }

  private restoreDraft(): void {
    if (!this.browser) return;
    try {
      const saved = JSON.parse(sessionStorage.getItem(DRAFT_KEY) ?? 'null') as unknown;
      if (isDraft(saved)) this.draft.set(saved);
      else sessionStorage.removeItem(DRAFT_KEY);
    } catch {
      this.draft.set(null);
    }
  }

  private load(slug: string): void {
    const current = ++this.requestVersion;
    this.loading.set(true);
    forkJoin({ product: this.catalog.get(slug), availability: this.catalog.availability(slug) })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: ({ product, availability }) => {
          if (current !== this.requestVersion) return;
          this.product.set(product);
          this.availability.set(availability);
          this.loading.set(false);
        },
        error: (error: unknown) => {
          if (current !== this.requestVersion) return;
          this.loading.set(false);
          this.error.set(error instanceof HttpErrorResponse && error.status === 0
            ? 'Sin conexión. Puedes consultar un borrador guardado, pero para elegir variantes necesitas consultar el servidor.'
            : error instanceof HttpErrorResponse && error.status === 404
              ? 'La prenda no está publicada o dejó de estar disponible.'
              : 'No se pudieron consultar las opciones de reserva. Revisa la conexión.');
        },
      });
  }

  selectable(): CatalogAvailabilityItem[] {
    return this.availability()?.items.filter(item => item.hay_existencias_fisicas) ?? [];
  }

  saveDraft(): void {
    this.error.set(null);
    this.notice.set(null);
    const product = this.product();
    if (!this.browser || !product || !this.availability() || this.loading()) return;
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.error.set('Selecciona una variante y sucursal, con cantidad entera entre 1 y 100.');
      return;
    }
    const { key, cantidad } = this.form.getRawValue();
    const item = this.selectable().find(row => key === `${row.sucursal_id}:${row.variante_id}`);
    if (!item || !Number.isSafeInteger(cantidad) || cantidad <= 0 || cantidad > 100) {
      this.error.set('La selección ya no es válida. Vuelve a consultar la disponibilidad.');
      return;
    }
    const draft: ReservationDraft = {
      id: crypto.randomUUID(),
      producto_id: product.id,
      producto_nombre: product.nombre,
      producto_slug: product.slug,
      sucursal_id: item.sucursal_id,
      sucursal_nombre: item.sucursal,
      variante_id: item.variante_id,
      talla: item.talla,
      color: item.color,
      cantidad,
      creado_en: new Date().toISOString(),
      estado: 'BORRADOR_LOCAL',
    };
    try {
      sessionStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
      this.draft.set(draft);
      this.notice.set('Borrador guardado en esta pestaña. No se envió una reserva ni se comprometió inventario.');
    } catch {
      this.error.set('El navegador no permitió guardar el borrador local.');
    }
  }

  clearDraft(): void {
    if (this.browser) {
      try { sessionStorage.removeItem(DRAFT_KEY); }
      catch { this.error.set('No se pudo borrar el almacenamiento de la pestaña.'); return; }
    }
    this.draft.set(null);
    this.notice.set('Borrador eliminado.');
  }
}
