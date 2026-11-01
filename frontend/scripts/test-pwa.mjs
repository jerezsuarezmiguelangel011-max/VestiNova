import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { access, mkdir, mkdtemp, readFile, realpath, rm, writeFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { isAbsolute, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { checkPwaBuild } from './check-pwa.mjs';
import { createPwaServer } from './serve-pwa.mjs';

// Prueba de navegador con API temporal: nunca utiliza el backend ni PostgreSQL.
const frontend = fileURLToPath(new URL('../', import.meta.url));
const runtime = resolve(frontend, '.angular');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const reports = [];
const passed = label => { reports.push(label); console.log(`OK: ${label}`); };

class DevTools {
  constructor(socket) {
    this.socket = socket;
    this.nextId = 0;
    this.pending = new Map();
    socket.addEventListener('message', event => {
      const message = JSON.parse(String(event.data));
      const waiting = this.pending.get(message.id);
      if (!waiting) return;
      this.pending.delete(message.id);
      clearTimeout(waiting.timer);
      if (message.error) waiting.reject(new Error(message.error.message));
      else waiting.resolve(message.result);
    });
    socket.addEventListener('close', () => {
      for (const waiting of this.pending.values()) {
        clearTimeout(waiting.timer);
        waiting.reject(new Error('Se cerró la conexión con el navegador.'));
      }
      this.pending.clear();
    });
  }

  send(method, params = {}, sessionId) {
    const id = ++this.nextId;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`Tiempo agotado: ${method}`));
      }, 15000);
      this.pending.set(id, { resolve, reject, timer });
      this.socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
    });
  }

  async evaluate(session, expression) {
    const result = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }, session);
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description ?? result.exceptionDetails.text);
    return result.result.value;
  }

  async until(session, expression, description, timeout = 20000) {
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      try { if (await this.evaluate(session, expression)) return; } catch { /* La navegación puede sustituir el contexto JS. */ }
      await pause(100);
    }
    const body = await this.evaluate(session, 'document.body?.innerText').catch(() => 'sin documento');
    throw new Error(`No se cumplió: ${description}. Pantalla: ${String(body).slice(0, 1400)}`);
  }
}

const readSnapshot = `new Promise((resolve, reject) => {
  const request = indexedDB.open('vestinova-public-catalog', 1);
  request.onerror = () => reject(new Error('IndexedDB inaccesible'));
  request.onsuccess = () => {
    const db = request.result;
    const tx = db.transaction('snapshots');
    let value;
    tx.objectStore('snapshots').get('public-catalog').onsuccess = event => { value = event.target.result; };
    tx.oncomplete = () => { db.close(); resolve(value ?? null); };
    tx.onabort = () => { db.close(); reject(new Error('Lectura abortada')); };
  };
})`;

const readOperations = `new Promise((resolve, reject) => {
  const request = indexedDB.open('vestinova-public-sync', 1);
  request.onerror = () => reject(new Error('Cola local inaccesible'));
  request.onsuccess = () => {
    const db = request.result;
    const tx = db.transaction('operations');
    let value;
    tx.objectStore('operations').getAll().onsuccess = event => { value = event.target.result; };
    tx.oncomplete = () => { db.close(); resolve(value); };
    tx.onabort = () => { db.close(); reject(new Error('Lectura de cola abortada')); };
  };
})`;

async function listen(server) {
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  return `http://127.0.0.1:${server.address().port}`;
}

