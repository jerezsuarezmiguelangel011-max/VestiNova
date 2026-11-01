import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router } from '@angular/router';
import { finalize } from 'rxjs';
import { CustomerAuthService } from './customer-auth.service';

@Component({
  selector: 'vn-customer-account', styleUrl: './customer.css',
  template: `<main class="customer-shell"><div class="customer-brand"><span aria-hidden="true">VN</span> VestiNova</div>
    <section class="customer-card vn-card" aria-labelledby="account-title">
      @if (auth.customer(); as customer) {
        <p class="vn-eyebrow">{{ customer.empresa.nombre }}</p><h1 id="account-title" class="vn-title">Tu cuenta</h1>
        <dl><dt>Nombre</dt><dd>{{ customer.nombre }}</dd><dt>Correo electrónico</dt><dd>{{ customer.correo }}</dd><dt>Tipo de cuenta</dt><dd>Cliente de {{ customer.empresa.nombre }}</dd></dl>
        <p>Tu acceso pertenece a esta tienda.</p>
        @if (error(); as message) { <p class="vn-alert vn-alert--error" role="alert">{{ message }}</p> }
        <button type="button" class="vn-button vn-button--primary" [disabled]="closing()" (click)="logout()">{{ closing() ? 'Cerrando sesión…' : 'Cerrar sesión' }}</button>
      } @else { <h1 id="account-title" class="vn-title">Sesión no disponible</h1><p>Vuelve al enlace de acceso de tu tienda.</p> }
    </section></main>`,
})
export class CustomerAccountPage {
  readonly auth = inject(CustomerAuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  readonly closing = signal(false);
  readonly error = signal<string | null>(null);
  logout(): void {
    if (this.closing()) return;
    const slug = this.route.snapshot.paramMap.get('tienda')!;
    this.closing.set(true); this.error.set(null);
    this.auth.logout(slug).pipe(takeUntilDestroyed(this.destroyRef), finalize(() => this.closing.set(false))).subscribe({
      next: () => void this.router.navigate(['/tienda', slug, 'acceso']),
      error: () => this.error.set('No pudimos cerrar la sesión en el servidor. Reintenta para confirmar el cierre.'),
    });
  }
}
