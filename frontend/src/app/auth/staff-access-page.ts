import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { Company, CompanyService } from '../company/company.service';
import { AuthService } from './auth.service';

interface StaffContext {
  empresa: Company;
  sucursales: { id: number; empresa_id: number; codigo: string; nombre: string; activo: boolean }[];
}

@Component({
  selector: 'vn-staff-access', imports: [RouterLink], styleUrl: './account.css',
  template: `
    <section aria-labelledby="staff-title">
      <p class="vn-eyebrow">Cuenta de personal</p><h1 id="staff-title" class="vn-title">Tu acceso autorizado</h1>
      @if (loading()) { <p role="status">Comprobando tu empresa y sucursales…</p> }
      @else if (error(); as message) { <p class="vn-alert vn-alert--error" role="alert">{{ message }}</p><button type="button" class="vn-button" (click)="load()">Reintentar</button> }
      @else if (context(); as access) {
        <div class="vn-card account-details"><h2>{{ access.empresa.nombre }}</h2><p><strong>{{ auth.user()?.nombre }}</strong><br>{{ auth.user()?.correo }}</p>
          <p>Rol: <strong>{{ roleLabel(access.empresa.rol) }}</strong></p>
          <h3>Sucursales autorizadas</h3>
          @if (access.sucursales.length) { <ul>@for (branch of access.sucursales; track branch.id) { <li><strong>{{ branch.nombre }}</strong> · {{ branch.codigo }}</li> }</ul> }
          @else { <p>No tienes sucursales activas asignadas. Solicita a la administración que revise tu acceso.</p> }
          <p>Consulta aquí la empresa y las sucursales a las que tienes acceso.</p>
          <a routerLink="/admin/empresa" class="vn-button">Cambiar empresa</a>
        </div>
      }
    </section>`,
})
export class StaffAccessPage {
  readonly auth = inject(AuthService);
  private readonly companies = inject(CompanyService);
  private readonly http = inject(HttpClient);
  private readonly destroyRef = inject(DestroyRef);
  readonly context = signal<StaffContext | null>(null);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  ngOnInit(): void {
    this.load();
    this.companies.changes$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.context.set(null); this.error.set('El contexto cambió. Selecciona una empresa para continuar.');
    });
  }
  roleLabel(role: string): string {
    return ({ ADMINISTRADOR: 'Administrador de empresa', ENCARGADO_SUCURSAL: 'Encargado de sucursal', CAJERO: 'Cajero', OPERADOR: 'Operador de consulta' } as Record<string, string>)[role] ?? role;
  }
  load(): void {
    if (this.loading()) return;
    this.context.set(null); this.error.set(null); this.loading.set(true);
    this.companies.scoped(company => this.http.get<StaffContext>('/api/auth/contexto', { headers: { 'X-Empresa-Id': String(company.id) } }))
      .pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.loading.set(false))).subscribe({
        next: result => this.context.set(result),
        error: error => this.error.set(error instanceof HttpErrorResponse && error.status === 403
          ? 'Tu pertenencia o acceso ya no está disponible. Actualiza tus empresas autorizadas.'
          : 'No pudimos comprobar tu acceso. Revisa la conexión e inténtalo nuevamente.'),
      });
  }
}
