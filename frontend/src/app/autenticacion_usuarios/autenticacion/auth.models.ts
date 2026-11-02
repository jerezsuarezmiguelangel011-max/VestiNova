export interface Administrator {
  id: number;
  nombre: string;
  correo: string;
  rol: 'ADMINISTRADOR';
  es_superadministrador?: boolean;
}

export interface LoginCredentials { correo: string; password: string; }
export interface LoginResponse {
  access_token: string;
  token_type: 'bearer';
  expires_at: string;
  administrador: Administrator;
}
