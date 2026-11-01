/** Misma política que app/image_url.py; casos compartidos en docs/contracts. */
export const IMAGE_URL_ERROR = 'Introduce una URL http o https completa, con host y puerto válidos, sin espacios ni credenciales.';

export function validImageUrl(input: string): boolean {
  const value = input.trim();
  const authority = /^https?:\/\/([^/?#]+)/i.exec(value)?.[1];
  if (value.length > 2048 || /[\s\\\u0000-\u001f\u007f]/u.test(value)
    || !authority || authority.includes('@') || authority.endsWith(':')) return false;
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) && Boolean(url.hostname) && !url.username && !url.password;
  } catch { return false; }
}
