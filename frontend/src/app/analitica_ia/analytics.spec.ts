import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { CompanyService } from '../organizacion_empresarial/empresa/company.service';
import { ReportsPage } from './reports-page';
import { DashboardPage } from './dashboard-page';

const company = (id: number) => ({ id, nombre: `Empresa ${id}`, slug: `empresa-${id}`, activo: true, rol: 'ADMINISTRADOR', permisos: ['reportes.ia.consultar', 'analitica.consultar'] });
const options = { profesional_vigente: true, ia_configurada: true, tipos: [], formatos: ['html','pdf','xlsx'], sucursales: [{id: 10, nombre: 'Sucursal propia'}], categorias: [], productos: [] };
const report = {tipo:'inventario', titulo:'Existencias actuales', empresa:{id:1,nombre:'Empresa 1'}, generado_en:'2026-11-07T12:00:00Z', filtros:{}, columnas:['producto','disponible'], filas:[{producto:'Camisa',disponible:5}], total_filas:1,truncado:false,totales:{disponible:5},notas:[],sin_datos:false};

class ControlledSpeech {
  static current: ControlledSpeech;
  lang = '';
  interimResults = false;
  onresult: ((event: {results: {transcript: string}[][]}) => void) | null = null;
  onerror: ((event: {error: string}) => void) | null = null;
  onend: (() => void) | null = null;
  onaudiostart: (() => void) | null = null;
  onaudioend: (() => void) | null = null;
  onsoundstart: (() => void) | null = null;
  start = vi.fn(); stop = vi.fn(); abort = vi.fn();
  constructor() { ControlledSpeech.current = this; }
  recognize(text: string): void { this.onresult?.({results:[[{transcript:text}]]}); }
}

