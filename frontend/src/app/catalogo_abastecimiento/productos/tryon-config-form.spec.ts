import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CompanyService } from '../../organizacion_empresarial/empresa/company.service';
import { TryOnConfigForm } from './tryon-config-form';
import { calibrationError, initialAnchors } from './garment-anchors';

describe('Foto de una variante para el vestidor', () => {
  let http: HttpTestingController;
  const variant = { id: 11, producto_id: 4, talla: 'M', color: 'AZUL', activo: true, creado_en: '2026-11-08T00:00:00Z' };
  const endpoint = '/api/admin/productos/4/variantes/11/vestidor';
  beforeEach(() => {
    TestBed.configureTestingModule({ imports: [TryOnConfigForm], providers: [provideHttpClient(), provideHttpClientTesting(),
      { provide: CompanyService, useValue: { canManage: () => true, scoped: (action: (company: { id: number }) => unknown) => action({ id: 7 }) } },
    ] });
    http = TestBed.inject(HttpTestingController);
    vi.stubGlobal('URL', class extends URL {
      static override createObjectURL() { return 'blob:recorte-local'; }
      static override revokeObjectURL() {}
    });
  });
  afterEach(() => { http.verify(); vi.unstubAllGlobals(); });
  function open() {
    const fixture = TestBed.createComponent(TryOnConfigForm);
    fixture.componentRef.setInput('productId', 4); fixture.componentRef.setInput('variant', variant); fixture.detectChanges();
    return fixture;
  }
  function choose(component: TryOnConfigForm, file: File) {
    component.selectFile({ target: { files: [file], value: 'selected' } } as unknown as Event);
  }
  it('exige un recurso y rechaza una foto JPG antes de enviarla', () => {
    const fixture = open(); http.expectOne(endpoint).flush({ configuracion: null });
    choose(fixture.componentInstance, new File(['photo'], 'prenda.jpg', { type: 'image/jpeg' }));
    expect(fixture.componentInstance.error()).toContain('PNG');
    fixture.componentInstance.save();
    expect(fixture.componentInstance.error()).toContain('Selecciona el PNG');
    http.expectNone(endpoint + '/recurso');
  });
  it('sube el PNG y después publica la configuración en la empresa seleccionada', () => {
    const fixture = open(); http.expectOne(endpoint).flush({ configuracion: null });
    const file = new File(['fixture png'], 'camisa.png', { type: 'image/png' });
    choose(fixture.componentInstance, file); fixture.componentInstance.save();
    const upload = http.expectOne(endpoint + '/recurso');
    expect(upload.request.headers.get('X-Empresa-Id')).toBe('7');
    expect(upload.request.headers.get('Content-Type')).toBe('image/png');
    expect(upload.request.body).toBe(file);
    const url = '/api/vestidor/recursos/empresas/7/' + 'a'.repeat(64) + '.png';
    upload.flush({ recurso_url: url, publicado: false });
    const publish = http.expectOne(endpoint);
    expect(publish.request.method).toBe('PUT'); expect(publish.request.body.recurso_url).toBe(url);
    publish.flush({ configuracion: { ...fixture.componentInstance.form.getRawValue(), recurso_url: url } });
    expect(fixture.componentInstance.notice()).toContain('guardada');
    expect(fixture.componentInstance.form.pristine).toBe(true);
  });
  it('cancela respuestas de otra variante y muestra la validación real del servidor', () => {
    const fixture = open(); const previous = http.expectOne(endpoint);
    fixture.componentRef.setInput('variant', { ...variant, id: 12, talla: 'L' }); fixture.detectChanges();
    expect(previous.cancelled).toBe(true);
    const next = '/api/admin/productos/4/variantes/12/vestidor'; http.expectOne(next).flush({ configuracion: null });
    choose(fixture.componentInstance, new File(['invalid'], 'fondo.png', { type: 'image/png' }));
    fixture.componentInstance.save();
    http.expectOne(next + '/recurso').flush({ detail: 'Usa un PNG con fondo transparente.' }, { status: 422, statusText: 'Unprocessable Entity' });
    expect(fixture.componentInstance.error()).toContain('fondo transparente');
    expect(fixture.componentInstance.busy()).toBe(false);
    http.expectNone(next);
  });
  it('consulta, edita y guarda puntos sin subir otra foto, y conserva la calibración al recargar', () => {
    const fixture = open(); const anchors = initialAnchors();
    const resource = '/api/vestidor/recursos/camisa-blanca.png';
    http.expectOne(endpoint).flush({ configuracion: { recurso_url: resource, anclajes: anchors } });
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelectorAll('.anchor-row').length).toBe(8);
    fixture.componentInstance.setCoordinate('hombro_izq','x',{ target: { value: '0.31' } } as unknown as Event);
    fixture.componentInstance.save();
    http.expectNone(endpoint+'/recurso');
    const publish = http.expectOne(endpoint);
    expect(publish.request.body.anclajes.hombro_izq.x).toBe(.31);
    expect(publish.request.headers.get('X-Empresa-Id')).toBe('7');
    publish.flush({ configuracion: publish.request.body });
    const updated = fixture.componentInstance.anchors();
    fixture.componentInstance.ngOnChanges();
    http.expectOne(endpoint).flush({ configuracion: { recurso_url: resource, anclajes: updated } });
    expect(fixture.componentInstance.anchors()?.hombro_izq.x).toBe(.31);
    choose(fixture.componentInstance,new File(['new photo'],'otra.png',{ type:'image/png' }));
    expect(fixture.componentInstance.anchors()).toBeNull();
  });
  it('mapea el puntero a la imagen y bloquea puntos cruzados o fuera de rango', () => {
    const fixture = open(); http.expectOne(endpoint).flush({ configuracion: { recurso_url: '/api/vestidor/recursos/camisa-blanca.png' } });
    const component = fixture.componentInstance; component.toggleCalibration();
    component.markPoint({ currentTarget: { getBoundingClientRect: () => ({ left:100,top:100,width:500,height:500 }) }, clientX:250,clientY:200 } as unknown as PointerEvent);
    expect(component.anchors()?.hombro_izq).toEqual({ x:.3,y:.2 });
    component.setCoordinate('hombro_der','x',{ target: { value:'0.2' } } as unknown as Event);
    component.save(); expect(component.error()).toContain('hombros'); http.expectNone(endpoint);
    const points = initialAnchors();
    expect(calibrationError(points)).toBeNull();
    expect(calibrationError({ ...points, manga_izq_media:points.hombro_izq })).toContain('Separa');
    expect(calibrationError({ ...points, cintura_izq:{ x:Infinity,y:1 } })).toContain('entre 0 y 1');
    expect(calibrationError({ ...points, manga_der_fin:{ x:.1,y:.8 } })).toContain('foto frontal');
  });
});
