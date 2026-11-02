import { HttpErrorResponse } from '@angular/common/http';
import { DatePipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize, forkJoin } from 'rxjs';
import { AdministratorOption, PlatformCompany, PlatformCompanyService } from './company.service';

@Component({
  selector: 'vn-platform-companies-page',
  imports: [ReactiveFormsModule, DatePipe],
  templateUrl: './platform-companies-page.html',
  styleUrl: './platform.css',
})
export class PlatformCompaniesPage {
  private readonly api = inject(PlatformCompanyService);
  private readonly destroyRef = inject(DestroyRef);
  readonly companies = signal<PlatformCompany[]>([]);
  readonly administrators = signal<AdministratorOption[]>([]);
  readonly editing = signal<PlatformCompany | null>(null);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);
  readonly notice = signal<string | null>(null);
  readonly form = new FormGroup({
    nombre: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.minLength(3), Validators.maxLength(120)] }),
    slug: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.minLength(3), Validators.maxLength(100), Validators.pattern(/^[a-z0-9]+(?:-[a-z0-9]+)*$/)] }),
    administrador_id: new FormControl<number | null>(null),
    nit: new FormControl('', { nonNullable: true, validators: [Validators.maxLength(30)] }),
    correo_contacto: new FormControl('', { nonNullable: true, validators: [Validators.email, Validators.maxLength(254)] }),
    telefono_contacto: new FormControl('', { nonNullable: true, validators: [Validators.maxLength(40)] }),
  });
  readonly query = new FormControl('', { nonNullable: true, validators: [Validators.maxLength(120)] });

  ngOnInit(): void { this.load(); }

  load(): void {
    this.loading.set(true); this.error.set(null);
    forkJoin({ companies: this.api.companies(this.query.value), administrators: this.api.administrators() })
      .pipe(finalize(() => this.loading.set(false)), takeUntilDestroyed(this.destroyRef)).subscribe({
        next: data => { this.companies.set(data.companies); this.administrators.set(data.administrators); },
        error: error => this.error.set(this.message(error)),
      });
  }

  search(): void { if (this.query.invalid) { this.query.markAsTouched(); return; } this.load(); }

  reset(): void {
    this.editing.set(null);
    this.form.reset({ nombre: '', slug: '', administrador_id: null, nit: '', correo_contacto: '', telefono_contacto: '' });
    this.form.controls.slug.enable({ emitEvent: false });
    this.form.controls.administrador_id.enable({ emitEvent: false });
  }

  edit(company: PlatformCompany): void {
    this.editing.set(company);
    this.form.setValue({ nombre: company.nombre, slug: company.slug, administrador_id: null, nit: company.nit ?? '', correo_contacto: company.correo_contacto ?? '', telefono_contacto: company.telefono_contacto ?? '' });
    this.form.controls.slug.disable({ emitEvent: false });
    this.form.controls.administrador_id.disable({ emitEvent: false });
    this.form.markAsPristine(); this.error.set(null); this.notice.set(null);
  }

  submit(): void {
    if (this.saving()) return;
    this.error.set(null);
    if (this.form.invalid) { this.form.markAllAsTouched(); return; }
    const value = this.form.getRawValue();
    const current = this.editing();
    this.saving.set(true);
    const request = current
      ? this.api.update(current.id, { nombre: value.nombre.trim(), nit: value.nit.trim() || null, correo_contacto: value.correo_contacto.trim() || null, telefono_contacto: value.telefono_contacto.trim() || null })
      : value.administrador_id ? this.api.create({ nombre: value.nombre.trim(), slug: value.slug.trim(), administrador_id: value.administrador_id, nit: value.nit.trim() || null, correo_contacto: value.correo_contacto.trim() || null, telefono_contacto: value.telefono_contacto.trim() || null }) : null;
    if (!request) { this.saving.set(false); this.form.controls.administrador_id.markAsTouched(); this.error.set('Selecciona una cuenta administrativa activa.'); return; }
    request.pipe(finalize(() => this.saving.set(false)), takeUntilDestroyed(this.destroyRef)).subscribe({
      next: company => { this.notice.set(current ? `Se actualizaron los datos de ${company.nombre}.` : `Se registró ${company.nombre} con el plan Básico inicial.`); this.reset(); this.load(); },
      error: error => this.error.set(this.message(error)),
    });
  }

  toggle(company: PlatformCompany): void {
    if (this.saving()) return;
    this.saving.set(true); this.error.set(null);
    this.api.setActive(company.id, !company.activo).pipe(finalize(() => this.saving.set(false)), takeUntilDestroyed(this.destroyRef)).subscribe({
      next: updated => { this.notice.set(`${updated.nombre} quedó ${updated.activo ? 'habilitada' : 'suspendida'}.`); this.load(); },
      error: error => this.error.set(this.message(error)),
    });
  }

  private message(error: unknown): string {
    if (error instanceof HttpErrorResponse && typeof error.error?.detail === 'string') return error.error.detail;
    return 'No pudimos completar la operación. Revisa los datos de la empresa y vuelve a intentarlo.';
  }
}
