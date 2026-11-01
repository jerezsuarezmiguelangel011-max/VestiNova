import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import { relative, resolve, sep } from 'node:path';
import { pathToFileURL } from 'node:url';
import { defaultBuildRoot } from './serve-pwa.mjs';

async function filesIn(directory) {
  const result = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const file = resolve(directory, entry.name);
    if (entry.isDirectory()) result.push(...await filesIn(file));
    else if (entry.isFile()) result.push(file);
  }
  return result;
}

export async function checkPwaBuild(buildRoot = defaultBuildRoot) {
  const worker = JSON.parse(await readFile(resolve(buildRoot, 'ngsw.json'), 'utf8'));
  const manifest = JSON.parse(await readFile(resolve(buildRoot, 'manifest.webmanifest'), 'utf8'));
  const index = await readFile(resolve(buildRoot, 'index.html'), 'utf8');
  assert.equal(worker.index, '/index.html');
  assert.deepEqual(worker.dataGroups ?? [], [], 'El service worker no debe guardar respuestas de la API.');
  assert.match(index, /<link\s+[^>]*rel="manifest"[^>]*>/);
  assert.equal(manifest.start_url, '/catalogo');
  assert.equal(manifest.display, 'standalone');

  const prefetched = new Set();
  for (const group of worker.assetGroups) {
    assert.deepEqual(group.patterns ?? [], [], 'No se deben guardar recursos remotos mediante patrones de URL.');
    for (const url of group.urls) {
      assert.ok(!/^\/(?:api|admin)(?:\/|$)/.test(url), `Recurso fuera del shell: ${url}`);
      if (group.installMode === 'prefetch') prefetched.add(url);
    }
  }
  for (const path of ['/index.html', '/manifest.webmanifest', '/icons/vn.svg', '/icons/vn-192.png', '/icons/vn-512.png']) {
    assert.ok(prefetched.has(path), `Falta precargar ${path}.`);
  }
  const workerScripts = new Set(['ngsw-worker.js', 'safety-worker.js', 'worker-basic.min.js']);
  for (const file of await filesIn(buildRoot)) {
    const path = relative(buildRoot, file).split(sep).join('/');
    if (/\.(?:m?js|css)$/.test(path) && !workerScripts.has(path)) {
      assert.ok(prefetched.has(`/${path}`), `Falta precargar el bundle /${path}.`);
    }
  }

  const allowsNavigation = path => {
    const pathname = new URL(path, 'http://127.0.0.1').pathname;
    return worker.navigationUrls.some(rule => rule.positive && new RegExp(rule.regex).test(pathname))
      && !worker.navigationUrls.some(rule => !rule.positive && new RegExp(rule.regex).test(pathname));
  };
  for (const path of ['/catalogo', '/catalogo/', '/catalogo/camisa-lino', '/catalogo/camisa-lino?q=lino']) {
    assert.ok(allowsNavigation(path), `La navegación pública debe funcionar: ${path}`);
  }
  for (const path of ['/', '/admin', '/admin/login', '/admin/productos', '/api', '/api/catalogo/productos', '/api/auth/me', '/api/admin/productos', '/catalogografia', '/otro/catalogo', '/catalogo/imagen.png', '/catalogo/a__b']) {
    assert.ok(!allowsNavigation(path), `El worker debe omitir esta navegación: ${path}`);
  }

  for (const size of [192, 512]) {
    const icon = manifest.icons.find(icon => icon.sizes === `${size}x${size}` && icon.type === 'image/png');
    assert.ok(icon, `Falta el icono PNG de ${size}px.`);
    const bytes = await readFile(resolve(buildRoot, `.${icon.src}`));
    assert.equal(bytes.subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
    assert.equal(bytes.readUInt32BE(16), size);
    assert.equal(bytes.readUInt32BE(20), size);
  }
  return { prefetchedAssets: prefetched.size, navigation: 'solo catálogo', apiCache: false };
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  checkPwaBuild().then(result => {
    console.log(`PWA verificada: ${result.prefetchedAssets} recursos precargados, navegación solo del catálogo y API sin caché.`);
  }).catch(error => {
    console.error(`No pasó la comprobación PWA: ${error.message}`);
    process.exitCode = 1;
  });
}
