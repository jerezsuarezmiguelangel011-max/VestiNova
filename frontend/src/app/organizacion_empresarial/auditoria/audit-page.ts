import { DatePipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { Subject, catchError, defer, finalize, of, switchMap } from 'rxjs';
import { CompanyService } from '../empresa/company.service';
import { AuditEvent, AuditList, AuditQuery, AuditService } from './audit.service';

@Component({
  selector: 'vn-audit-page',
  imports: [DatePipe, ReactiveFormsModule],
  templateUrl: './audit-page.html',
  styleUrl: './audit-page.css',
})
export class AuditPage {
  readonly companies = inject(CompanyService);
  private readonly api = inject(AuditService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly requests = new Subject<AuditQuery>();
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly result = signal<AuditList>({ items: [], total: 0, limit: 25, offset: 0 });
  readonly filters = new FormGroup({
    q: new FormControl('', { nonNullable: true, validators: [Validators.maxLength(120)] }),
    accion: new FormControl('', { nonNullable: true }),
    entidad: new FormControl('', { nonNullable: true }),
    desde: new FormControl('', { nonNullable: true }),
    hasta: new FormControl('', { nonNullable: true }),
  });
  private currentQuery: AuditQuery = { limit: 25, offset: 0 };
  readonly actions = [
    ['usuario.creado', 'Alta de usuario'], ['usuario.actualizado', 'Edición de usuario'], ['usuario.acceso_actualizado', 'Cambio de acceso'],
    ['rol.creado', 'Creación de rol'], ['rol.actualizado', 'Edición de rol'], ['sucursal.creada', 'Alta de sucursal'],
    ['sucursal.actualizada', 'Edición de sucursal'], ['categoria.creada', 'Creación de categoría'], ['categoria.actualizada', 'Edición de categoría'],
    ['producto.creado', 'Alta de producto'], ['producto.actualizado', 'Edición de producto'], ['variante.creada', 'Alta de variante'],
    ['variante.actualizada', 'Edición de variante'],
  ] as const;

  constructor() {
    this.requests.pipe(
      switchMap(query => defer(() => {
        this.loading.set(true);
        this.error.set(null);
        return this.api.list(query).pipe(
          catchError(error => {
            this.error.set(error?.status === 403 ? 'Tu permiso de consulta cambió.' : 'No pudimos consultar la bitácora.');
            return of(null);
          }),
          finalize(() => this.loading.set(false)),
        );
      })),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe(result => { if (result) this.result.set(result); });

    let revision = this.companies.revision();
    this.companies.changes$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(next => {
      if (revision === next) return;
      revision = next;
      this.filters.reset();
      this.currentQuery = { limit: 25, offset: 0 };
      this.result.set({ items: [], total: 0, limit: 25, offset: 0 });
      if (this.companies.active()) this.reload();
    });
  }

  ngOnInit(): void { this.reload(); }

  search(): void {
    if (this.filters.invalid) { this.filters.markAllAsTouched(); return; }
    const value = this.filters.getRawValue();
    if (value.desde && value.hasta && value.desde > value.hasta) {
      this.error.set('La fecha inicial no puede ser posterior a la fecha final.');
      return;
    }
    this.currentQuery = {
      q: value.q.trim() || undefined,
      accion: value.accion || undefined,
      entidad: (value.entidad || undefined) as AuditQuery['entidad'],
      desde: value.desde || undefined,
      hasta: value.hasta || undefined,
      limit: 25,
      offset: 0,
    };
    this.reload();
  }

  clear(): void { this.filters.reset(); this.search(); }
  reload(): void { this.requests.next({ ...this.currentQuery }); }
  page(direction: -1 | 1): void {
    if (this.loading()) return;
    this.currentQuery = { ...this.currentQuery, offset: this.currentQuery.offset + direction * this.currentQuery.limit };
    this.reload();
  }
  first(): number { return this.result().total === 0 ? 0 : this.result().offset + 1; }
  last(): number { return Math.min(this.result().offset + this.result().items.length, this.result().total); }
  actionLabel(action: string): string { return this.actions.find(([code]) => code === action)?.[1] ?? action; }
  entityLabel(entity: string): string { return ({ usuario: 'Usuario', rol: 'Rol', sucursal: 'Sucursal', categoria: 'Categoría', producto: 'Producto', variante: 'Variante' } as Record<string, string>)[entity] ?? entity; }
  detailSummary(event: AuditEvent): string {
    const details = event.detalles ?? {};
    const fields = Array.isArray(details['campos']) ? (details['campos'] as string[]).join(', ') : '';
    const name = typeof details['nombre'] === 'string' ? details['nombre'] : '';
    const email = typeof details['correo'] === 'string' ? details['correo'] : '';
    const permissions = Array.isArray(details['permisos']) ? `Permisos: ${(details['permisos'] as string[]).join(', ')}` : '';
    return [name || email, fields ? `Campos: ${fields}` : '', permissions].filter(Boolean).join(' · ') || 'Cambio guardado';
  }
}