async function run() {
  await checkPwaBuild();
  const browserPath = process.env['VESTINOVA_BROWSER'] ?? 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
  try { await access(browserPath); } catch { throw new Error('No se encontró Edge. Define VESTINOVA_BROWSER con la ruta de un navegador Chromium instalado.'); }
  await mkdir(runtime, { recursive: true });
  const profile = await mkdtemp(resolve(runtime, 'cu14-browser-'));
  let browser;
  let tools;
  let preview;
  let api;
  try {
    const date = '2026-10-25T12:00:00Z';
    const products = Array.from({ length: 121 }, (_, index) => ({
      id: 121 - index, slug: `prenda-prueba-${121 - index}`, nombre: `Prenda de prueba ${121 - index}`,
      descripcion: 'Datos exclusivos de la prueba automatizada.', precio: '149.90', moneda: 'BOB',
      imagen_url: null, activo: true, creado_en: date, actualizado_en: date,
      access_token: 'token-ficticio-que-no-debe-guardarse',
    }));
    let failUpdate = false;
    let denied = false;
    let leakedAuthorization = false;
    let privateRequests = 0;
    let capabilitiesRequests = 0;
    let purchasePosts = 0;
    const downloadOffsets = [];
    api = createServer((request, response) => {
      const url = new URL(request.url, 'http://127.0.0.1');
      if (/^\/api\/(?:auth|admin)(?:\/|$)/.test(url.pathname)) privateRequests++;
      if (request.headers.authorization) leakedAuthorization = true;
      if (url.pathname === '/api/compras' && request.method === 'POST') purchasePosts++;
      let status = 200;
      let result;
      if (denied) { status = 403; result = { detail: 'Permiso denegado para la prueba.' }; }
      else if (url.pathname === '/api/compras/capacidades') {
        capabilitiesRequests++;
        result = { habilitado: false, detail: 'Faltan los adaptadores autorizados para confirmar compras.' };
      }
      else if (url.pathname === '/api/catalogo/productos') {
        const limit = Number(url.searchParams.get('limit') ?? 20);
        const offset = Number(url.searchParams.get('offset') ?? 0);
        const q = (url.searchParams.get('q') ?? '').trim().toLowerCase();
        if (limit === 100) downloadOffsets.push(offset);
        if (failUpdate && limit === 100 && offset === 100) { status = 500; result = { detail: 'Fallo simulado de actualización.' }; }
        else {
          const matches = products.filter(product => !q || product.nombre.toLowerCase().includes(q));
          result = { items: matches.slice(offset, offset + limit), total: matches.length, limit, offset };
        }
      } else {
        result = products.find(product => url.pathname === `/api/catalogo/productos/${product.slug}`);
        if (!result) { status = 404; result = { detail: 'Producto no encontrado.' }; }
      }
      response.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
      response.end(JSON.stringify(result));
    });
    const apiOrigin = await listen(api);
    preview = createPwaServer({ apiOrigin });
    const origin = await listen(preview);

    browser = spawn(browserPath, [
      '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
      '--disable-background-networking', '--disable-sync', '--disable-extensions',
      '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank',
    ], { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] });
    let browserError;
    browser.on('error', error => { browserError = error; });
    browser.stderr.on('data', () => {});
    let port;
    const startDeadline = Date.now() + 20000;
    while (Date.now() < startDeadline) {
      if (browserError) throw browserError;
      if (browser.exitCode !== null) throw new Error('El navegador terminó antes de iniciar DevTools.');
      try { port = (await readFile(resolve(profile, 'DevToolsActivePort'), 'utf8')).split(/\r?\n/)[0]; break; } catch { await pause(100); }
    }
    if (!port) throw new Error('No se pudo iniciar DevTools en Edge.');
    const version = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
    const socket = new WebSocket(version.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => { socket.addEventListener('open', resolve, { once: true }); socket.addEventListener('error', reject, { once: true }); });
    tools = new DevTools(socket);
    async function newTab(offline = false) {
      const { targetId } = await tools.send('Target.createTarget', { url: 'about:blank' });
      const { sessionId } = await tools.send('Target.attachToTarget', { targetId, flatten: true });
      await tools.send('Page.enable', {}, sessionId);
      await tools.send('Runtime.enable', {}, sessionId);
      await tools.send('Network.enable', {}, sessionId);
      await tools.send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 1000, deviceScaleFactor: 1, mobile: false }, sessionId);
      if (offline) await tools.send('Network.emulateNetworkConditions', { offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0 }, sessionId);
      return { targetId, sessionId };
    }
    let { targetId, sessionId } = await newTab();
    await tools.send('Page.addScriptToEvaluateOnNewDocument', {
      source: "sessionStorage.setItem('vestinova_mvp_session', 'token-administrativo-solo-prueba');",
    }, sessionId);
    await tools.send('Page.navigate', { url: `${origin}/catalogo` }, sessionId);
    await tools.until(sessionId, "document.querySelectorAll('.catalog-card').length === 20", 'catálogo online');
    await tools.until(sessionId, "document.querySelector('.catalog-pwa-status')?.textContent.includes('Apertura sin conexión preparada')", 'recursos PWA preparados', 45000);
    passed('Recursos PWA preparados y catálogo online sin consultar administración.');

    await tools.evaluate(sessionId, "document.querySelector('.catalog-download button').click()");
    await tools.until(sessionId, "document.querySelector('.catalog-download')?.textContent.includes('121 prendas guardadas')", 'descarga de todas las páginas');
    assert.deepEqual(downloadOffsets, [0, 100]);
    const original = await tools.evaluate(sessionId, readSnapshot);
    assert.equal(original.total, 121);
    assert.equal(original.products.length, 121);
    assert.equal(original.products[0].precio, '149.90');
    assert.ok(original.downloadedAt);
    assert.ok(original.products.every(product => !('access_token' in product)));
    let currentSnapshot = original;
    passed('Descarga completa de 121 productos en dos páginas y persistencia pública en IndexedDB.');

    failUpdate = true;
    await tools.evaluate(sessionId, "document.querySelector('.catalog-download button').click()");
    await tools.until(sessionId, "document.querySelector('.catalog-download [role=alert]')?.textContent.includes('copia anterior se conserva')", 'actualización fallida');
    assert.deepEqual(await tools.evaluate(sessionId, readSnapshot), original);
    failUpdate = false;
    passed('Una actualización interrumpida conserva productos y fecha anteriores.');

    denied = true;
    await tools.evaluate(sessionId, "document.querySelector('.catalog-search button[type=submit]').click()");
    await tools.until(sessionId, "document.querySelector('.catalog-results [role=alert]')?.textContent.includes('No tienes permiso')", '403 sin usar copia local');
    assert.equal(await tools.evaluate(sessionId, "document.querySelectorAll('.catalog-card').length"), 0);
    assert.equal(await tools.evaluate(sessionId, "document.querySelector('.catalog-local-notice') !== null"), false);
    denied = false;
    await tools.evaluate(sessionId, "document.querySelector('.catalog-search button[type=submit]').click()");
    await tools.until(sessionId, "document.querySelectorAll('.catalog-card').length === 20", 'consulta autorizada de nuevo');
    passed('El rechazo de autorización del servidor no muestra productos de la copia.');

    await tools.evaluate(sessionId, "document.querySelector('.catalog-card').click()");
    await tools.until(sessionId, "document.querySelector('.catalog-detail__product')", 'detalle para preparar compra');
    const selectedName = await tools.evaluate(sessionId, "document.querySelector('.catalog-detail h1').textContent");
    await tools.evaluate(sessionId, "document.querySelector('.catalog-detail__content a').click()");
    await tools.until(sessionId, "document.querySelector('.purchase-line') && document.querySelector('.purchase-dependency')", 'selección con compras no disponibles');
    assert.equal(await tools.evaluate(sessionId, "document.querySelector('.purchase-line h3').textContent"), selectedName);
    assert.equal(await tools.evaluate(sessionId, "document.querySelector('.purchase-confirm').disabled"), true);
    await tools.evaluate(sessionId, "document.querySelector('.purchase-confirm').click()");
    assert.equal(await tools.evaluate(sessionId, "document.querySelector('.purchase-receipt') !== null"), false);
    assert.equal(capabilitiesRequests, 1);
    assert.equal(purchasePosts, 0);
    const checkoutMetrics = await tools.send('Page.getLayoutMetrics', {}, sessionId);
    await tools.send('Page.captureScreenshot', {
      format: 'png', captureBeyondViewport: true,
      clip: { x: 0, y: 0, width: 1280, height: Math.ceil(checkoutMetrics.cssContentSize.height), scale: 1 },
    }, sessionId).then(result => writeFile(resolve(runtime, 'cu10-compra-desktop.png'), Buffer.from(result.data, 'base64')));
    await tools.evaluate(sessionId, "document.querySelector('.purchase-page > .purchase-back').click()");
    await tools.until(sessionId, "document.querySelectorAll('.catalog-card').length === 20", 'volver de selección al catálogo');
    passed('CU10 conserva la selección con capacidades bloqueadas, confirmación desactivada y ningún recibo ni POST.');

    await tools.evaluate(sessionId, "document.querySelector('.catalog-header a[href=\"/catalogo/acciones/sincronizacion\"]').click()");
    await tools.until(sessionId, "document.querySelector('.sync-page')?.getAttribute('aria-busy') === 'false'", 'pantalla de sincronización');
    await tools.evaluate(sessionId, "document.querySelector('.sync-enqueue').click()");
    await tools.until(sessionId, "document.querySelectorAll('.sync-operation[data-state=PENDIENTE]').length === 1", 'operación registrada en cola real');
    const firstOperation = (await tools.evaluate(sessionId, readOperations))[0];
    assert.equal(firstOperation.expectedDownloadedAt, currentSnapshot.downloadedAt);
    await tools.evaluate(sessionId, "document.querySelector('.sync-process').click()");
    await tools.until(sessionId, "document.querySelector('.sync-operation[data-state=SINCRONIZADA]') && !document.querySelector('.sync-process').disabled", 'sincronización completada');
    currentSnapshot = await tools.evaluate(sessionId, readSnapshot);
    assert.notEqual(currentSnapshot.downloadedAt, original.downloadedAt);
    assert.deepEqual(currentSnapshot.products, original.products);
    assert.equal((await tools.evaluate(sessionId, readOperations)).find(operation => operation.id === firstOperation.id).state, 'SINCRONIZADA');
    passed('CU15 procesa una actualización pendiente con API temporal y cola IndexedDB reales.');

    await tools.evaluate(sessionId, "document.querySelector('.sync-enqueue').click()");
    await tools.until(sessionId, "document.querySelectorAll('.sync-operation[data-state=PENDIENTE]').length === 1", 'nueva operación antes del cambio manual');
    const conflictOperation = (await tools.evaluate(sessionId, readOperations)).find(operation => operation.state === 'PENDIENTE');
    assert.equal(conflictOperation.expectedDownloadedAt, currentSnapshot.downloadedAt);
    await tools.evaluate(sessionId, "document.querySelector('.catalog-download button').click()");
    await tools.until(sessionId, `(() => {
      const time = document.querySelector('.catalog-download time');
      return time && time.getAttribute('datetime') !== ${JSON.stringify(currentSnapshot.downloadedAt)}
        && !document.querySelector('.catalog-download button').disabled;
    })()`, 'descarga manual posterior al registro');
    currentSnapshot = await tools.evaluate(sessionId, readSnapshot);
    const offsetsBeforeConflict = downloadOffsets.length;
    await tools.evaluate(sessionId, "document.querySelector('.sync-process').click()");
    await tools.until(sessionId, "document.querySelector('.sync-operation[data-state=CONFLICTO]') && !document.querySelector('.sync-process').disabled", 'conflicto de copia local');
    assert.deepEqual(await tools.evaluate(sessionId, readSnapshot), currentSnapshot);
    assert.equal(downloadOffsets.length, offsetsBeforeConflict);
    assert.equal((await tools.evaluate(sessionId, readOperations)).find(operation => operation.id === conflictOperation.id).state, 'CONFLICTO');
    const syncMetrics = await tools.send('Page.getLayoutMetrics', {}, sessionId);
    await tools.send('Page.captureScreenshot', {
      format: 'png', captureBeyondViewport: true,
      clip: { x: 0, y: 0, width: 1280, height: Math.ceil(syncMetrics.cssContentSize.height), scale: 1 },
    }, sessionId).then(result => writeFile(resolve(runtime, 'cu15-sincronizacion-desktop.png'), Buffer.from(result.data, 'base64')));
    await tools.evaluate(sessionId, "document.querySelector('.sync-page > .sync-back').click()");
    await tools.until(sessionId, "document.querySelectorAll('.catalog-card').length === 20", 'volver al catálogo antes del corte');
    passed('CU15 detecta una actualización manual posterior y conserva la copia sin forzar el conflicto.');

    // Cortar también el origen real impide que un fetch del worker oculte una
    // simulación offline limitada únicamente al target de DevTools.
    preview.closeAllConnections();
    await new Promise(resolve => preview.close(resolve));
    preview = null;
    await tools.send('Network.emulateNetworkConditions', { offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0 }, sessionId);
    await tools.send('Page.reload', {}, sessionId);
    await tools.until(sessionId, "document.querySelector('.catalog-local-notice time') && document.querySelectorAll('.catalog-card').length === 20", 'recarga de catálogo offline');
    assert.equal(await tools.evaluate(sessionId, "document.querySelector('.catalog-local-notice time').getAttribute('datetime')"), currentSnapshot.downloadedAt);
    passed('Recarga sin conexión: shell del Service Worker y productos de IndexedDB con su fecha.');

    await tools.evaluate(sessionId, `(() => {
      const input = document.querySelector('#catalog-search'); input.value = 'prenda de prueba 12';
      input.dispatchEvent(new Event('input', { bubbles: true }));
      document.querySelector('.catalog-search').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    })()`);
    await tools.until(sessionId, "document.querySelectorAll('.catalog-card').length === 3 && document.querySelector('.catalog-local-notice')", 'búsqueda local');
    await tools.evaluate(sessionId, "Array.from(document.querySelectorAll('.catalog-search button')).find(button => button.textContent.trim() === 'Limpiar').click()");
    await tools.until(sessionId, "document.querySelectorAll('.catalog-card').length === 20", 'limpiar búsqueda local');
    await tools.evaluate(sessionId, "Array.from(document.querySelectorAll('.catalog-pagination button')).find(button => button.textContent.trim() === 'Siguiente').click()");
    await tools.until(sessionId, "document.querySelector('.catalog-pagination p')?.textContent.includes('21–40 de 121')", 'paginación local');
    passed('Búsqueda y paginación sobre la copia completa, sin Internet.');
    await tools.send('Page.captureScreenshot', { format: 'png' }, sessionId).then(result => writeFile(resolve(runtime, 'cu14-catalogo-offline.png'), Buffer.from(result.data, 'base64')));

    const detailPath = await tools.evaluate(sessionId, "document.querySelector('.catalog-card').getAttribute('href')");
    await tools.evaluate(sessionId, "document.querySelector('.catalog-card').click()");
    await tools.until(sessionId, "document.querySelector('.catalog-detail__product') && document.querySelector('.catalog-local-notice time')", 'detalle nunca visitado offline');
    await tools.send('Page.reload', {}, sessionId);
    await tools.until(sessionId, "document.querySelector('.catalog-detail__product') && document.querySelector('.catalog-local-notice time')", 'recarga directa del detalle offline');
    passed('Detalle y recarga de su URL directa sin conexión, incluidos los chunks precargados.');

    await tools.send('Target.closeTarget', { targetId });
    ({ targetId, sessionId } = await newTab(true));
    await tools.send('Page.navigate', { url: `${origin}${detailPath}` }, sessionId);
    await tools.until(sessionId, "document.querySelector('.catalog-detail__product') && document.querySelector('.catalog-local-notice time')", 'reabrir pestaña offline');
    await tools.send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: false }, sessionId);
    const metrics = await tools.send('Page.getLayoutMetrics', {}, sessionId);
    await tools.send('Page.captureScreenshot', {
      format: 'png', captureBeyondViewport: true,
      clip: { x: 0, y: 0, width: 390, height: Math.ceil(metrics.cssContentSize.height), scale: 1 },
    }, sessionId).then(result => writeFile(resolve(runtime, 'cu14-detalle-offline-movil.png'), Buffer.from(result.data, 'base64')));
    passed('Nueva pestaña abierta directamente al detalle offline con datos persistidos.');

    const cachedUrls = await tools.evaluate(sessionId, `(async () => {
      const result = [];
      for (const name of await caches.keys()) for (const request of await (await caches.open(name)).keys()) result.push(request.url);
      return result;
    })()`);
    assert.ok(cachedUrls.length > 0);
    assert.ok(cachedUrls.every(url => !/^\/api(?:\/|$)/.test(new URL(url).pathname)));
    assert.equal(leakedAuthorization, false);
    assert.equal(privateRequests, 0);
    assert.equal(purchasePosts, 0);
    passed('CacheStorage sin respuestas API y ninguna petición con credenciales ni a módulos privados.');

    await tools.send('Page.navigate', { url: `${origin}/catalogo/acciones/sincronizacion` }, sessionId);
    await tools.until(sessionId, "document.querySelectorAll('.sync-operation').length === 2 && document.querySelector('.sync-page')?.getAttribute('aria-busy') === 'false'", 'cola reabierta offline');
    await tools.evaluate(sessionId, "document.querySelector('.sync-enqueue').click()");
    await tools.until(sessionId, "document.querySelectorAll('.sync-operation[data-state=PENDIENTE]').length === 1", 'operación registrada sin conexión');
    const offlineOperation = (await tools.evaluate(sessionId, readOperations)).find(operation => operation.state === 'PENDIENTE');
    await tools.send('Page.reload', {}, sessionId);
    await tools.until(sessionId, "document.querySelectorAll('.sync-operation[data-state=PENDIENTE]').length === 1", 'operación offline persistida tras recargar');
    assert.equal((await tools.evaluate(sessionId, readOperations)).find(operation => operation.id === offlineOperation.id).state, 'PENDIENTE');
    await tools.evaluate(sessionId, "document.querySelector('.sync-process').click()");
    await tools.until(sessionId, "document.querySelector('.sync-operation[data-state=ERROR]') && !document.querySelector('.sync-process').disabled", 'error de actualización sin conexión');
    const failedOffline = (await tools.evaluate(sessionId, readOperations)).find(operation => operation.id === offlineOperation.id);
    assert.equal(failedOffline.state, 'ERROR');
    assert.equal(failedOffline.expectedDownloadedAt, currentSnapshot.downloadedAt);
    assert.deepEqual(await tools.evaluate(sessionId, readSnapshot), currentSnapshot);
    passed('CU15 registra y recupera la cola offline; el error de red conserva la copia y el UUID de la operación.');
    await tools.send('Page.navigate', { url: `${origin}${detailPath}` }, sessionId);
    await tools.until(sessionId, "document.querySelector('.catalog-detail__product') && document.querySelector('.catalog-local-notice time')", 'volver al detalle antes de eliminar la copia de prueba');

    await tools.evaluate(sessionId, `new Promise((resolve, reject) => {
      const request = indexedDB.deleteDatabase('vestinova-public-catalog');
      request.onsuccess = () => resolve(true); request.onerror = request.onblocked = () => reject(new Error('No se pudo borrar la copia de prueba'));
    })`);
    await tools.send('Page.reload', {}, sessionId);
    await tools.until(sessionId, "document.querySelector('.catalog-detail [role=alert]')?.textContent.includes('No hay un catálogo descargado')", 'mensaje sin copia local');
    assert.equal(await tools.evaluate(sessionId, "document.querySelector('.catalog-detail__product') !== null"), false);
    passed('Aplicación offline sin copia: mensaje explícito y ningún producto inventado.');
    console.log(`PWA: ${reports.length} comprobaciones de navegador correctas. API temporal; PostgreSQL no utilizado.`);
  } finally {
    if (tools) {
      await tools.send('Browser.close').catch(() => {});
      tools.socket.close();
    }
    if (browser && browser.exitCode === null) {
      await Promise.race([new Promise(resolve => browser.once('exit', resolve)), pause(5000)]);
      if (browser.exitCode === null) browser.kill();
    }
    for (const server of [preview, api]) if (server) {
      server.closeAllConnections();
      await new Promise(resolve => server.close(resolve));
    }
    // Borrar únicamente el perfil temporal creado dentro de .angular, nunca perfiles del usuario.
    const base = await realpath(runtime);
    const target = await realpath(profile).catch(() => null);
    if (target) {
      const path = relative(base, target);
      if (!path || isAbsolute(path) || path === '..' || path.startsWith(`..${sep}`)) throw new Error('Se rechazó limpiar una ruta fuera del espacio de pruebas.');
      await rm(target, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
    }
  }
}

run().catch(error => { console.error(`Falló la prueba PWA: ${error.message}`); process.exitCode = 1; });
