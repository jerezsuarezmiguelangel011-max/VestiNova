import { Component, computed, input, signal } from '@angular/core';

@Component({
  selector: 'vn-catalog-image',
  template: `
    @if (source(); as src) {
      <img [src]="src" [alt]="name()" loading="lazy" decoding="async" (error)="failedUrl.set(src)" />
    } @else {
      <div class="catalog-image-empty" role="img" [attr.aria-label]="'Sin imagen de ' + name()">
        <span class="catalog-image-empty__brand" aria-hidden="true">VN</span>
        <div class="catalog-image-empty__symbol" aria-hidden="true">
          <svg viewBox="0 0 64 64" width="64" height="64" fill="none" stroke="currentColor" stroke-width="1.2">
            <path d="m23 12 9 6 9-6 13 15-11 8v19H21V35l-11-8z" />
            <path d="M26 14c0 8 12 8 12 0" />
          </svg>
        </div>
        <span>Imagen no disponible</span>
      </div>
    }
  `,
  styles: `
    :host { display: block; width: 100%; height: 100%; }
    img { display: block; width: 100%; height: 100%; object-fit: contain; }
    .catalog-image-empty { position: relative; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px; height: 100%; min-height: 180px; overflow: hidden; color: #587362; background: radial-gradient(circle at 47% 30%,#edf3e9 0,#dce7da 61%,#c4d3c5 100%); }
    .catalog-image-empty::before { content: ''; width: 73%; aspect-ratio: 1; position: absolute; border-radius: 50%; border: 1px solid #ffffff92; top: 12%; left: 13%; }
    .catalog-image-empty__brand { position: absolute; top: 16px; left: 19px; font: 600 18px Georgia,serif!important; color: #366a4c; letter-spacing: -.08em; }
    .catalog-image-empty__symbol { position: relative; display: grid; place-items: center; width: min(31%, 140px); aspect-ratio: 1; border-radius: 50%; background: #f9faf1a8; box-shadow: 0 16px 38px #2f503c16; }
    .catalog-image-empty__symbol svg { width: 53%; height: auto; color: #386a4b; }
    .catalog-image-empty > span:last-child { position: relative; font-size: 12px; letter-spacing: .03em; }
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
