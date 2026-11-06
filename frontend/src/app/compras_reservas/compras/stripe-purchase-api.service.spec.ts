import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { authInterceptor } from '../../autenticacion_usuarios/autenticacion/auth.interceptor';
import { CustomerAuthService } from '../clientes/customer-auth.service';
import { StripePurchaseApiService } from './stripe-purchase-api.service';

describe('CU09: cliente Stripe Checkout por empresa', () => {
  let api: StripePurchaseApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [
      provideHttpClient(withInterceptors([authInterceptor])),
      provideHttpClientTesting(), provideRouter([]),
      { provide: CustomerAuthService, useValue: {
        token: (slug: string) => slug === 'demo-moda-andina' ? 'token-del-cliente' : null,
      } },
    ] });
    api = TestBed.inject(StripePurchaseApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('no usa sesión administrativa y envía cliente, variante y sucursal solo a su tienda', () => {
    const payload = {
      id: '123e4567-e89b-42d3-a456-426614174000', sucursal_id: 2, entrega: 'RETIRO' as const,
      direccion: '', items: [{ producto_id: 7, variante_id: 9, cantidad: 2 }],
    };
    api.checkout('demo-moda-andina', payload).subscribe();
    const request = http.expectOne('/api/tiendas/demo-moda-andina/compras/checkout');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual(payload);
    expect(request.request.headers.get('Authorization')).toBe('Bearer token-del-cliente');
    expect(request.request.headers.get('ngsw-bypass')).toBe('true');
    request.flush({ id: payload.id, estado: 'PAGO_PENDIENTE', moneda: 'BOB',
      total: '200.00', checkout_url: 'https://checkout.stripe.com/c/pay/test', detalle: null });

    api.status('demo-moda-andina', payload.id).subscribe();
    const status = http.expectOne('/api/tiendas/demo-moda-andina/compras/' + payload.id + '/estado');
    expect(status.request.headers.get('Authorization')).toBe('Bearer token-del-cliente');
    status.flush({ id: payload.id, estado: 'PAGO_PENDIENTE', moneda: 'BOB',
      total: '200.00', checkout_url: null, detalle: null });
  });

  it('sin sesión de otra empresa no reutiliza tokens ni habilita un cobro ajeno', () => {
    api.capabilities('demo-moda-urbana').subscribe();
    const request = http.expectOne('/api/tiendas/demo-moda-urbana/compras/capacidades');
    expect(request.request.headers.has('Authorization')).toBe(false);
    request.flush({ habilitado: false, pasarela: 'STRIPE_TEST', detail: 'Sin configurar' });
    expect(() => api.capabilities('../empresa-oculta')).toThrow();
  });
});
