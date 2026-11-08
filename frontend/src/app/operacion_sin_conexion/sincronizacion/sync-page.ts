import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import type { SyncOperation } from './sync.models';
import { SyncService } from './sync.service';

@Component({
  selector: 'vn-sync-page',
  imports: [RouterLink, DatePipe],
  template: `
    <section class="sync-page" aria-labelledby="sync-title" [attr.aria-busy]="refreshing() || sync.processing() || sync.enqueuing()">
      <a class="sync-back" routerLink="/catalogo">← Volver al catálogo</a>
      <header class="sync-heading">
        <p class="sync-eyebrow">VestiNova · Soporte PWA · Catálogo público</p>
        <h1 id="sync-title">Sincronización</h1>
        <p>Registra una actualización pendiente y decide cuándo procesarla. Puedes registrar la operación sin conexión.</p>
      </header>

      <aside class="sync-scope" aria-label="Alcance de la sincronización">
        Este panel procesa actualizaciones pendientes del catálogo público. Las reservas CU10 se guardan y sincronizan desde «Preparar reserva» en la ficha de cada prenda. Las compras digitales no se confirman sin conexión.
      </aside>

      <div class="sync-actions">
        <button class="vn-button vn-button--primary sync-enqueue" type="button" (click)="enqueue()" [disabled]="sync.enqueuing()" [attr.aria-busy]="sync.enqueuing()">
          {{ sync.enqueuing() ? 'Registrando…' : 'Registrar actualización pendiente' }}
        </button>
        <button class="vn-button sync-process" type="button" (click)="process()" [disabled]="sync.processing()" [attr.aria-busy]="sync.processing()">
          {{ sync.processing() ? 'Procesando…' : 'Procesar pendientes' }}
        </button>
      </div>
      @if (error(); as message) { <p class="vn-alert vn-alert--error" role="alert">{{ message }}</p> }
      @if (sync.processing()) { <p class="sync-status" role="status">Procesando las operaciones pendientes. Espera el resultado de cada actualización.</p> }

      <section class="sync-history" aria-labelledby="sync-history-title">
        <h2 id="sync-history-title">Operaciones registradas</h2>
        @if (refreshing()) {
          <p class="sync-status" role="status">Cargando operaciones guardadas…</p>
        } @else if (sync.operations().length === 0 && !error()) {
          <div class="sync-empty" role="status"><h3>Todavía no hay operaciones</h3><p>Registra una actualización para dejarla pendiente en este navegador.</p></div>
        } @else {
          <ul class="sync-list">
            @for (operation of sync.operations(); track operation.id) {
              <li class="sync-operation" [attr.data-state]="operation.state" [attr.aria-busy]="operation.state === 'PROCESANDO'">
                <div class="sync-operation-heading"><h3>Actualización de catálogo</h3><span class="sync-state" [attr.data-state]="operation.state">{{ operation.state }}</span></div>
                <p class="sync-operation-id">Operación <span>{{ operation.id }}</span></p>
                <dl class="sync-dates">
                  <div><dt>Registrada</dt><dd><time [attr.datetime]="operation.createdAt">{{ operation.createdAt | date:'dd/MM/yyyy HH:mm':'-0400' }}</time></dd></div>
                  <div><dt>Último cambio</dt><dd><time [attr.datetime]="operation.updatedAt">{{ operation.updatedAt | date:'dd/MM/yyyy HH:mm':'-0400' }}</time></dd></div>
                  <div><dt>Copia local al registrar</dt><dd>@if (operation.expectedDownloadedAt; as downloaded) { <time [attr.datetime]="downloaded">{{ downloaded | date:'dd/MM/yyyy HH:mm':'-0400' }}</time> } @else { Sin copia previa }</dd></div>
                </dl>
                <p class="sync-timezone">Fechas en hora de Bolivia.</p>
                @if (operation.message) { <p class="sync-operation-message">{{ operation.message }}</p> }
                @switch (operation.state) {
                  @case ('PENDIENTE') { <p class="sync-operation-help">Se procesará cuando pulses «Procesar pendientes».</p> }
                  @case ('ERROR') {
                    <p class="sync-operation-help">Reintentar devuelve esta operación a pendiente. Después puedes procesarla cuando estés listo.</p>
                    <button class="vn-button sync-retry" type="button" (click)="retry(operation)" [disabled]="sync.processing()">Reintentar</button>
                  }
                  @case ('CONFLICTO') {
                    <p class="sync-conflict">Revisa la copia del catálogo y registra una nueva operación si quieres actualizarla. Este conflicto requiere una revisión antes de continuar.</p>
                    <a class="sync-back" routerLink="/catalogo">Revisar catálogo →</a>
                  }
                }
              </li>
            }
          </ul>
        }
      </section>
    </section>
  `,
  styles: `
    :host{display:block;min-width:0}.sync-page{color:var(--vn-text,#24332c)}.sync-back{display:inline-flex;align-items:center;min-height:44px;margin-bottom:22px;font-size:13px;text-underline-offset:4px}.sync-heading{max-width:760px;margin-bottom:26px}.sync-eyebrow{margin:0 0 13px;color:var(--vn-emerald,#116149);font-size:11px;font-weight:700;letter-spacing:.13em;text-transform:uppercase}.sync-heading h1{margin:0;color:var(--vn-coal,#202a25);font:400 clamp(34px,5vw,52px)/1.15 var(--vn-serif,Georgia);letter-spacing:-.04em}.sync-heading>p:last-child{margin:18px 0 0;color:var(--vn-muted,#59685f);line-height:1.8}.sync-scope{padding:17px 20px;border:1px solid #b6cdbd;border-radius:8px;background:var(--vn-soft,#eaf2ec);font-size:13px;line-height:1.8}.sync-actions{display:flex;flex-wrap:wrap;gap:12px;margin:24px 0}.sync-status{color:var(--vn-muted,#59685f);font-size:13px;line-height:1.8}.sync-history{margin-top:34px}.sync-history>h2{margin:0 0 20px;font:400 29px/1.2 var(--vn-serif,Georgia);letter-spacing:-.025em}.sync-list{display:grid;gap:18px;margin:0;padding:0;list-style:none}.sync-operation,.sync-empty{min-width:0;padding:24px;border:1px solid var(--vn-line,#d8ded5);border-radius:10px;background:var(--vn-white,#fff)}.sync-operation-heading{display:flex;flex-wrap:wrap;gap:14px;align-items:center;justify-content:space-between}.sync-operation h3,.sync-empty h3{margin:0;color:var(--vn-coal,#202a25);font:400 24px/1.25 var(--vn-serif,Georgia);letter-spacing:-.02em}.sync-state{display:inline-flex;align-items:center;min-height:30px;padding:5px 10px;border-radius:5px;background:#edf0e8;color:#42594a;font-size:10px;font-weight:700;letter-spacing:.06em;overflow-wrap:anywhere}.sync-state[data-state=SINCRONIZADA]{background:#e4f0e7;color:var(--vn-emerald,#116149)}.sync-state[data-state=ERROR]{background:#fbeaec;color:var(--vn-danger,#a32d36)}.sync-state[data-state=CONFLICTO]{background:#fbf1da;color:#785827}.sync-state[data-state=PROCESANDO]{background:#e7eef4;color:#375d77}.sync-operation-id{display:flex;flex-wrap:wrap;gap:7px;margin:14px 0 22px;color:var(--vn-muted,#59685f);font-size:11px}.sync-operation-id span{overflow-wrap:anywhere}.sync-dates{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;margin:0}.sync-dates dt{margin-bottom:7px;color:var(--vn-muted,#59685f);font-size:11px}.sync-dates dd{margin:0;font-size:13px;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}.sync-timezone{margin:12px 0 0;color:var(--vn-muted,#59685f);font-size:10px}.sync-operation-message,.sync-operation-help,.sync-conflict,.sync-empty p{margin:18px 0 0;color:var(--vn-muted,#59685f);font-size:13px;line-height:1.8}.sync-conflict{padding:14px 16px;border-left:3px solid #ae8741;background:#fffbef;color:#785827}.sync-operation>.vn-button{margin-top:16px}.sync-operation>.sync-back{margin:10px 0 0}:is(a,button):focus-visible{outline:3px solid var(--vn-emerald,#116149);outline-offset:3px}@media(max-width:650px){.sync-dates{grid-template-columns:1fr}.sync-operation,.sync-empty{padding:20px}.sync-actions{display:grid;grid-template-columns:1fr}.sync-actions button{justify-content:center}}
  `,
})
export class SyncPage {
  readonly sync = inject(SyncService);
  readonly refreshing = signal(true);
  private readonly actionError = signal<string | null>(null);
  readonly error = computed(() => this.sync.error() ?? this.actionError());

  ngOnInit(): void {
    void this.refresh();
  }

  private async refresh(): Promise<void> {
    try {
      await this.sync.refresh();
    } catch {
      this.actionError.set('No se pudieron consultar las operaciones guardadas en este navegador.');
    } finally {
      this.refreshing.set(false);
    }
  }

  async enqueue(): Promise<void> {
    if (this.sync.enqueuing()) return;
    this.actionError.set(null);
    try {
      await this.sync.enqueueCatalogUpdate();
    } catch {
      this.actionError.set('No se pudo registrar la actualización pendiente. Comprueba el almacenamiento del navegador.');
    }
  }

  async process(): Promise<void> {
    if (this.sync.processing()) return;
    this.actionError.set(null);
    try {
      await this.sync.processPending();
    } catch {
      this.actionError.set('No se pudieron procesar las operaciones. Revisa su estado antes de volver a intentarlo.');
    }
  }

  async retry(operation: SyncOperation): Promise<void> {
    if (operation.state !== 'ERROR' || this.sync.processing()) return;
    this.actionError.set(null);
    try {
      await this.sync.retry(operation.id);
    } catch {
      this.actionError.set('No se pudo dejar la operación pendiente. Su estado debe revisarse antes de continuar.');
    }
  }
}
