export const anchorLabels = [
  ['hombro_izq', 'Hombro izquierdo'], ['hombro_der', 'Hombro derecho'],
  ['cintura_izq', 'Cintura izquierda'], ['cintura_der', 'Cintura derecha'],
  ['manga_izq_media', 'Mitad de manga izquierda'], ['manga_izq_fin', 'Extremo de manga izquierda'],
  ['manga_der_media', 'Mitad de manga derecha'], ['manga_der_fin', 'Extremo de manga derecha'],
] as const;
export type AnchorKey = typeof anchorLabels[number][0];
export interface ImagePoint { x: number; y: number; }
export type GarmentAnchors = Record<AnchorKey, ImagePoint> & { manga: 'CORTA' | 'LARGA' };
export function initialAnchors(): GarmentAnchors {
  const points = [[.32,.2],[.68,.2],[.35,.86],[.65,.86],[.22,.48],[.12,.85],[.78,.48],[.88,.85]];
  return { manga: 'LARGA', ...Object.fromEntries(anchorLabels.map(([key],i) => [key,{ x: points[i][0], y: points[i][1] }])) } as GarmentAnchors;
}
export function calibrationError(value: GarmentAnchors): string | null {
  if (!['CORTA','LARGA'].includes(value.manga) || anchorLabels.some(([key]) =>
    ![value[key]?.x,value[key]?.y].every(n => Number.isFinite(n) && n >= 0 && n <= 1))) return 'Cada punto debe tener coordenadas entre 0 y 1.';
  const {hombro_izq: l,hombro_der: r,cintura_izq: bl,cintura_der: br} = value;
  if (r.x-l.x < .15 || br.x-bl.x < .1 || Math.min(bl.y,br.y)-Math.max(l.y,r.y) < .2)
    return 'Marca los hombros separados y la cintura debajo, sin cruzar izquierda y derecha de la foto.';
  for (const [a,b,c] of [[l,value.manga_izq_media,value.manga_izq_fin],[r,value.manga_der_media,value.manga_der_fin]]) {
    if (Math.hypot(a.x-b.x,a.y-b.y)<.05 || Math.hypot(b.x-c.x,b.y-c.y)<.05) return 'Separa el hombro, la mitad y el extremo de cada manga.';
  }
  if ([value.manga_izq_media,value.manga_izq_fin].some(p => p.x>l.x+.04) || [value.manga_der_media,value.manga_der_fin].some(p => p.x<r.x-.04))
    return 'Utiliza una foto frontal con las mangas a los lados del cuerpo de la prenda.';
  return null;
}
