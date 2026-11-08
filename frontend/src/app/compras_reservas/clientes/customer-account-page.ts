import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { CustomerAuthService } from './customer-auth.service';

@Component({
  selector: 'vn-customer-account', imports: [RouterLink], styleUrls: ['./customer.css', './customer-enhancements.css'],
  template: `
    <main class="customer-shell customer-page account-shell">
      <div class="customer-brand"><span aria-hidden="true">VN</span> VestiNova</div>
      <nav class="customer-breadcrumb" aria-label="Ruta de navegación">
        <a [routerLink]="['/tienda', slug]">Tienda</a><span aria-hidden="true">/</span><span>Mi cuenta</span>
      </nav>
      @if (auth.customer(); as customer) {
        <section class="account-hero" aria-labelledby="account-title">
          <div>
            <p class="account-eyebrow">MI ESPACIO EN {{ customer.empresa.nombre }}</p>
            <h1 id="account-title">Hola, {{ customer.nombre }}</h1>
            <p>Encuentra tus compras, opiniones, prendas guardadas y avisos en un mismo lugar.</p>
          </div>
          <div class="account-hero__monogram" aria-hidden="true">VN</div>
        </section>
        <section class="account-main" aria-label="Opciones de la cuenta">
          <div class="account-main__heading"><h2>¿Qué quieres hacer?</h2><p>Selecciona una opción para continuar.</p></div>
          <div class="account-shortcuts">
            <a class="account-shortcut" [routerLink]="['/tienda', slug, 'compras']">
              <span class="account-shortcut__icon" aria-hidden="true">▣</span>
              <strong>Mis compras</strong><span>Historial, comprobantes y seguimiento de entrega.</span>
              <span class="account-shortcut__arrow" aria-hidden="true">Ver mis compras →</span>
            </a>
            <a class="account-shortcut" [routerLink]="['/tienda', slug, 'valoraciones']">
              <span class="account-shortcut__icon" aria-hidden="true">★</span>
              <strong>Mis valoraciones</strong><span>Opina sobre las prendas que recibiste y edita tus reseñas.</span>
              <span class="account-shortcut__arrow" aria-hidden="true">Ver valoraciones →</span>
            </a>
            <a class="account-shortcut" [routerLink]="['/tienda', slug, 'deseos']">
              <span class="account-shortcut__icon" aria-hidden="true">♡</span>
              <strong>Mi lista de deseos</strong><span>Revisa tus prendas favoritas y su disponibilidad.</span>
              <span class="account-shortcut__arrow" aria-hidden="true">Ver mis deseos →</span>
            </a>
            <a class="account-shortcut" [routerLink]="['/tienda', slug, 'alertas']">
              <span class="account-shortcut__icon" aria-hidden="true">♧</span>
              <strong>Mis alertas</strong><span>Gestiona los avisos de reposición que solicitaste.</span>
              <span class="account-shortcut__arrow" aria-hidden="true">Gestionar alertas →</span>
            </a>
          </div>
        </section>
        <section class="account-profile" aria-labelledby="account-profile-heading">
          <div><p class="account-eyebrow">CUENTA DE CLIENTE</p><h2 id="account-profile-heading">Mis datos</h2></div>
          <dl class="account-profile__data">
            <div><dt>Nombre</dt><dd>{{ customer.nombre }}</dd></div>
            <div><dt>Correo electrónico</dt><dd>{{ customer.correo }}</dd></div>
            <div><dt>Tienda asociada</dt><dd>{{ customer.empresa.nombre }}</dd></div>
          </dl>
          <p class="account-profile__note">Por seguridad, tu sesión es exclusiva de esta tienda.</p>
        </section>
        <div class="account-footer-actions">
          <a class="vn-button" [routerLink]="['/tienda', slug, 'catalogo']">Seguir comprando</a>
          <button type="button" class="vn-button account-logout" [disabled]="closing()" (click)="logout()">{{ closing() ? 'Cerrando sesión…' : 'Cerrar sesión' }}</button>
        </div>
        @if (error(); as message) { <p class="vn-alert vn-alert--error" role="alert">{{ message }}</p> }
      } @else {
        <section class="customer-card vn-card"><h1 id="account-title">Sesión no disponible</h1>
          <p>Vuelve a iniciar sesión desde tu tienda.</p>
          <a class="vn-button vn-button--primary" [routerLink]="['/tienda', slug, 'acceso']">Ir a iniciar sesión</a>
        </section>
      }
    </main>`,
})
export class CustomerAccountPage {
  readonly auth = inject(CustomerAuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  readonly closing = signal(false);
  readonly error = signal<string | null>(null);
  readonly slug = this.route.snapshot.paramMap.get('tienda') ?? '';
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
