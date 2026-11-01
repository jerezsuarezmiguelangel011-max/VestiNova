import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { finalize } from 'rxjs';
import { AuthService } from './auth.service';

@Component({
  selector: 'vn-login-page',
  imports: [ReactiveFormsModule],
  templateUrl: './login-page.html',
  styleUrl: './login-page.css',
})
export class LoginPage {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private readonly reason = inject(ActivatedRoute).snapshot.queryParamMap.get('motivo');
  readonly notice = this.reason === 'sesion'
    ? 'Tu sesión terminó. Ingresa nuevamente para continuar.'
    : this.reason === 'conexion' ? 'No pudimos verificar la sesión. Comprueba que la API esté disponible.' : null;
  readonly sending = signal(false);
  readonly showPassword = signal(false);
  readonly error = signal<string | null>(null);
  readonly form = new FormGroup({
    correo: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.email, Validators.maxLength(254)] }),
    password: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
  });

  invalid(field: 'correo' | 'password'): boolean {
    const control = this.form.controls[field];
    return control.touched && control.invalid;
  }

  togglePassword(): void { this.showPassword.update(value => !value); }

  canRetrySession(): boolean { return this.auth.token() !== null; }

  retrySession(): void {
    if (this.sending()) return;
    this.sending.set(true); this.error.set(null);
    this.auth.ensureSession().pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.sending.set(false))).subscribe({
      next: user => {
        if (user) void this.router.navigateByUrl(user.es_superadministrador ? '/admin/plataforma' : '/admin/productos');
        else this.error.set('La sesión ya no está disponible. Inicia sesión para continuar.');
      },
      error: () => this.error.set('No pudimos verificar la sesión. Revisa la conexión y vuelve a intentarlo.'),
    });
  }

  submit(): void {
    if (this.sending()) return;
    this.form.markAllAsTouched();
    this.error.set(null);
    if (this.form.invalid) return;
    const credentials = this.form.getRawValue();
    this.sending.set(true);
    this.auth.login({ correo: credentials.correo.trim().toLowerCase(), password: credentials.password })
      .pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.sending.set(false)))
      .subscribe({
        next: user => void this.router.navigateByUrl(user.es_superadministrador ? '/admin/plataforma' : '/admin/productos'),
        error: (error: unknown) => {
          const status = error instanceof HttpErrorResponse ? error.status : 0;
          this.error.set(status === 401 || status === 403
            ? 'El correo o la contraseña no son válidos, o la cuenta está deshabilitada.'
            : status === 422 ? 'Revisa los datos de acceso e inténtalo nuevamente.'
            : 'No pudimos conectar con el sistema. Inténtalo nuevamente.');
        },
      });
  }
}
