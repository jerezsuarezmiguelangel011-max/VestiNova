import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CompanyService } from '../../organizacion_empresarial/empresa/company.service';

interface CompraEntrega {
  id: string;
  cliente_id: number;
  sucursal_id: number;
  importe_total: string;
  entrega: 'ENTREGADA' | 'PENDIENTE';
  entregada_en: string | null;
  items: Array<{ producto_id: number; nombre: string; cantidad: number }>;
}

@Component({
  selector: 'vn-purchase-deliveries',
  templateUrl: './purchase-deliveries-page.html',
  styles: [':host{display:block}.vn-delivery-card{border:1px solid #ccd0d8;border-radius:8px;margin:1rem 0;padding:1rem;overflow-wrap:anywhere}.vn-delivery-card label{display:block;margin:.6rem 0}.vn-delivery-card input[type=text]{display:block;padding:.5rem;max-width:100%;width:400px}'],
})
export class PurchaseDeliveriesPage {
  private readonly http = inject(HttpClient);
  private readonly company = inject(CompanyService);
  private readonly destroyRef = inject(DestroyRef);
  readonly purchases = signal<CompraEntrega[]>([]);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);
  readonly notice = signal<string | null>(null);

  constructor() { this.reload(); }

  private headers(): HttpHeaders {
    const selected = this.company.active();
    return new HttpHeaders(selected ? { 'X-Empresa-Id': String(selected.id), 'ngsw-bypass': 'true' } : {});
  }

  reload(): void {
    this.loading.set(true); this.error.set(null);
    this.http.get<{items:CompraEntrega[]}>('/api/admin/entregas-compras', { headers: this.headers() })
      .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: data => { this.purchases.set(data.items); this.loading.set(false); },
        error: () => { this.loading.set(false); this.error.set('No se pudieron consultar las compras confirmadas.'); },
      });
  }

  confirm(id: string, verified: boolean, proof: string): void {
    if (!verified || proof.trim().length < 3) {
      this.error.set('Verifica la identidad del cliente y registra la comprobación de entrega.'); return;
    }
    this.saving.set(true); this.error.set(null); this.notice.set(null);
    this.http.post<CompraEntrega>('/api/admin/entregas-compras/'+encodeURIComponent(id)+'/confirmar',
      { identidad_verificada: true, comprobacion: proof.trim() }, { headers: this.headers() })
      .pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
        next: value => {
          this.purchases.update(rows => rows.map(row => row.id === id ? value : row));
          this.saving.set(false); this.notice.set('Entrega confirmada. El cliente ya puede valorar las prendas.');
        },
        error: () => { this.saving.set(false); this.error.set('No pudimos confirmar la entrega. Verifica la sucursal y la compra.'); },
      });
  }
}
