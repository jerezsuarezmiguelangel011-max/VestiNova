import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { Subject, finalize, forkJoin, takeUntil } from 'rxjs';
import { CompanyService } from '../../organizacion_empresarial/empresa/company.service';
import { CompanyRole, Permission, RoleInput, StaffService, staffError, validationFields } from './staff.service';

@Component({ selector: 'vn-staff-roles', imports: [ReactiveFormsModule], templateUrl: './staff-roles-page.html', styleUrl: './staff.css' })
export class StaffRolesPage {
  readonly companies = inject(CompanyService);
  private readonly api = inject(StaffService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly editorChanged = new Subject<void>();
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly contextChanged = signal(false);
  readonly roles = signal<CompanyRole[]>([]);
  readonly permissions = signal<Permission[]>([]);
  readonly error = signal<string | null>(null);
  readonly formError = signal<string | null>(null);
  readonly notice = signal<string | null>(null);
  readonly fields = signal<Record<string, string>>({});
  readonly editorOpen = signal(false);
  readonly editing = signal<CompanyRole | null>(null);
  readonly search = signal('');
  readonly visibleRoles = computed(() => this.roles().filter(role => `${role.nombre} ${role.descripcion}`.toLocaleLowerCase().includes(this.search().trim().toLocaleLowerCase())));
  readonly form = new FormGroup({
    nombre: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.minLength(3), Validators.maxLength(120), Validators.pattern(/\S/)] }),
    descripcion: new FormControl('', { nonNullable: true, validators: [Validators.maxLength(500)] }),
    permisos: new FormControl<string[]>([], { nonNullable: true }),
    activo: new FormControl(true, { nonNullable: true }),
  });
  constructor() {
    this.companies.changes$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.editorChanged.next(); this.contextChanged.set(true); this.roles.set([]); this.permissions.set([]); this.editorOpen.set(false); this.editing.set(null); this.form.reset(); this.form.disable(); this.error.set(null); this.notice.set(null); this.formError.set(null);
    });
  }
  ngOnInit(): void { this.load(); }
  load(): void {
    if (this.loading() || this.contextChanged() || !this.companies.canViewRoles() || !this.canLeave()) return;
    if (this.editorOpen()) { this.resetEditor(); this.editorOpen.set(false); }
    this.loading.set(true); this.error.set(null);
    forkJoin({ roles: this.api.roles(), permissions: this.api.permissions() }).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.loading.set(false))).subscribe({
      next: result => { this.roles.set(result.roles); this.permissions.set(result.permissions); }, error: error => this.error.set(staffError(error)),
    });
  }
  canLeave(): boolean { return this.contextChanged() || (!this.saving() && (!this.editorOpen() || !this.form.dirty || window.confirm('Tienes cambios sin guardar. ¿Quieres descartarlos?'))); }
  newRole(): void {
    if (!this.companies.canManageRoles() || !this.canLeave()) return;
    this.resetEditor(); this.editorOpen.set(true);
  }
  edit(role: CompanyRole): void {
    if (!this.canLeave()) return;
    const current = this.roles().find(item => item.id === role.id);
    if (!current) return;
    this.resetEditor(); this.editorOpen.set(true); this.editing.set(current);
    this.form.setValue({ nombre: current.nombre, descripcion: current.descripcion, permisos: [...current.permisos], activo: current.activo }); this.form.markAsPristine();
    if (current.protegido || !this.companies.canManageRoles()) this.form.disable();
  }
  close(): void { if (this.canLeave()) { this.resetEditor(); this.editorOpen.set(false); } }
  private resetEditor(): void { this.editorChanged.next(); this.editing.set(null); this.formError.set(null); this.fields.set({}); this.notice.set(null); this.form.enable(); this.form.reset({ nombre: '', descripcion: '', permisos: [], activo: true }); }
  togglePermission(code: string, checked: boolean): void {
    if (!this.companies.canManageRoles() || this.editing()?.protegido || this.saving() || !this.permissions().some(item => item.codigo === code)) return;
    const chosen = new Set(this.form.controls.permisos.value);
    if (checked) {
      const add = (key: string): void => { if (chosen.has(key)) return; chosen.add(key); this.permissions().find(item => item.codigo === key)?.requiere.forEach(add); };
      add(code);
    } else {
      chosen.delete(code);
      let removed: boolean;
      do { removed = false; for (const item of this.permissions()) if (chosen.has(item.codigo) && item.requiere.some(dependency => !chosen.has(dependency))) { chosen.delete(item.codigo); removed = true; } } while (removed);
    }
    this.form.controls.permisos.setValue([...chosen].sort()); this.form.controls.permisos.markAsDirty();
  }
  permissionName(code: string): string { return this.permissions().find(item => item.codigo === code)?.nombre ?? code; }
  dependencyNames(permission: Permission): string { return permission.requiere.map(code => this.permissionName(code)).join(', '); }
  fieldError(name: 'nombre' | 'descripcion' | 'permisos'): string | null {
    if (this.fields()[name]) return this.fields()[name];
    const field = this.form.controls[name];
    if (!field.touched || !field.errors) return null;
    return name === 'nombre' ? 'Escribe un nombre de 3 a 120 caracteres.' : 'Usa como máximo 500 caracteres.';
  }
  submit(): void {
    const current = this.editing();
    if (this.saving() || this.loading() || this.contextChanged() || current?.protegido || !this.companies.canManageRoles()) return;
    this.formError.set(null); this.fields.set({});
    if (this.form.invalid) { this.form.markAllAsTouched(); return; }
    const value = this.form.getRawValue();
    const input: RoleInput = { nombre: value.nombre.trim(), descripcion: value.descripcion.trim(), permisos: [...value.permisos].sort() };
    if (input.nombre.length < 3) { this.fields.set({ nombre: 'Escribe un nombre de 3 a 120 caracteres.' }); return; }
    if (input.permisos.some(code => !this.permissions().some(item => item.codigo === code))) { this.fields.set({ permisos: 'Selecciona permisos del catálogo de esta empresa.' }); return; }
    const changes: Partial<RoleInput> & { activo?: boolean } = {};
    if (current) {
      if (input.nombre !== current.nombre) changes.nombre = input.nombre;
      if (input.descripcion !== current.descripcion) changes.descripcion = input.descripcion;
      if (input.permisos.join() !== [...current.permisos].sort().join()) changes.permisos = input.permisos;
      if (value.activo !== current.activo) changes.activo = value.activo;
      if (!Object.keys(changes).length) { this.formError.set('No hay cambios para guardar.'); return; }
      if ((changes.permisos !== undefined || changes.activo !== undefined) && !window.confirm('Los cambios de permisos o estado se aplicarán a todas las personas con este rol y a sus sesiones. ¿Guardar los cambios?')) return;
    }
    const request = current ? this.api.updateRole(current.id, changes) : this.api.createRole(input);
    this.saving.set(true); this.form.disable();
    request.pipe(takeUntil(this.editorChanged), takeUntilDestroyed(this.destroyRef), finalize(() => this.saving.set(false))).subscribe({
      next: role => {
        this.roles.update(items => [...items.filter(item => item.id !== role.id), role].sort((a, b) => a.id - b.id));
        this.resetEditor(); this.editorOpen.set(false); this.notice.set(current ? 'Cambios guardados en el rol.' : 'Rol creado para esta empresa.');
        this.companies.refreshAccess().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({ error: error => this.error.set(staffError(error)) });
      }, error: error => { this.form.enable(); this.formError.set(staffError(error)); this.fields.set(validationFields(error)); },
    });
  }
  refreshAccess(): void {
    if (!this.canLeave()) return;
    this.companies.refreshAccess().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({ next: () => { this.resetEditor(); this.editorOpen.set(false); this.load(); }, error: error => this.error.set(staffError(error)) });
  }
}
