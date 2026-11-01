export type SyncState = 'PENDIENTE' | 'PROCESANDO' | 'SINCRONIZADA' | 'CONFLICTO' | 'ERROR';

export interface SyncOperation {
  id: string;
  scope: 'public-catalog';
  type: 'ACTUALIZAR_CATALOGO';
  expectedDownloadedAt: string | null;
  state: SyncState;
  createdAt: string;
  updatedAt: string;
  message: string | null;
}
