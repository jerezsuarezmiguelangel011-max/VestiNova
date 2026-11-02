import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, ElementRef, ViewChild, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { CatalogDataService } from '../catalogo/catalog-data.service';
import { type CatalogProduct, type CatalogResult } from '../catalogo/catalog.models';

@Component({
  selector: 'vn-virtual-fitting-room-page',
  imports: [RouterLink],
  templateUrl: './virtual-fitting-room-page.html',
  styleUrl: './virtual-fitting-room-page.css',
})
export class VirtualFittingRoomPage {
  private readonly catalog = inject(CatalogDataService);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  @ViewChild('camera') private camera?: ElementRef<HTMLVideoElement>;
  private stream: MediaStream | null = null;
  private cameraAttempt = 0;

  readonly loading = signal(true);
  readonly product = signal<CatalogProduct | null>(null);
  readonly source = signal<'network' | 'local' | null>(null);
  readonly error = signal<string | null>(null);
  readonly cameraError = signal<string | null>(null);
  readonly cameraOn = signal(false);
  readonly cameraBusy = signal(false);
  readonly opacity = signal(0.5);

  constructor() {
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(params => {
      this.stopCamera();
      this.load(params.get('slug'));
    });
    this.destroyRef.onDestroy(() => this.stopCamera());
  }

  startCamera(): void {
    if (this.cameraBusy() || this.cameraOn()) return;
    this.cameraError.set(null);
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      this.cameraError.set('Este navegador no permite acceder a la cámara. Puedes consultar la prenda sin activarla.');
      return;
    }
    const video = this.camera?.nativeElement;
    if (!video) {
      this.cameraError.set('La vista de cámara todavía no está lista. Inténtalo nuevamente.');
      return;
    }
    const attempt = ++this.cameraAttempt;
    this.cameraBusy.set(true);
    navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: false }).then(stream => {
      if (attempt !== this.cameraAttempt) {
        stream.getTracks().forEach(track => track.stop());
        return;
      }
      this.stream = stream;
      video.srcObject = stream;
      this.cameraOn.set(true);
      return video.play();
    }).catch(() => {
      if (attempt === this.cameraAttempt) {
        this.stopCamera();
        this.cameraError.set('No se pudo activar la cámara. Revisa el permiso del navegador o continúa sin cámara.');
      }
    }).finally(() => { if (attempt === this.cameraAttempt) this.cameraBusy.set(false); });
  }

  stopCamera(): void {
    this.cameraAttempt += 1;
    this.stream?.getTracks().forEach(track => track.stop());
    this.stream = null;
    if (this.camera?.nativeElement) this.camera.nativeElement.srcObject = null;
    this.cameraOn.set(false);
    this.cameraBusy.set(false);
  }

  setOpacity(event: Event): void {
    this.opacity.set(Number((event.target as HTMLInputElement).value) / 100);
  }

  private load(slug: string | null): void {
    this.loading.set(true);
    this.error.set(null);
    this.product.set(null);
    this.source.set(null);
    if (!slug) {
      this.loading.set(false);
      this.error.set('No se indicó una prenda para mostrar.');
      return;
    }
    this.catalog.get(slug).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (result: CatalogResult<CatalogProduct>) => {
        this.product.set(result.data);
        this.source.set(result.source);
        this.loading.set(false);
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.error.set(error instanceof HttpErrorResponse && error.status === 404
          ? 'La prenda ya no está disponible en el catálogo.'
          : 'No pudimos cargar esta prenda. Vuelve al catálogo e intenta nuevamente.');
      },
    });
  }
}
