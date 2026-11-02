import { Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { AuthService } from './auth.service';

@Component({
  selector: 'vn-platform-access', imports: [RouterLink], styleUrl: './account.css',
  template: `<section aria-labelledby="platform-title"><p class="vn-eyebrow">Plataforma VestiNova</p><h1 id="platform-title" class="vn-title">Acceso de superadministración</h1>
    <div class="vn-card account-details"><h2>{{ auth.user()?.nombre }}</h2><p>{{ auth.user()?.correo }}</p><p>Tu identidad de superadministrador SaaS ha sido validada por el servidor.</p>
    <p>Los permisos de plataforma y de cada empresa se validan por separado. Aquí puedes consultar tus empresas autorizadas.</p>
    <a routerLink="/admin/empresa" class="vn-button">Consultar mis empresas autorizadas</a></div></section>`,
})
export class PlatformAccessPage { readonly auth = inject(AuthService); }