describe('CU21 y CU22: pantallas con respuestas HTTP controladas', () => {
  let http: HttpTestingController;
  let companies: CompanyService;
  beforeEach(() => {
    sessionStorage.clear();
    TestBed.configureTestingModule({providers:[provideHttpClient(),provideHttpClientTesting()]});
    http = TestBed.inject(HttpTestingController); companies = TestBed.inject(CompanyService);
    companies.ensureForUser(10).subscribe(); http.expectOne('/api/empresas').flush([company(1),company(2)]); companies.select(1);
  });
  afterEach(() => { http.verify(); sessionStorage.clear(); vi.unstubAllGlobals(); });

  function reports() {
    const fixture = TestBed.createComponent(ReportsPage); fixture.detectChanges();
    const request = http.expectOne('/api/admin/reportes-ia/opciones'); expect(request.request.headers.get('X-Empresa-Id')).toBe('1'); request.flush(options); fixture.detectChanges();
    return fixture;
  }
  it('valida la consulta, muestra filas reales y reconsulta al exportar', () => {
    const fixture = reports(); const page = fixture.componentInstance;
    page.generate(); http.expectNone('/api/admin/reportes-ia/generar'); expect(page.error()).toContain('5 a 800');
    page.chooseExample('Inventario actual por sucursal'); page.generate();
    const request = http.expectOne('/api/admin/reportes-ia/generar'); expect(request.request.body.consulta).toContain('Inventario'); request.flush({estado:'generado',reporte:report}); fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Camisa'); expect(page.report()?.totales['disponible']).toBe(5);
    page.export('pdf'); const download = http.expectOne('/api/admin/reportes-ia/exportar'); expect(download.request.body).toEqual({tipo:'inventario', filtros:{}, formato:'pdf'});
    download.flush(new Blob(), {status:403,statusText:'Forbidden'}); expect(page.error()).toContain('acceso');
  });
  it('cancela consultas y elimina el resultado privado al cambiar de empresa', () => {
    const fixture = reports(); const page = fixture.componentInstance;
    page.chooseExample('Inventario actual'); page.generate(); const pending = http.expectOne('/api/admin/reportes-ia/generar');
    companies.select(2); expect(pending.cancelled).toBe(true); expect(page.report()).toBeNull(); expect(page.options()).toBeNull(); expect(page.loading()).toBe(false);
    fixture.detectChanges(); expect(fixture.nativeElement.textContent).not.toContain('Camisa');
  });
  it('identifica compras simuladas y retira el aviso al consultar datos sin esa marca', () => {
    const fixture=reports();const page=fixture.componentInstance;
    page.chooseExample('Prendas más vendidas');page.generate();
    http.expectOne('/api/admin/reportes-ia/generar').flush({estado:'generado',reporte:{...report,tipo:'prendas_vendidas',origen_datos:{demostracion:true,compras_demo:126,compras_operativas:0}}});fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('126 compras simuladas');
    page.chooseExample('Inventario actual');page.generate();http.expectOne('/api/admin/reportes-ia/generar').flush({estado:'generado',reporte:report});fixture.detectChanges();
    expect(fixture.nativeElement.textContent).not.toContain('126 compras simuladas');
  });
  it('explica aclaraciones sin inventar cifras y bloquea el plan Básico', () => {
    const fixture = reports(); const page = fixture.componentInstance;
    page.chooseExample('Consulta ambigua'); page.generate(); http.expectOne('/api/admin/reportes-ia/generar').flush({estado:'aclaracion',mensaje:'Aclara el período.'});
    expect(page.report()).toBeNull(); expect(page.message()).toContain('Aclara');
    page.options.set({...options,profesional_vigente:false}); page.generate(); http.expectNone('/api/admin/reportes-ia/generar');
    fixture.detectChanges(); expect(fixture.nativeElement.textContent).toContain('Profesional');
  });
  it('ofrece texto cuando el navegador no tiene reconocimiento de voz', () => {
    const fixture = reports(); fixture.componentInstance.dictation(); expect(fixture.componentInstance.message()).toContain('escribir');
    expect(fixture.componentInstance.listening()).toBe(false); http.expectNone('/api/admin/reportes-ia/generar');
  });
  it('dicta una consulta libre, permite corregirla y solo la envía al confirmar', () => {
    vi.stubGlobal('SpeechRecognition', ControlledSpeech);
    const fixture = reports(); const page = fixture.componentInstance;
    fixture.nativeElement.querySelector('#ai-dictation').click(); fixture.detectChanges();
    const speech = ControlledSpeech.current;
    expect(speech.start).toHaveBeenCalledOnce(); expect(speech.lang).toBe('es-BO');
    expect(fixture.nativeElement.querySelector('#ai-dictation svg')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('#ai-dictation').getAttribute('aria-pressed')).toBe('false');
    expect(fixture.nativeElement.textContent).toContain('Esperando que el navegador active');
    speech.onaudiostart?.(); fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('#ai-dictation').getAttribute('aria-pressed')).toBe('true');
    expect(fixture.nativeElement.textContent).toContain('Micrófono activado por el navegador');
    const dictated = 'Muéstrame las prendas más vendidas del 1 al 7 de noviembre de 2026 en Urbana Norte';
    speech.recognize(dictated); page.generate(); http.expectNone('/api/admin/reportes-ia/generar');
    page.dictation(); expect(speech.stop).toHaveBeenCalledOnce(); expect(speech.abort).not.toHaveBeenCalled();
    expect(page.finishingVoice()).toBe(true); page.generate(); http.expectNone('/api/admin/reportes-ia/generar');
    speech.onend?.();
    const corrected = dictated.replace('Urbana Norte','Urbana Centro');
    page.form.controls.consulta.setValue(corrected); page.generate();
    const request = http.expectOne('/api/admin/reportes-ia/generar');
    expect(request.request.body).toEqual({consulta:corrected, filtros:{}});
    expect(request.request.headers.get('X-Empresa-Id')).toBe('1');
    request.flush({estado:'aclaracion',mensaje:'Respuesta controlada; el dictado se envió al servidor.'});
  });
  it('explica el permiso de micrófono denegado y mantiene la entrada por texto', () => {
    vi.stubGlobal('SpeechRecognition', ControlledSpeech);
    const fixture = reports(); const page = fixture.componentInstance;
    page.dictation(); ControlledSpeech.current.onerror?.({error:'not-allowed'});
    expect(page.listening()).toBe(false); expect(page.message()).toContain('No se autorizó el micrófono');
    page.form.controls.consulta.setValue('Ventas de esta semana'); page.generate();
    http.expectOne('/api/admin/reportes-ia/generar').flush({estado:'aclaracion',mensaje:'Respuesta controlada'});
  });
  it('cancela el micrófono y rechaza la transcripción de otra empresa', () => {
    vi.stubGlobal('SpeechRecognition', ControlledSpeech);
    const fixture = reports(); const page = fixture.componentInstance;
    page.dictation(); const speech = ControlledSpeech.current; const late = speech.onresult;
    companies.select(2); expect(speech.abort).toHaveBeenCalledOnce();
    late?.({results:[[{transcript:'Consulta de la empresa anterior'}]]});
    expect(page.form.controls.consulta.value).toBe(''); expect(page.listening()).toBe(false);
    http.expectNone('/api/admin/reportes-ia/generar');
  });
  it('un dictado anterior no sobrescribe el nuevo aunque la empresa siga igual', () => {
    vi.stubGlobal('SpeechRecognition', ControlledSpeech);
    const fixture = reports(); const page = fixture.componentInstance;
    page.dictation(); const first = ControlledSpeech.current; const late = first.onresult;
    page.dictation(); first.onend?.(); page.dictation(); const second = ControlledSpeech.current;
    late?.({results:[[{transcript:'Resultado anterior'}]]});
    expect(page.form.controls.consulta.value).toBe('');
    second.recognize('Inventario de Urbana Centro');
    expect(page.form.controls.consulta.value).toBe('Inventario de Urbana Centro');
    http.expectNone('/api/admin/reportes-ia/generar');
  });
  it('no afirma que se abrió el micrófono cuando el navegador termina sin captura', () => {
    vi.stubGlobal('SpeechRecognition', ControlledSpeech);
    const fixture = reports(); const page = fixture.componentInstance;
    page.dictation(); ControlledSpeech.current.onend?.();
    expect(page.audioActive()).toBe(false); expect(page.message()).toContain('sin activar el micrófono');
    http.expectNone('/api/admin/reportes-ia/generar');
  });
  it('distingue un micrófono abierto sin sonido', () => {
    vi.stubGlobal('SpeechRecognition', ControlledSpeech);
    const fixture = reports(); const page = fixture.componentInstance;
    page.dictation(); const speech = ControlledSpeech.current;
    speech.onaudiostart?.(); speech.onaudioend?.(); speech.onend?.();
    expect(page.message()).toContain('no se detectó sonido'); expect(page.audioActive()).toBe(false);
  });
  it('distingue sonido capturado sin transcripción del proveedor de voz', () => {
    vi.stubGlobal('SpeechRecognition', ControlledSpeech);
    const fixture = reports(); const page = fixture.componentInstance;
    page.dictation(); const speech = ControlledSpeech.current;
    speech.onaudiostart?.(); speech.onsoundstart?.(); fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Se detecta sonido');
    speech.onend?.(); expect(page.message()).toContain('no devolvió una transcripción');
    http.expectNone('/api/admin/reportes-ia/generar');
  });
  it.each([
    ['network', 'no pudo conectarse'],
    ['audio-capture', 'No se pudo abrir el micrófono'],
    ['service-not-allowed', 'no permite el servicio de dictado'],
    ['language-not-supported', 'no admite el idioma'],
  ])('conserva la causa %s cuando después llega el evento de fin', (code, message) => {
    vi.stubGlobal('SpeechRecognition', ControlledSpeech);
    const fixture = reports(); const page = fixture.componentInstance;
    page.dictation(); const speech = ControlledSpeech.current;
    speech.onerror?.({error:code}); speech.onend?.();
    expect(page.message()).toContain(message); expect(page.listening()).toBe(false);
  });
  it('informa incompatibilidad si existe la API pero falla su constructor', () => {
    vi.stubGlobal('SpeechRecognition', class { constructor() { throw new Error('Controlado'); } });
    const fixture = reports(); const page = fixture.componentInstance;
    expect(() => page.dictation()).not.toThrow(); expect(page.message()).toContain('no pudo iniciar el servicio');
    expect(page.listening()).toBe(false);
  });
  it('no presenta ejemplos sintéticos como predicciones del negocio', () => {
    const fixture = TestBed.createComponent(DashboardPage); fixture.detectChanges(); http.expectOne('/api/admin/reportes-ia/opciones').flush(options);
    http.expectOne('/api/admin/dashboard-predictivo').flush({empresa:{id:1,nombre:'Empresa 1'},analisis:'ambos',estado:'datos_insuficientes',mensaje:'No hay datos empresariales suficientes.',filas:[],omitidos:[],filtros:{},modelo:{version:'v1',dataset:'prueba-sintetica',origen:'sintetico',entrenamiento:2400,evaluacion:600,division:'80/20',features:['unidades_7d'],metricas:{mae:2.3,rmse:2.9,r2:0.99,silhouette:0.61},ejemplos_sinteticos:[{entrada:[10],objetivo_sintetico:11,estimacion:10.5}],limitaciones:['Sin precisión validada sobre ventas reales.'],supervisado:{nombre:'Ridge',objetivo:'Demanda 7d'},no_supervisado:{nombre:'KMeans',grupos:3}}}); fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('datos empresariales suficientes'); expect(fixture.nativeElement.textContent).toContain('Así aprendieron los modelos'); expect(fixture.nativeElement.querySelector('.sample-badge').textContent).toContain('datos simulados'); expect(fixture.nativeElement.querySelector('.ai-bars')).toBeNull();
    companies.select(2); expect(fixture.componentInstance.data()).toBeNull();
  });
  it('identifica el historial demo y permite alternar demanda y grupos sin inventar grupos poblados',()=>{
    const fixture=TestBed.createComponent(DashboardPage);fixture.detectChanges();http.expectOne('/api/admin/reportes-ia/opciones').flush(options);
    const result={empresa:{id:1,nombre:'Empresa 1'},analisis:'ambos',estado:'resultados',mensaje:'Resultados experimentales',filas:[{producto_id:7,producto:'Prenda demo',unidades_reales_7d:8,unidades_reales_previas_7d:6,stock_disponible_real:12,precio_real_bob:'119.00',demanda_estimada_7d:10,agrupacion_estimada:'Rotación media'}],omitidos:[],filtros:{desde:'2026-10-10',hasta:'2026-11-08'},origen_datos:{demostracion:true,compras_demo:126,compras_operativas:0},modelo:{version:'v1',dataset:'simulado',origen:'sintetico',muestras:3000,entrenamiento:2400,evaluacion:600,division:'80/20',features:[],preprocesamiento:'Escalado',metricas:{mae:2.37,rmse:2.95,r2:0.99,silhouette:0.61},ejemplos_sinteticos:[],limitaciones:[],supervisado:{nombre:'Ridge',objetivo:'Demanda'},no_supervisado:{nombre:'KMeans',grupos:3,etiquetas:['Rotación baja','Rotación media','Rotación alta']}}};
    http.expectOne('/api/admin/dashboard-predictivo').flush(result);fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.demo-history').textContent).toContain('126 compras simuladas');
    expect(fixture.nativeElement.querySelector('.business-chart')).not.toBeNull();
    expect(fixture.componentInstance.groups().map(group=>group.count)).toEqual([0,1,0]);
    fixture.componentInstance.form.controls.analisis.setValue('agrupaciones');fixture.componentInstance.consult();
    http.expectOne('/api/admin/dashboard-predictivo').flush({...result,analisis:'agrupaciones',filas:result.filas.map(row=>({...row,demanda_estimada_7d:null}))});fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.business-chart')).toBeNull();expect(fixture.componentInstance.populatedGroups()).toBe(1);
    companies.select(2);expect(fixture.nativeElement.querySelector('.demo-history')).not.toBeNull();fixture.detectChanges();expect(fixture.nativeElement.querySelector('.demo-history')).toBeNull();
  });
});
