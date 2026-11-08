import type { Product, ProductList } from '../../catalogo_abastecimiento/productos/product.model';

// El contrato público comparte la respuesta de producto, sin operaciones administrativas.
export type CatalogProduct = Product;
export type CatalogList = ProductList;

export interface CatalogQuery {
  q?: string;
  categoria_id?: number;
  talla?: string;
  color?: string;
  temporada?: string;
  precio_min?: number;
  precio_max?: number;
  limit: number;
  offset: number;
}

export interface CatalogVariant {
  id: number;
  producto_slug: string;
  talla: string;
  color: string;
}

export interface CatalogBranch {
  id: number;
  nombre: string;
}

export interface CatalogSnapshot {
  schemaVersion: 1;
  scope: string;
  downloadedAt: string;
  total: number;
  products: CatalogProduct[];
  variants?: CatalogVariant[];
  branches?: CatalogBranch[];
}

export type CatalogSnapshotMetadata = Omit<CatalogSnapshot, 'products'>;

export interface CatalogResult<T> {
  data: T;
  source: 'network' | 'local';
  downloadedAt: string | null;
}

export class CatalogLocalError extends Error {
  constructor(
    readonly reason: 'no-copy' | 'missing-product' | 'storage' | 'unavailable-filter',
    readonly downloadedAt: string | null = null,
  ) {
    super(reason === 'no-copy'
      ? 'No hay un catálogo descargado en este navegador. Conéctate y pulsa «Descargar catálogo».'
      : reason === 'missing-product'
        ? 'Esta prenda no está incluida en la copia local. Conéctate para consultar el catálogo actualizado.'
        : reason === 'unavailable-filter'
          ? 'La copia local no incluye la información necesaria para filtrar por talla o color. Conéctate para hacer esta búsqueda.'
          : 'No se pudo acceder al catálogo local. Comprueba que el navegador permita el almacenamiento.');
    this.name = 'CatalogLocalError';
  }
}

/** Copia exclusivamente los campos públicos; nunca persiste cabeceras ni campos adicionales. */
export function copyPublicProduct(value: unknown): CatalogProduct {
  if (!value || typeof value !== 'object') throw new Error('Respuesta de catálogo inválida.');
  const product = value as Record<string, unknown>;
  const text = (name: string, max: number): string => {
    const field = product[name];
    if (typeof field !== 'string' || field.length > max) throw new Error('Respuesta de catálogo inválida.');
    return field;
  };
  const id = product['id'];
  const nombre = text('nombre', 120);
  const categoria_nombre = product['categoria_nombre'] === undefined ? 'General' : text('categoria_nombre', 100);
  const slug = text('slug', 140);
  const precio = text('precio', 11);
  const precioPromocional = product['precio_promocional'] === undefined ? null : product['precio_promocional'];
  const promocionNombre = product['promocion_nombre'] === undefined ? null : product['promocion_nombre'];
  const creado_en = text('creado_en', 64);
  const actualizado_en = text('actualizado_en', 64);
  if (!Number.isSafeInteger(id) || (id as number) < 1 || nombre.trim().length < 3 || slug.length < 3
    || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug) || !/^\d{1,8}\.\d{2}$/.test(precio) || /^0+\.00$/.test(precio)
    || product['moneda'] !== 'BOB' || product['activo'] !== true
    || !Number.isFinite(Date.parse(creado_en)) || !Number.isFinite(Date.parse(actualizado_en))) {
    throw new Error('Respuesta de catálogo inválida.');
  }
  const image = product['imagen_url'];
  const categoria_id = product['categoria_id'] === undefined ? null : product['categoria_id'];
  if (categoria_id !== null && (!Number.isSafeInteger(categoria_id) || (categoria_id as number) < 1)) {
    throw new Error('Respuesta de catálogo inválida.');
  }
  if (precioPromocional !== null && (typeof precioPromocional !== 'string' || !/^\d{1,8}\.\d{2}$/.test(precioPromocional) || Number(precioPromocional) >= Number(precio))) {
    throw new Error('Respuesta de catálogo inválida.');
  }
  if (promocionNombre !== null && (typeof promocionNombre !== 'string' || promocionNombre.length > 120 || !promocionNombre.trim())) {
    throw new Error('Respuesta de catálogo inválida.');
  }
  if (image !== null) {
    if (typeof image !== 'string' || image.length > 2048) throw new Error('Respuesta de catálogo inválida.');
    const url = new URL(image);
    if (!['http:', 'https:'].includes(url.protocol) || !url.hostname || url.username || url.password) {
      throw new Error('Respuesta de catálogo inválida.');
    }
  }
  return {
    id: id as number, categoria_id: categoria_id as number | null, categoria_nombre, nombre, slug, descripcion: text('descripcion', 3000),
    ...(product['material'] === undefined ? {} : { material: text('material', 120) }),
    ...(product['medidas'] === undefined ? {} : { medidas: text('medidas', 500) }),
    ...(product['temporada'] === undefined ? {} : { temporada: text('temporada', 60) }),
    precio,
    precio_promocional: precioPromocional as string | null, promocion_nombre: promocionNombre as string | null,
    moneda: 'BOB', imagen_url: image as string | null, activo: true, creado_en, actualizado_en,
  };
}
