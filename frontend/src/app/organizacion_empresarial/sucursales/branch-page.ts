import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize } from 'rxjs';
import { CompanyService } from '../empresa/company.service';
import { Branch, BranchInput, BranchService } from './branch.service';

@Component({
  selector: 'vn-branch-page',
  imports: [ReactiveFormsModule],
  templateUrl: './branch-page.html',
  styleUrl: './branch-page.css',
})
export class BranchPage {
  readonly companies = inject(CompanyService);
  private readonly api = inject(BranchService);
  private readonly destroyRef = inject(DestroyRef);
  readonly branches = signal<Branch[]>([]);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);
  readonly notice = signal<string | null>(null);
  readonly editing = signal<Branch | null>(null);
  readonly form = new FormGroup({
    codigo: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.maxLength(40), Validators.pattern(/^[a-zA-Z0-9][a-zA-Z0-9_-]*$/)] }),
    nombre: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.minLength(3), Validators.maxLength(120)] }),
    ciudad: new FormControl('', { nonNullable: true, validators: [Validators.maxLength(100)] }),
    ubicacion: new FormControl('', { nonNullable: true, validators: [Validators.maxLength(240)] }),
    contacto: new FormControl('', { nonNullable: true, validators: [Validators.maxLength(120)] }),
  });

  ngOnInit(): void {
    this.reload();
    this.companies.changes$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.branches.set([]);
      this.cancelEdit();
      this.notice.set(null);
      this.reload();
    });
  }

  reload(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.list().pipe(finalize(() => this.loading.set(false)), takeUntilDestroyed(this.destroyRef)).subscribe({
      next: rows => this.branches.set(rows),
      error: () => this.error.set('No pudimos cargar las sucursales de esta empresa.'),
    });
  }

  newBranch(): void {
    this.editing.set(null);
    this.form.enable({ emitEvent: false });
    this.form.reset({ codigo: '', nombre: '', ciudad: '', ubicacion: '', contacto: '' });
    this.notice.set(null);
    this.error.set(null);
  }

  edit(branch: Branch): void {
    this.editing.set(branch);
    this.form.enable({ emitEvent: false });
    this.form.setValue({ codigo: branch.codigo, nombre: branch.nombre, ciudad: branch.ciudad, ubicacion: branch.ubicacion, contacto: branch.contacto });
    this.form.controls.codigo.disable({ emitEvent: false });
    this.notice.set(null);
    this.error.set(null);
  }

  cancelEdit(): void {
    this.newBranch();
  }

  submit(): void {
    if (this.saving()) return;
    this.error.set(null);
    if (this.form.invalid) { this.form.markAllAsTouched(); return; }
    const value = this.form.getRawValue();
    const current = this.editing();
    this.saving.set(true);
    const request = current
      ? this.api.update(current.id, { nombre: value.nombre.trim(), ciudad: value.ciudad.trim(), ubicacion: value.ubicacion.trim(), contacto: value.contacto.trim() })
      : this.api.create({ codigo: value.codigo.trim().toUpperCase(), nombre: value.nombre.trim(), ciudad: value.ciudad.trim(), ubicacion: value.ubicacion.trim(), contacto: value.contacto.trim() } satisfies BranchInput);
    request.pipe(finalize(() => this.saving.set(false)), takeUntilDestroyed(this.destroyRef)).subscribe({
      next: branch => {
        this.notice.set(current ? `Se actualizaron los datos de ${branch.nombre}.` : `Se registró la sucursal ${branch.nombre}.`);
        this.newBranch();
        this.reload();
      },
      error: error => {
        this.error.set(error?.status === 409 ? 'Ya existe una sucursal con ese código.' : 'No pudimos guardar la sucursal. Revisa los datos e inténtalo nuevamente.');
      },
    });
  }

  toggleActive(branch: Branch): void {
    if (this.saving()) return;
    this.saving.set(true);
    this.error.set(null);
    this.api.update(branch.id, { activo: !branch.activo }).pipe(finalize(() => this.saving.set(false)), takeUntilDestroyed(this.destroyRef)).subscribe({
      next: updated => { this.notice.set(`${updated.nombre} quedó ${updated.activo ? 'activa' : 'inactiva'}.`); this.reload(); },
      error: () => this.error.set('No pudimos cambiar el estado de la sucursal.'),
    });
  }
}
