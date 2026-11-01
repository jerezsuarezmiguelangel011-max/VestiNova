export interface Variant {
  id: number;
  producto_id: number;
  talla: string;
  color: string;
  activo: boolean;
  creado_en: string;
}

export interface VariantInput { talla: string; color: string; activo: boolean; }
