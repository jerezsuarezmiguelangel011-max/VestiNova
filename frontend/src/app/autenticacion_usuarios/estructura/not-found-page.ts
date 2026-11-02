import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'vn-not-found', imports: [RouterLink],
  template: '<main class="not-found"><p class="vn-eyebrow">VestiNova · 404</p><h1 class="vn-title">Esta página no existe.</h1><p>Comprueba la dirección e inténtalo nuevamente.</p><a class="vn-button vn-button--primary" routerLink="/admin/productos">Ir a administración</a></main>',
  styles: '.not-found{max-width:680px;margin:12vh auto;padding:24px}.not-found p{color:var(--vn-muted)}.not-found a{margin-top:20px}',
})
export class NotFoundPage {}
