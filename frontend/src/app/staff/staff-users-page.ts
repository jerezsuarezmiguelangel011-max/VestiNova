import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { Subject, catchError, defer, finalize, forkJoin, of, switchMap, takeUntil } from 'rxjs';
import { CompanyService } from '../company/company.service';
import { AuthService } from '../auth/auth.service';
import { newPassword, PASSWORD_POLICY_MESSAGE } from '../customer/password-policy';
import { CompanyRole, StaffBranch, StaffChanges, StaffList, StaffQuery, StaffService, StaffUser, staffError, validationFields } from './staff.service';

@Component({ selector: 'vn-staff-users', imports: [ReactiveFormsModule], templateUrl: './staff-users-page.html', styleUrl: './staff.css' })
export class StaffUsersPage {
  readonly companies = inject(CompanyService);
  private readonly api = inject(StaffService);
  private readonly auth = inject(AuthService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly requests = new Subject<StaffQuery>();
  private readonly editorChanged = new Subject<void>();
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly editorLoading = signal(false);
  readonly contextChanged = signal(false);
  readonly error = signal<string | null>(null);
  readonly formError = signal<string | null>(null);
  readonly notice = signal<string | null>(null);
  readonly fields = signal<Record<string, string>>({});
  readonly result = signal<StaffList>({ items: [], total: 0, limit: 20, offset: 0 });
  readonly roles = signal<CompanyRole[]>([]);
  readonly branches = signal<StaffBranch[]>([]);
  readonly editorOpen = signal(false);
  readonly editing = signal<StaffUser | null>(null);
  readonly passwordMessage = PASSWORD_POLICY_MESSAGE;
  readonly filters = new FormGroup({ q: new FormControl('', { nonNullable: true, validators: [Validators.maxLength(120)] }), estado: new FormControl('todos', { nonNullable: true }), rol_id: new FormControl('', { nonNullable: true }) });
  readonly form = new FormGroup({
    nombre: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.minLength(3), Validators.maxLength(120), Validators.pattern(/\S/)] }),
    correo: new FormControl('', { nonNullable: true, validators: [Validators.required, Validators.email, Validators.maxLength(254)] }),
    password: new FormControl('', { nonNullable: true, validators: [newPassword] }),
    rol_id: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
    sucursal_ids: new FormControl<number[]>([], { nonNullable: true }),
    activo: new FormControl(true, { nonNullable: true }),
  });
  private query: StaffQuery = { q: '', estado: 'todos', limit: 20, offset: 0 };

  constructor() {
    this.requests.pipe(switchMap(query => defer(() => {
      this.loading.set(true); this.error.set(null);
      return this.api.users(query).pipe(catchError(error => { this.error.set(staffError(error)); return of(null); }), finalize(() => this.loading.set(false)));
    })), takeUntilDestroyed(this.destroyRef)).subscribe(result => { if (result) this.result.set(result); });
    this.companies.changes$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.editorChanged.next(); this.contextChanged.set(true); this.result.set({ items: [], total: 0, limit: 20, offset: 0 });
      this.roles.set([]); this.branches.set([]); this.editorOpen.set(false); this.editing.set(null); this.form.reset(); this.form.disable(); this.notice.set(null); this.error.set(null); this.formError.set(null);
    });
  }
  ngOnInit(): void { this.reload(); this.loadOptions(); }
  loadOptions(): void {
    if (!this.companies.canViewRoles()) return;
    const branches = this.companies.hasPermission('sucursales.consultar') ? this.api.branches() : of([] as StaffBranch[]);
    forkJoin({ roles: this.api.roles(), branches }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({ next: data => { this.roles.set(data.roles); this.branches.set(data.branches); }, error: error => this.error.set(staffError(error)) });
  }
  reload(): void { if (!this.contextChanged() && this.companies.canViewUsers()) this.requests.next({ ...this.query }); }
  search(): void {
    if (this.filters.invalid) { this.filters.markAllAsTouched(); return; }
    const value = this.filters.getRawValue();
    this.query = { q: value.q.trim(), estado: value.estado, rol_id: value.rol_id ? Number(value.rol_id) : undefined, limit: 20, offset: 0 }; this.reload();
  }
  page(direction: -1 | 1): void {
    const offset = this.query.offset + direction * this.query.limit;
    if (this.loading() || offset < 0 || offset >= this.result().total) return;
    this.query = { ...this.query, offset }; this.reload();
  }
  first(): number { return this.result().total ? this.result().offset + 1 : 0; }
  last(): number { return Math.min(this.result().offset + this.result().items.length, this.result().total); }
  canLeave(): boolean { return this.contextChanged() || (!this.saving() && (!this.editorOpen() || !this.form.dirty || window.confirm('Tienes cambios sin guardar. ¿Quieres descartarlos?'))); }
  newUser(): void {
    if (!this.companies.canCreateUsers() || !this.canLeave()) return;
    this.resetEditor(); this.editorOpen.set(true);
  }
  edit(user: StaffUser): void {
    if (!this.companies.canEditUsers() || !this.canLeave()) return;
    this.resetEditor(); this.editorLoading.set(true); this.editorOpen.set(true);
    this.api.user(user.id).pipe(takeUntil(this.editorChanged), takeUntilDestroyed(this.destroyRef), finalize(() => this.editorLoading.set(false))).subscribe({
      next: current => {
        this.editing.set(current); this.form.setValue({ nombre: current.nombre, correo: current.correo, password: '', rol_id: current.rol_id === null ? '' : String(current.rol_id), sucursal_ids: [...current.sucursal_ids], activo: current.activo });
        this.form.controls.correo.disable(); this.form.controls.password.disable(); this.form.markAsPristine(); this.form.markAsUntouched();
      }, error: error => { this.editorOpen.set(false); this.error.set(staffError(error)); },
    });
  }
  close(): void { if (this.canLeave()) { this.resetEditor(); this.editorOpen.set(false); } }
  private resetEditor(): void {
    this.editorChanged.next(); this.editing.set(null); this.formError.set(null); this.fields.set({}); this.notice.set(null);
    this.form.enable(); this.form.reset({ nombre: '', correo: '', password: '', rol_id: '', sucursal_ids: [], activo: true });
  }
  toggleBranch(id: number, checked: boolean): void {
    if (!this.branches().some(branch => branch.id === id) || this.saving()) return;
    const ids = this.form.controls.sucursal_ids;
    ids.setValue(checked ? [...new Set([...ids.value, id])] : ids.value.filter(value => value !== id)); ids.markAsDirty();
  }
  fieldError(name: 'nombre' | 'correo' | 'password' | 'rol_id' | 'sucursal_ids'): string | null {
    if (this.fields()[name]) return this.fields()[name];
    const field = this.form.controls[name];
    if (!field.touched || !field.errors) return null;
    if (name === 'password') return PASSWORD_POLICY_MESSAGE;
    if (field.hasError('email')) return 'Escribe un correo válido.';
    if (field.hasError('maxlength')) return name === 'correo' ? 'Usa como máximo 254 caracteres.' : 'Usa como máximo 120 caracteres.';
    if (field.hasError('minlength')) return 'Usa al menos 3 caracteres.';
    return name === 'rol_id' ? 'Selecciona un rol activo.' : 'Este campo es obligatorio.';
  }
  submit(): void {
    const current = this.editing();
    if (this.saving() || this.editorLoading() || this.contextChanged() || !(current ? this.companies.canEditUsers() : this.companies.canCreateUsers())) return;
    this.formError.set(null); this.fields.set({});
    if (this.form.invalid) { this.form.markAllAsTouched(); return; }
    const value = this.form.getRawValue(); const roleId = Number(value.rol_id);
    if (value.nombre.trim().length < 3) { this.fields.set({ nombre: 'Escribe un nombre de 3 a 120 caracteres.' }); return; }
    if (!this.roles().some(role => role.id === roleId && (role.activo || role.id === current?.rol_id))) { this.fields.set({ rol_id: 'Selecciona un rol activo de esta empresa.' }); return; }
    const changes: StaffChanges = {};
    if (current) {
      if (value.nombre.trim() !== current.nombre) changes.nombre = value.nombre.trim();
      if (value.activo !== current.activo) changes.activo = value.activo;
      if (roleId !== current.rol_id) changes.rol_id = roleId;
      if ([...value.sucursal_ids].sort().join() !== [...current.sucursal_ids].sort().join()) changes.sucursal_ids = value.sucursal_ids;
      if (!Object.keys(changes).length) { this.formError.set('No hay cambios para guardar.'); return; }
      if ((changes.activo !== undefined || changes.rol_id !== undefined || changes.sucursal_ids !== undefined) && !window.confirm('Vas a cambiar el acceso de esta persona a la empresa. Los nuevos permisos se aplicarán a sus sesiones. ¿Guardar los cambios?')) return;
    }
    const input = { nombre: value.nombre.trim(), correo: value.correo.trim(), password: value.password, rol_id: roleId, sucursal_ids: value.sucursal_ids, activo: value.activo };
    const request = current ? this.api.updateUser(current.id, changes) : this.api.createUser(input);
    this.saving.set(true); this.form.disable();
    request.pipe(takeUntil(this.editorChanged), takeUntilDestroyed(this.destroyRef), finalize(() => this.saving.set(false))).subscribe({
      next: () => {
        this.resetEditor(); this.editorOpen.set(false); this.notice.set(current ? 'Cambios guardados en la pertenencia.' : 'Persona agregada a la empresa.');
        if (current?.id === this.auth.user()?.id) this.companies.refreshAccess().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({ next: () => this.reload(), error: error => this.error.set(staffError(error)) });
        else this.reload();
      },
      error: error => { this.form.enable(); if (current) { this.form.controls.correo.disable(); this.form.controls.password.disable(); } this.formError.set(staffError(error)); this.fields.set(validationFields(error)); },
    });
  }
  refreshAccess(): void {
    if (!this.canLeave()) return;
    this.companies.refreshAccess().pipe(takeUntilDestroyed(this.destroyRef)).subscribe({ next: () => { this.resetEditor(); this.editorOpen.set(false); this.loadOptions(); this.reload(); }, error: error => this.error.set(staffError(error)) });
  }
}
