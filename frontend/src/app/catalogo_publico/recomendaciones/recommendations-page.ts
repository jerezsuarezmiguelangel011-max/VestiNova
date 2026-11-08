import { DatePipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { RecommendationsApi, type RecommendationResult } from './recommendations-api.service';
import { StorefrontContextService } from '../catalogo/storefront-context.service';
import { CustomerRecommendationsService } from './customer-recommendations.service';

@Component({
  selector: 'vn-recommendations',
  imports: [RouterLink, ReactiveFormsModule, DatePipe],
  template: `
    <section class="rec-page">
      <a [routerLink]="['/tienda', tienda(), 'catalogo']">← Volver al catálogo</a>
      <p class="rec-tag">VestiNova · CU19</p>
      <h1>Prendas recomendadas para ti</h1>
      <p>Explora sugerencias basadas en características de prendas y tus preferencias.
        Se utilizan exclusivamente productos publicados en esta tienda.</p>
      @if (signedIn()) {
        <section class="rec-consent" aria-label="Personalización opcional">
          <div>
            <strong>Recomendaciones según tus visitas</strong>
            <p>Es opcional. Si activas esta función, guardaremos en esta tienda
            qué prendas visitas para sugerir otras similares. Puedes desactivarla
            y borrar ese historial aquí mismo.</p>
          </div>
          <button type="button" (click)="togglePersonalization()"
                  [disabled]="settingsBusy()">
            {{ settingsBusy() ? 'Guardando…' :
               consent() ? 'Desactivar y borrar visitas' : 'Activar recomendaciones personales' }}
          </button>
        </section>
      } @else {
        <p class="rec-note">Para obtener sugerencias basadas en tus visitas,
        inicia sesión como cliente y activa voluntariamente la personalización.</p>
      }
      @if (settingsNotice(); as notice) { <p role="status" class="rec-note">{{ notice }}</p> }
      <form [formGroup]="form" (ngSubmit)="load()" class="rec-filters">
        <label>Talla preferida
          <input formControlName="talla" maxlength="30" placeholder="Ej.: M" />
        </label>
        <label>Color preferido
          <input formControlName="color" maxlength="60" placeholder="Ej.: Azul" />
        </label>
        <button type="submit" [disabled]="loading()">Actualizar recomendaciones</button>
      </form>
      @if (reference()) {
        <p role="status">Sugerencias relacionadas con la prenda consultada.
          <button type="button" class="rec-plain" (click)="clearReference()">Ver todas las sugerencias</button>
        </p>
      }
      @if (loading()) { <p role="status">Buscando prendas relacionadas…</p> }
      @if (error(); as message) { <p role="alert" class="rec-error">{{ message }}</p> }
      @if (result(); as data) {
        <p class="rec-note">Consulta en línea: {{ data.consultado_en | date:'dd/MM/yyyy HH:mm':'-0400' }}.
          {{ data.criterio === 'REGLAS_HISTORIAL_CONSENTIDO'
             ? 'Basadas en tus visitas aceptadas y en la similitud del catálogo.'
             : 'Recomendaciones por características del catálogo.' }} No utiliza un modelo predictivo.
          La disponibilidad es referencial y se vuelve a verificar antes de comprar.</p>
        <div class="rec-grid">
          @for (item of data.items; track item.producto_id) {
            <article class="rec-item">
              @if (item.imagen_url) { <img [src]="item.imagen_url" [alt]="item.nombre" loading="lazy" /> }
              <div class="rec-copy">
                <p class="rec-tag">{{ item.categoria }}</p>
                <h2>{{ item.nombre }}</h2>
                <p><strong>Bs {{ item.precio }}</strong></p>
                <p>{{ item.motivos.join(' · ') }}</p>
                @if (item.disponibilidad === 'DISPONIBLE_REFERENCIAL') {
                  <p class="rec-stock">Disponible según último saldo central</p>
                } @else if (item.disponibilidad === 'SIN_UNIDADES_CONOCIDAS') {
                  <p class="rec-stock">Sin unidades conocidas en la sucursal elegida</p>
                } @else {
                  <p class="rec-stock">Disponibilidad sin verificar por sucursal</p>
                }
                <a [routerLink]="['/tienda', tienda(), 'prenda', item.slug]">Ver prenda y variantes</a>
              </div>
            </article>
          } @empty {
            <p>No hay otras prendas publicadas que coincidan. Prueba con otra talla o color.</p>
          }
        </div>
      }
    </section>
  `,
  styles: `
    :host{display:block}.rec-page{max-width:1120px;margin:0 auto;padding:24px;color:#27392e}
    .rec-page h1{font:400 clamp(32px,5vw,46px) Georgia,serif;margin:14px 0}
    .rec-page>p{line-height:1.7}.rec-tag{color:#126c50;text-transform:uppercase;letter-spacing:.12em;font-size:11px;font-weight:700}
    .rec-filters{display:flex;flex-wrap:wrap;gap:14px;align-items:end;margin:22px 0;padding:18px;border:1px solid #d5e0d5;border-radius:12px;background:white}
    .rec-filters label{display:grid;gap:6px;font-size:13px}.rec-filters input{padding:10px;border:1px solid #a6b9a9;border-radius:5px;min-height:42px}
    .rec-filters button,.rec-plain{min-height:42px;padding:10px 15px;border-radius:6px;border:1px solid #176647;background:#e7f1e9;color:#164b37;cursor:pointer}
    .rec-plain{min-height:auto;padding:4px 8px}.rec-note{font-size:13px;color:#586a60}
    .rec-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:18px;margin-top:20px}
    .rec-item{border:1px solid #d6e3d7;border-radius:12px;overflow:hidden;background:#fff}
    .rec-item img{width:100%;height:210px;object-fit:cover}.rec-copy{padding:18px}
    .rec-copy h2{font:400 24px Georgia,serif;margin:8px 0}.rec-copy p{font-size:13px;line-height:1.55}
    .rec-copy a{display:inline-block;margin-top:10px;color:#126c50;font-weight:700}
    .rec-consent{display:flex;gap:16px;justify-content:space-between;align-items:center;flex-wrap:wrap;
      background:#edf5ed;border:1px solid #cbdacb;border-radius:10px;padding:16px;margin:18px 0}
    .rec-consent>div{flex:1;min-width:190px}.rec-consent strong{font-size:14px}
    .rec-consent p{font-size:12px;line-height:1.5;margin:6px 0 0}
    .rec-consent button{border:1px solid #206c4e;background:white;color:#174c37;border-radius:6px;padding:10px;cursor:pointer}
    .rec-stock{color:#657565}.rec-error{padding:13px;background:#fff0f0;color:#9e2636}
  `,
})
export class RecommendationsPage {
  private readonly api = inject(RecommendationsApi);
  private readonly personal = inject(CustomerRecommendationsService);
  readonly signedIn = signal(false);
  readonly consent = signal(false);
  readonly settingsBusy = signal(false);
  readonly settingsNotice = signal<string | null>(null);
  private readonly route = inject(ActivatedRoute);
  private readonly context = inject(StorefrontContextService);
  private readonly destroyRef = inject(DestroyRef);
  readonly tienda = signal('');
  readonly reference = signal<string | null>(null);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly result = signal<RecommendationResult | null>(null);
  readonly form = new FormGroup({
    talla: new FormControl('', { nonNullable: true }),
    color: new FormControl('', { nonNullable: true }),
  });
  private sequence = 0;

  constructor() {
    this.route.parent?.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(params => {
      const slug = params.get('tienda') ?? '';
      if (slug !== this.tienda()) {
        this.sequence++;
        this.tienda.set(slug);
        this.consent.set(false);
        this.signedIn.set(this.personal.activeSession(slug));
        this.settingsNotice.set(null);
        if (this.signedIn()) this.loadPreferences(slug);
        this.result.set(null);
        this.error.set(null);
        this.loading.set(false);
        this.load();
      }
    });
    this.route.queryParamMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(params => {
      const ref = params.get('producto_slug');
      this.reference.set(ref && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(ref) ? ref : null);
      this.load();
    });
  }
  private loadPreferences(tienda: string): void {
    this.personal.preferences(tienda).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: data => {
        if (this.tienda() !== tienda) return;
        this.consent.set(data.habilitado);
        this.load();
      },
      error: () => {
        if (this.tienda() === tienda) {
          this.signedIn.set(false);
          this.settingsNotice.set('No se pudo verificar la personalización de esta sesión.');
        }
      },
    });
  }
  togglePersonalization(): void {
    const tienda = this.tienda();
    if (!tienda || !this.signedIn() || this.settingsBusy()) return;
    const nextValue = !this.consent();
    this.settingsBusy.set(true);
    this.settingsNotice.set(null);
    this.personal.setPreferences(tienda, nextValue).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: result => {
        if (this.tienda() !== tienda) return;
        this.settingsBusy.set(false);
        this.consent.set(result.habilitado);
        this.settingsNotice.set(result.habilitado
          ? 'Personalización activada. A partir de ahora podrás recibir sugerencias según tus visitas.'
          : 'Personalización desactivada y visitas anteriores borradas.');
        this.reference.set(null);
        this.load();
      },
      error: () => {
        if (this.tienda() === tienda) {
          this.settingsBusy.set(false);
          this.settingsNotice.set('No se pudo cambiar la preferencia. Inténtalo nuevamente.');
        }
      },
    });
  }

  clearReference(): void {
    this.reference.set(null);
    this.load();
  }
  load(): void {
    const tienda = this.tienda();
    if (!tienda) return;
    const seq = ++this.sequence;
    this.loading.set(true);
    this.error.set(null);
    this.result.set(null);
    const filters = {
      talla: this.form.controls.talla.value.trim() || undefined,
      color: this.form.controls.color.value.trim() || undefined,
      sucursal_id: this.context.branch(),
    };
    const result$ = this.consent() && this.signedIn() && !this.reference()
      ? this.personal.recommendations(tienda, filters)
      : this.api.list(tienda, { ...filters, producto_slug: this.reference() ?? undefined });
    result$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: data => { if (seq === this.sequence) { this.result.set(data); this.loading.set(false); } },
      error: () => { if (seq === this.sequence) {
        this.error.set('No pudimos consultar recomendaciones. Comprueba la conexión y vuelve a intentar.');
        this.loading.set(false);
      } },
    });
  }
}
