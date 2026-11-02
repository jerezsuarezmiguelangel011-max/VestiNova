export interface PublicStore { slug: string; nombre: string; }
export interface Customer {
  id: number; nombre: string; correo: string; rol: 'CLIENTE'; empresa: PublicStore;
}
export interface CustomerCredentials { correo: string; password: string; }
export interface CustomerRegistration extends CustomerCredentials { nombre: string; }
export interface CustomerLoginResponse {
  access_token: string; token_type: 'bearer'; expires_at: string; cliente: Customer;
}
