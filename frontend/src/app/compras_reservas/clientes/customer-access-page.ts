import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { AbstractControl, FormControl, FormGroup, ReactiveFormsModule, ValidationErrors, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { Subject, finalize, forkJoin, takeUntil } from 'rxjs';
import { CustomerAuthService } from './customer-auth.service';
import { PublicStore } from './customer.models';
import { PASSWORD_POLICY_MESSAGE, validNewPassword } from './password-policy';

export function customerError(error: unknown, registration = false): string {
  const status = error instanceof HttpErrorResponse ? error.status : 0;
  if (status === 401 || status === 403) return 'El correo o la contraseña no son válidos, o la cuenta no está disponible en esta tienda.';
  if (status === 404) return 'Esta tienda no está disponible. Comprueba el enlace de acceso.';
  if (status === 409) return 'Este correo ya está registrado en esta tienda. Inicia sesión con esa cuenta.';
  if (status === 422) return registration ? 'Revisa tu nombre, correo y contraseña antes de registrar la cuenta.' : 'Revisa los datos de acceso.';
  return 'No pudimos conectar con la tienda. Revisa la conexión e inténtalo nuevamente.';
}

function customerEmail(control: AbstractControl): ValidationErrors | null {
  const value = String(control.value ?? '').trim();
  return value.length <= 254 && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value) ? null : { email: true };
}

@Component({
  selector: 'vn-customer-access', imports: [ReactiveFormsModule],
  templateUrl: './customer-access-page.html', styleUrl: './customer.css',
})
export class CustomerAccessPage {
  private readonly auth = inject(CustomerAuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  private readonly changed = new Subject<void>();
  private slug = '';
  private revision = 0;
  readonly store = signal<PublicStore | null>(null);
  readonly loading = signal(false);
  readonly loadError = signal<string | null>(null);
  readonly sending = signal(false);
  readonly registering = signal(false);
  readonly showPassword = signal(false);
  readonly error = signal<string | null>(null);
  readonly passwordPolicy = PASSWORD_POLICY_MESSAGE;
  readonly form = new FormGroup({
    nombre: new FormControl('', { nonNullable: true }),
    correo: new FormControl('', { nonNullable: true, validators: [Validators.required, customerEmail] }),
    password: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
    confirmacion: new FormControl('', { nonNullable: true }),
  });

  ngOnInit(): void {
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(params => {
      this.revision++; this.changed.next(); this.slug = params.get('tienda') ?? '';
      this.form.reset(); this.registering.set(false); this.error.set(null); this.sending.set(false); this.showPassword.set(false);
      this.auth.selectStore(this.slug);
      if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(this.slug)) { this.store.set(null); this.loadError.set('El enlace de tienda no es válido.'); return; }
      this.load();
    });
  }
  load(): void {
    if (this.loading() || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(this.slug)) return;
    this.store.set(null); this.loadError.set(null); this.loading.set(true);
    const revision = this.revision;
    forkJoin({ store: this.auth.store(this.slug), customer: this.auth.ensureSession(this.slug) })
      .pipe(takeUntil(this.changed), takeUntilDestroyed(this.destroyRef), finalize(() => this.loading.set(false))).subscribe({
        next: result => {
          if (revision !== this.revision) return;
          if (result.customer) { void this.router.navigate(['/tienda', this.slug, 'cuenta']); return; }
          this.store.set(result.store);
        },
        error: error => { if (revision === this.revision) this.loadError.set(customerError(error)); },
      });
  }
  mode(registering: boolean): void {
    if (this.sending()) return;
    this.registering.set(registering); this.error.set(null); this.form.controls.password.reset(); this.form.controls.confirmacion.reset(); this.showPassword.set(false);
  }
  fieldError(field: keyof typeof this.form.controls): string | null {
    const control = this.form.controls[field];
    if (!control.touched) return null;
    if (field === 'correo' && control.invalid) return 'Ingresa un correo electrónico válido.';
    if (field === 'password') {
      if (this.registering() && !validNewPassword(control.value)) return PASSWORD_POLICY_MESSAGE;
      if (!control.value) return 'Ingresa tu contraseña.';
    }
    if (field === 'nombre' && this.registering() && (Array.from(control.value.trim()).length < 3 || Array.from(control.value.trim()).length > 120)) return 'Escribe tu nombre, entre 3 y 120 caracteres.';
    if (field === 'confirmacion' && this.registering() && control.value !== this.form.controls.password.value) return 'Las contraseñas deben coincidir.';
    return null;
  }
  submit(): void {
    if (this.sending() || this.loading() || !this.store()) return;
    this.form.markAllAsTouched(); this.error.set(null);
    if (this.form.invalid || (Object.keys(this.form.controls) as (keyof typeof this.form.controls)[]).some(field => this.fieldError(field))) return;
    const value = this.form.getRawValue();
    const credentials = { correo: value.correo.trim().toLowerCase(), password: value.password };
    const registration = this.registering();
    const revision = this.revision;
    this.sending.set(true);
    const request = registration ? this.auth.register(this.slug, { ...credentials, nombre: value.nombre.trim() }) : this.auth.login(this.slug, credentials);
    request.pipe(takeUntil(this.changed), takeUntilDestroyed(this.destroyRef), finalize(() => this.sending.set(false))).subscribe({
      next: () => { if (revision === this.revision) { this.form.controls.password.reset(); this.form.controls.confirmacion.reset(); void this.router.navigate(['/tienda', this.slug, 'cuenta']); } },
      error: error => { if (revision === this.revision) this.error.set(customerError(error, registration)); },
    });
  }
}
