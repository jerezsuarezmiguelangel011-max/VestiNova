import { Component, DestroyRef, OnDestroy, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe, KeyValuePipe } from '@angular/common';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize } from 'rxjs';
import { CompanyService } from '../organizacion_empresarial/empresa/company.service';
import { AnalyticsService, Report, ReportOptions, analyticsError, formFilters } from './analytics.service';

interface SpeechEngine { lang: string; interimResults: boolean; onresult: ((event: { results: { [key: number]: { [key: number]: { transcript: string } } } }) => void) | null; onerror: ((event: { error?: string }) => void) | null; onend: (() => void) | null; onaudiostart: (() => void) | null; onaudioend: (() => void) | null; onsoundstart: (() => void) | null; start(): void; stop(): void; abort(): void; }

const VOICE_ERRORS: Record<string, string> = {
  'not-allowed': 'No se autorizó el micrófono. Revisa el permiso del navegador y de Windows, o escribe la consulta.',
  'service-not-allowed': 'El navegador no permite el servicio de dictado. Prueba esta página en Google Chrome o escribe la consulta.',
  'audio-capture': 'No se pudo abrir el micrófono. Revisa el dispositivo de entrada y su acceso en Windows.',
  'no-speech': 'El servicio no detectó voz. Revisa el micrófono seleccionado y vuelve a hablar.',
  'network': 'El servicio de reconocimiento de voz no pudo conectarse. Revisa tu conexión o prueba otro navegador. Esta consulta todavía no se envió a Gemini.',
  'language-not-supported': 'El servicio de dictado de este navegador no admite el idioma configurado. Prueba esta página en Google Chrome o escribe la consulta.',
};
@Component({ selector: 'vn-ai-reports', imports: [ReactiveFormsModule, DatePipe, DecimalPipe, KeyValuePipe], templateUrl: './reports-page.html', styleUrl: './analytics.css' })
export class ReportsPage implements OnDestroy {
  readonly companies = inject(CompanyService);
  private readonly api = inject(AnalyticsService);
  private readonly destroyRef = inject(DestroyRef);
  readonly options = signal<ReportOptions | null>(null);
  readonly report = signal<Report | null>(null);
  readonly loading = signal(false);
  readonly exporting = signal(false);
  readonly error = signal<string | null>(null);
  readonly message = signal<string | null>(null);
  readonly listening = signal(false);
  readonly finishingVoice = signal(false);
  readonly audioActive = signal(false);
  readonly soundDetected = signal(false);
  private speech: SpeechEngine | undefined;
  private revision = 0;
  readonly examples = ['Ventas diarias del último mes', 'Prendas más vendidas este mes', 'Inventario actual por sucursal', 'Abastecimiento por proveedor este mes'];
  readonly form = new FormGroup({ consulta: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.minLength(5), Validators.maxLength(800)] }), desde: new FormControl('', { nonNullable: true }), hasta: new FormControl('', { nonNullable: true }), sucursal_id: new FormControl('', { nonNullable: true }), categoria_id: new FormControl('', { nonNullable: true }), producto_id: new FormControl('', { nonNullable: true }) });
  constructor() {
    this.companies.changes$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => { this.revision++; this.stopVoice(); this.report.set(null); this.options.set(null); this.loading.set(false); this.exporting.set(false); this.form.reset(); this.error.set('La empresa cambió. Actualiza este módulo para consultar el nuevo contexto.'); });
  }
  ngOnInit(): void { this.load(); }
  load(): void {
    this.error.set(null); this.report.set(null); const revision = ++this.revision;
    this.loading.set(true);
    this.api.options().pipe(takeUntilDestroyed(this.destroyRef), finalize(() => { if (revision === this.revision) this.loading.set(false); })).subscribe({ next: options => { if (revision === this.revision) this.options.set(options); }, error: error => { if (revision === this.revision) this.error.set(analyticsError(error)); } });
  }
  chooseExample(text: string): void { this.form.controls.consulta.setValue(text); if (text.startsWith('Inventario')) { this.form.controls.desde.setValue(''); this.form.controls.hasta.setValue(''); } }
  generate(): void {
    if (this.loading() || this.listening() || !this.options()?.profesional_vigente || !this.options()?.ia_configurada) return;
    if (this.form.invalid || !this.form.controls.consulta.value.trim()) { this.form.markAllAsTouched(); this.error.set('Escribe una consulta de 5 a 800 caracteres.'); return; }
    this.stopVoice(); this.error.set(null); this.message.set(null); this.report.set(null); this.loading.set(true); const revision = ++this.revision;
    const value = this.form.getRawValue();
    this.api.generate(value.consulta.trim(), formFilters(value)).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => { if (revision === this.revision) this.loading.set(false); })).subscribe({ next: result => { if (revision !== this.revision) return; this.report.set(result.reporte ?? null); this.message.set(result.mensaje ?? null); }, error: error => { if (revision === this.revision) this.error.set(analyticsError(error)); } });
  }
  export(formato: string): void {
    const report = this.report(); if (!report || this.exporting() || this.loading()) return;
    const revision = this.revision; this.exporting.set(true); this.error.set(null);
    this.api.export(report, formato).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => { if (revision === this.revision) this.exporting.set(false); })).subscribe({ next: blob => {
      if (revision !== this.revision) return;
      const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = `vestinova-${report.tipo}.${formato}`; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    }, error: error => { if (revision === this.revision) this.error.set(analyticsError(error)); } });
  }
  dictation(): void {
    if (this.listening()) {
      if (this.finishingVoice()) return;
      this.finishingVoice.set(true); this.message.set('Finalizando el dictado…');
      try { this.speech?.stop(); }
      catch { this.stopVoice(); this.message.set('No se pudo finalizar el dictado. Puedes escribir la consulta.'); }
      return;
    }
    if (this.loading()) return;
    const api = window as unknown as { SpeechRecognition?: new () => SpeechEngine; webkitSpeechRecognition?: new () => SpeechEngine };
    const Constructor = api.SpeechRecognition ?? api.webkitSpeechRecognition;
    if (!Constructor) { this.message.set('Este navegador no ofrece dictado. Puedes escribir la consulta.'); return; }
    this.stopVoice(); this.message.set(null);
    const revision = this.revision;
    let speech: SpeechEngine;
    try { speech = new Constructor(); }
    catch { this.message.set('Este navegador no pudo iniciar el servicio de dictado. Prueba esta página en Google Chrome o escribe la consulta.'); return; }
    this.speech = speech; speech.lang = 'es-BO'; speech.interimResults = false;
    const current = () => revision === this.revision && this.speech === speech;
    let recognized = false; let failed = false; let captured = false; let detected = false;
    speech.onaudiostart = () => { if (current()) { captured = true; this.audioActive.set(true); } };
    speech.onaudioend = () => { if (current()) this.audioActive.set(false); };
    speech.onsoundstart = () => { if (current()) { detected = true; this.soundDetected.set(true); } };
    speech.onresult = event => {
      if (!current()) return;
      const text = event.results?.[0]?.[0]?.transcript?.trim();
      if (!text) { this.message.set('No se reconoció una consulta. Puedes volver a dictarla o escribirla.'); return; }
      recognized = true;
      this.form.controls.consulta.setValue(text.slice(0, 800));
      this.message.set('Revisa y corrige el texto dictado antes de generar el reporte.');
    };
    speech.onerror = event => { if (current()) { failed = true; this.listening.set(false); this.finishingVoice.set(false); this.audioActive.set(false); this.message.set(VOICE_ERRORS[event.error ?? ''] ?? 'No se pudo usar el dictado. Revisa el permiso o escribe la consulta.'); } };
    speech.onend = () => {
      if (!current()) return;
      this.listening.set(false); this.finishingVoice.set(false); this.audioActive.set(false);
      if (!failed) this.message.set(recognized ? 'Revisa y corrige el texto dictado antes de generar el reporte.'
        : !captured ? 'El navegador terminó el dictado sin activar el micrófono. Revisa sus permisos o prueba esta página en Google Chrome.'
        : !detected ? 'Se abrió el micrófono, pero no se detectó sonido. Comprueba el dispositivo de entrada en Windows y vuelve a intentarlo.'
        : 'Se detectó sonido, pero el servicio de voz no devolvió una transcripción. Prueba esta página en Google Chrome o escribe la consulta.');
    };
    try { speech.start(); this.listening.set(true); } catch { this.stopVoice(); this.message.set('El dictado no está disponible. Utiliza texto.'); }
  }
  private stopVoice(): void { const speech = this.speech; this.speech = undefined; if (speech) { speech.onresult = null; speech.onerror = null; speech.onend = null; speech.onaudiostart = null; speech.onaudioend = null; speech.onsoundstart = null; try { speech.abort(); } catch { /* La captura ya puede haber terminado. */ } } this.listening.set(false); this.finishingVoice.set(false); this.audioActive.set(false); this.soundDetected.set(false); }
  ngOnDestroy(): void { this.revision++; this.stopVoice(); }
  metric(row: Record<string, string | number | boolean>): number { return Number(row['disponible'] ?? row['unidades'] ?? row['recibidas'] ?? 0); }
  label(row: Record<string, string | number | boolean>): string { return String(row['producto'] || row['fecha'] || row['proveedor'] || row['sucursal'] || 'Registro'); }
  width(row: Record<string, string | number | boolean>): number { return 100 * this.metric(row) / Math.max(1, ...(this.report()?.filas.map(value => this.metric(value)) ?? [])); }
}
