import { Component, computed, input, signal } from '@angular/core';

@Component({
  selector: 'vn-catalog-image',
  template: `
    @if (source(); as src) {
      <img [src]="src" [alt]="name()" loading="lazy" decoding="async" (error)="failedUrl.set(src)" />
    } @else {
      <div class="catalog-image-empty" role="img" [attr.aria-label]="'Sin imagen de ' + name()">
        <svg viewBox="0 0 64 64" width="64" height="64" fill="none" stroke="currentColor" stroke-width="1.2" aria-hidden="true">
          <path d="m23 12 9 6 9-6 13 15-11 8v19H21V35l-11-8z" />
          <path d="M26 14c0 8 12 8 12 0" />
        </svg>
        <span>Imagen no disponible</span>
      </div>
    }
  `,
  styles: `
    :host { display: block; width: 100%; height: 100%; }
    img { display: block; width: 100%; height: 100%; object-fit: contain; }
    .catalog-image-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 18px; height: 100%; min-height: 180px; color: var(--vn-muted); }
    .catalog-image-empty span { font-size: 12px; }
    svg { max-width: 25%; }
  `,
})
export class CatalogImage {
  readonly url = input<string | null>(null);
  readonly name = input.required<string>();
  readonly failedUrl = signal<string | null>(null);
  readonly source = computed(() => {
    const url = this.url();
    return url && url !== this.failedUrl() ? url : null;
  });
}
