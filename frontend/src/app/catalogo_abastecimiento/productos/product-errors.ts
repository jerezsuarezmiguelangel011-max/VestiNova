import { HttpErrorResponse } from '@angular/common/http';

/** Mensajes de dominio permitidos; no presentar trazas ni respuestas técnicas. */
export function productError(error: unknown): string {
  if (!(error instanceof HttpErrorResponse)) return 'No pudimos completar la operación. Intenta de nuevo.';
  if (error.status === 0) return 'No hay conexión con el servidor. Comprueba que la API esté en ejecución.';
  if (error.status === 401) return 'La sesión ha terminado. Vuelve a iniciar sesión.';
  if (error.status === 403) return 'Tu cuenta no tiene permiso para gestionar productos.';
  if (error.status === 404) return 'No encontramos este producto.';
  if (error.status === 409) return 'Ya existe un producto con ese identificador público. Elige otro.';
  if (error.status === 422) return 'Revisa los campos: el servidor no pudo validar los datos enviados.';
  return 'No pudimos completar la operación. Intenta de nuevo.';
}
