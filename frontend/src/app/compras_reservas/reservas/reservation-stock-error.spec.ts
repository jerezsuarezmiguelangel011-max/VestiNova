import { HttpErrorResponse } from '@angular/common/http';
import { shortageMessage } from './reservation-stock-error';

describe('CU10: saldo verificado ante un conflicto', () => {
  it('muestra disponibilidad por variante sin inventar existencias', () => {
    const cause = new HttpErrorResponse({
      status: 409, error: { detail: {
        mensaje: 'Sin stock', disponibilidades: [
          { variante_id: 12, disponible: 1, solicitado: 3 },
          { variante_id: 13, disponible: 0, solicitado: 2 },
        ],
      } },
    });
    expect(shortageMessage(cause)).toContain('variante #12, disponible 1, solicitado 3');
    expect(shortageMessage(cause)).toContain('variante #13, disponible 0, solicitado 2');
  });

  it('no atribuye saldos a un UUID reutilizado o datos mal formados', () => {
    expect(shortageMessage(new HttpErrorResponse({
      status: 409, error: { detail: 'El identificador ya pertenece a otra solicitud.' },
    }))).toBeNull();
    expect(shortageMessage(new HttpErrorResponse({
      status: 409, error: { detail: { disponibilidades: [
        { variante_id: -1, disponible: -5, solicitado: 1 },
      ] } },
    }))).toBeNull();
  });
});
