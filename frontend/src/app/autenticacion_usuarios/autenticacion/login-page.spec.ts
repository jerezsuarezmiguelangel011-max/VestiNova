import { HttpErrorResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap, provideRouter } from '@angular/router';
import { Subject } from 'rxjs';
import { AuthService } from './auth.service';
import { Administrator } from './auth.models';
import { LoginPage } from './login-page';

describe('Pantalla de acceso VestiNova', () => {
  async function setup() {
    const response = new Subject<Administrator>();
    const login = vi.fn(() => response);
    await TestBed.configureTestingModule({
      imports: [LoginPage],
      providers: [provideRouter([]), { provide: AuthService, useValue: { login, token: () => null } },
        { provide: ActivatedRoute, useValue: { snapshot: { queryParamMap: convertToParamMap({}) } } }],
    }).compileComponents();
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    const fixture = TestBed.createComponent(LoginPage);
    fixture.detectChanges();
    return { fixture, component: fixture.componentInstance, root: fixture.nativeElement as HTMLElement, response, login, navigate };
  }
  it('ofrece etiquetas visibles y no envía datos inválidos', async () => {
    const { component, fixture, root, login } = await setup();
    component.submit();
    fixture.detectChanges();
    expect(login).not.toHaveBeenCalled();
    expect(root.querySelector('label[for="login-email"]')?.textContent).toContain('Correo');
    expect(root.querySelector('#login-email')?.getAttribute('aria-invalid')).toBe('true');
    expect(root.querySelector('#login-password-error')?.textContent).toContain('contraseña');
  });
  it('conserva contraseña, evita doble envío y redirige solo al recibir una cuenta', async () => {
    const { component, fixture, root, response, login, navigate } = await setup();
    component.form.setValue({ correo: 'Admin@vestinova.test', password: ' Clave exacta ' });
    component.submit();
    component.submit();
    fixture.detectChanges();
    expect(login).toHaveBeenCalledExactlyOnceWith({ correo: 'admin@vestinova.test', password: ' Clave exacta ' });
    expect((root.querySelector('button[type="submit"]') as HTMLButtonElement).disabled).toBe(true);
    expect(navigate).not.toHaveBeenCalled();
    response.next({ id: 1, nombre: 'Ana', correo: 'admin@vestinova.test', rol: 'ADMINISTRADOR' });
    expect(navigate).toHaveBeenCalledWith('/admin/productos');
  });
  it('muestra un error controlado y permite reintentar', async () => {
    const { component, fixture, root, response } = await setup();
    component.form.setValue({ correo: 'admin@vestinova.test', password: 'incorrecta' });
    component.submit();
    response.error(new HttpErrorResponse({ status: 500, error: { detail: 'SQL privado' } }));
    fixture.detectChanges();
    expect(root.querySelector('[role="alert"]')?.textContent).toContain('No pudimos conectar');
    expect(root.textContent).not.toContain('SQL privado');
    expect(component.sending()).toBe(false);
  });
  it('mostrar la contraseña conserva su valor y anuncia el estado', async () => {
    const { component, fixture, root } = await setup();
    component.form.controls.password.setValue(' Clave exacta ');
    (root.querySelector('[aria-controls="login-password"]') as HTMLButtonElement).click();
    fixture.detectChanges();
    expect((root.querySelector('#login-password') as HTMLInputElement).type).toBe('text');
    expect(component.form.controls.password.value).toBe(' Clave exacta ');
    expect(root.querySelector('[aria-controls="login-password"]')?.getAttribute('aria-pressed')).toBe('true');
  });
  it('permite comprobar una contraseña heredada corta sin aplicar reglas de creación al login', async () => {
    const { component, login } = await setup();
    component.form.setValue({ correo: 'admin@vestinova.test', password: 'abc' });
    expect(component.form.controls.password.valid).toBe(true);
    component.submit();
    expect(login).toHaveBeenCalledExactlyOnceWith({ correo: 'admin@vestinova.test', password: 'abc' });
  });
});
