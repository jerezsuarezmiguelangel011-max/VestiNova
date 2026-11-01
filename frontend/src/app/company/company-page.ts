import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router } from '@angular/router';
import { AuthService } from '../auth/auth.service';
import { CompanyService } from './company.service';

@Component({
  selector: 'vn-company-page',
  templateUrl: './company-page.html',
  styleUrl: './company-page.css',
})
export class CompanyPage {
  readonly companies = inject(CompanyService);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  readonly candidate = signal('');
  readonly error = signal<string | null>(null);
  readonly navigating = signal(false);

  roleLabel(role: string): string {
    return ({ ADMINISTRADOR: 'Administración', ENCARGADO_SUCURSAL: 'Encargado de sucursal', CAJERO: 'Cajero', OPERADOR: 'Consulta' } as Record<string, string>)[role] ?? role;
  }

  ngOnInit(): void {
    const user = this.auth.user();
    if (!user || this.companies.error()) return;
    this.companies.ensureForUser(user.id).pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.candidate.set(String(this.companies.active()?.id ?? '')));
  }

  refresh(): void {
    this.error.set(null);
    this.companies.refresh().pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.candidate.set(String(this.companies.active()?.id ?? '')));
  }

  async continue(): Promise<void> {
    if (this.navigating()) return;
    this.error.set(null);
    if (!this.companies.select(Number(this.candidate()))) { this.error.set('Selecciona una empresa de la lista para continuar.'); return; }
    this.navigating.set(true);
    try {
      if (!await this.router.navigate([this.companies.canViewProducts() ? '/admin/productos' : '/admin/acceso'])) this.error.set('La empresa está seleccionada. Intenta continuar nuevamente.');
    } catch { this.error.set('No pudimos abrir tu espacio. Inténtalo nuevamente.'); }
    finally { this.navigating.set(false); }
  }
}
