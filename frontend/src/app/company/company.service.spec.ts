import { HttpClient, HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Subject } from 'rxjs';
import { Company, COMPANY_KEY, CompanyService } from './company.service';

export const A: Company = { id: 1, nombre: 'Empresa A', slug: 'empresa-a', activo: true, rol: 'ADMINISTRADOR' };
export const B: Company = { id: 2, nombre: 'Empresa B', slug: 'empresa-b', activo: true, rol: 'OPERADOR' };

describe('Contexto empresarial validado por servidor', () => {
  let service: CompanyService;
  let http: HttpTestingController;
  beforeEach(() => {
    sessionStorage.clear();
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    http = TestBed.inject(HttpTestingController);
    service = TestBed.inject(CompanyService);
  });
  afterEach(() => { http.verify(); sessionStorage.clear(); });

  it('selecciona automáticamente la única empresa autorizada y comparte la consulta', () => {
    service.ensureForUser(10).subscribe();
    service.ensureForUser(10).subscribe();
    expect(service.active()).toBeNull();
    http.expectOne('/api/empresas').flush([A]);
    expect(service.active()).toEqual(A);
    expect(service.canManage()).toBe(true);
    expect(JSON.parse(sessionStorage.getItem(COMPANY_KEY)!)).toEqual({ usuario_id: 10, empresa_id: 1 });
    service.ensureForUser(10).subscribe();
    http.expectNone('/api/empresas');
  });

  it('no adivina una empresa con múltiples pertenencias y exige una opción de la lista', () => {
    service.ensureForUser(10).subscribe();
    http.expectOne('/api/empresas').flush([A, B]);
    expect(service.active()).toBeNull();
    expect(service.select(99)).toBe(false);
    expect(service.select(2)).toBe(true);
    expect(service.active()).toEqual(B);
    expect(service.canManage()).toBe(false);
  });

  it('restaura una elección solo después de comprobar que el servidor aún la autoriza', () => {
    sessionStorage.setItem(COMPANY_KEY, JSON.stringify({ usuario_id: 10, empresa_id: 2 }));
    service.ensureForUser(10).subscribe();
    expect(service.active()).toBeNull();
    http.expectOne('/api/empresas').flush([A, B]);
    expect(service.active()).toEqual(B);
  });

  it('descarta elecciones de otra cuenta y elecciones ya no autorizadas', () => {
    sessionStorage.setItem(COMPANY_KEY, JSON.stringify({ usuario_id: 11, empresa_id: 2 }));
    service.ensureForUser(10).subscribe();
    http.expectOne('/api/empresas').flush([A, B]);
    expect(service.active()).toBeNull();
    expect(sessionStorage.getItem(COMPANY_KEY)).toBeNull();
    service.select(2);
    service.refresh().subscribe();
    expect(service.active()).toBeNull();
    http.expectOne('/api/empresas').flush([]);
    expect(service.active()).toBeNull();
    expect(service.companies()).toEqual([]);
    expect(sessionStorage.getItem(COMPANY_KEY)).toBeNull();
  });

  it('mantiene un estado vacío real y permite reintentar ante errores sin inventar empresas', () => {
    const ready: boolean[] = [];
    service.ensureForUser(10).subscribe(value => ready.push(value));
    http.expectOne('/api/empresas').flush({ detail: 'SQL no debe mostrarse' }, { status: 503, statusText: 'Unavailable' });
    expect(ready).toEqual([false]);
    expect(service.error()).toContain('No pudimos consultar');
    expect(service.error()).not.toContain('SQL');
    expect(service.loading()).toBe(false);
    service.refresh().subscribe();
    http.expectOne('/api/empresas').flush([]);
    expect(service.error()).toBeNull();
    expect(service.companies()).toEqual([]);
    expect(service.active()).toBeNull();
  });

  it('no utiliza una respuesta de otra identidad después de cambiar de usuario', () => {
    service.ensureForUser(10).subscribe();
    const old = http.expectOne('/api/empresas');
    service.bindUser(11);
    expect(old.cancelled).toBe(true);
    service.ensureForUser(11).subscribe();
    http.expectOne('/api/empresas').flush([B]);
    expect(service.active()).toEqual(B);
  });

  it('cancela consultas y descarta emisiones tardías al cambiar empresa', () => {
    service.ensureForUser(10).subscribe();
    http.expectOne('/api/empresas').flush([A, B]);
    service.select(1);
    const result = vi.fn();
    const httpClient = TestBed.inject(HttpClient);
    service.scoped(() => httpClient.get('/api/admin/productos')).subscribe(result);
    const request = http.expectOne('/api/admin/productos');
    const late = new Subject<string>();
    service.scoped(() => late).subscribe(result);
    service.select(2);
    expect(request.cancelled).toBe(true);
    late.next('dato anterior');
    expect(result).not.toHaveBeenCalled();
    expect(service.active()?.id).toBe(2);
  });

  it('rechaza una operación sin empresa y limpia selección al cerrar sesión', () => {
    let status = 0;
    service.scoped(() => { throw new Error('No debe ejecutarse'); }).subscribe({ error: (error: HttpErrorResponse) => status = error.status });
    expect(status).toBe(403);
    service.ensureForUser(10).subscribe();
    http.expectOne('/api/empresas').flush([A]);
    service.clear();
    expect(service.active()).toBeNull();
    expect(service.companies()).toEqual([]);
    expect(service.canManage()).toBe(false);
    expect(sessionStorage.getItem(COMPANY_KEY)).toBeNull();
  });
});
