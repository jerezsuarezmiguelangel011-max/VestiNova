import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { finalize } from 'rxjs';
import { AuthService } from '../auth/auth.service';
import { CompanyService } from '../company/company.service';

@Component({
  selector: 'vn-admin-layout',
  imports: [RouterLink, RouterLinkActive, RouterOutlet],
  templateUrl: './admin-layout.html',
  styleUrl: './admin-layout.css',
})
export class AdminLayout {
  readonly auth = inject(AuthService);
  readonly companies = inject(CompanyService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  readonly signingOut = signal(false);
  readonly logoutError = signal<string | null>(null);

  logout(): void {
    if (this.signingOut()) return;
    this.signingOut.set(true);
    this.logoutError.set(null);
    this.auth.logout().pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.signingOut.set(false)))
      .subscribe({
        next: () => void this.router.navigateByUrl('/admin/login'),
        error: () => this.logoutError.set('No pudimos cerrar la sesión en el servidor. Inténtalo nuevamente.'),
      });
  }
}
