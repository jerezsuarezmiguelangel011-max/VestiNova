import { createReadStream } from 'node:fs';
import { access, realpath, stat } from 'node:fs/promises';
import { createServer, request as httpRequest } from 'node:http';
import { request as httpsRequest } from 'node:https';
import { basename, extname, isAbsolute, relative, resolve, sep } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

export const defaultBuildRoot = fileURLToPath(new URL('../dist/vestinova-mvp/browser/', import.meta.url));

const CONTENT_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.webmanifest': 'application/manifest+json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.txt': 'text/plain; charset=utf-8',
};

function sendText(response, status, message) {
  if (response.headersSent) {
    response.destroy();
    return;
  }
  response.writeHead(status, {
    'Content-Type': 'text/plain; charset=utf-8',
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
  });
  response.end(message);
}

function withoutHopHeaders(headers) {
  const excluded = new Set([
    'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
    'te', 'trailer', 'transfer-encoding', 'upgrade',
    ...(headers.connection ?? '').split(',').map(value => value.trim().toLowerCase()),
  ]);
  return Object.fromEntries(Object.entries(headers).filter(([name]) => !excluded.has(name.toLowerCase())));
}

function proxyApi(request, response, url, apiTarget) {
  const transport = apiTarget.protocol === 'https:' ? httpsRequest : httpRequest;
  const upstream = transport({
    protocol: apiTarget.protocol,
    hostname: apiTarget.hostname,
    port: apiTarget.port || (apiTarget.protocol === 'https:' ? 443 : 80),
    method: request.method,
    path: `${url.pathname}${url.search}`,
    headers: { ...withoutHopHeaders(request.headers), host: apiTarget.host },
  }, upstreamResponse => {
    response.writeHead(upstreamResponse.statusCode ?? 502, {
      ...withoutHopHeaders(upstreamResponse.headers),
      'cache-control': 'no-store',
      'x-content-type-options': 'nosniff',
    });
    upstreamResponse.on('error', () => response.destroy());
    upstreamResponse.pipe(response);
  });
  upstream.setTimeout(15000, () => upstream.destroy());
  upstream.on('error', () => sendText(response, 502, 'No se pudo conectar con la API local.'));
  request.on('aborted', () => upstream.destroy());
  response.on('close', () => { if (!response.writableEnded) upstream.destroy(); });
  request.pipe(upstream);
}

function isInside(directory, file) {
  const path = relative(directory, file);
  return path === '' || (!isAbsolute(path) && path !== '..' && !path.startsWith(`..${sep}`));
}

export function createPwaServer({ apiOrigin = 'http://127.0.0.1:8001', root = defaultBuildRoot } = {}) {
  const buildRoot = resolve(root);
  const apiTarget = new URL(apiOrigin);
  if (!['http:', 'https:'].includes(apiTarget.protocol) || apiTarget.username || apiTarget.password) {
    throw new Error('La API debe usar un origen HTTP o HTTPS sin credenciales.');
  }

  return createServer(async (request, response) => {
    try {
      const url = new URL(request.url ?? '/', 'http://127.0.0.1');
      if (url.pathname === '/api' || url.pathname.startsWith('/api/')) {
        proxyApi(request, response, url, apiTarget);
        return;
      }
      if (!['GET', 'HEAD'].includes(request.method ?? '')) {
        response.setHeader('Allow', 'GET, HEAD');
        sendText(response, 405, 'Método no permitido.');
        return;
      }

      let pathname;
      try {
        pathname = decodeURIComponent(url.pathname);
      } catch {
        sendText(response, 400, 'Ruta no válida.');
        return;
      }
      if (pathname.includes('\0') || pathname.includes('\\')) {
        sendText(response, 400, 'Ruta no válida.');
        return;
      }

      let file = resolve(buildRoot, `.${pathname}`);
      if (!isInside(buildRoot, file)) {
        sendText(response, 404, 'Archivo no encontrado.');
        return;
      }

      let info;
      try {
        info = await stat(file);
        if (!info.isFile()) throw new Error('not-file');
      } catch {
        const acceptsHtml = (request.headers.accept ?? '').includes('text/html');
        if (!acceptsHtml || extname(pathname) || pathname.startsWith('/api/')) {
          sendText(response, 404, 'Archivo no encontrado.');
          return;
        }
        file = resolve(buildRoot, 'index.html');
        info = await stat(file);
      }

      if (!isInside(await realpath(buildRoot), await realpath(file))) {
        sendText(response, 404, 'Archivo no encontrado.');
        return;
      }

      const fileName = basename(file);
      const neverStale = ['index.html', 'ngsw.json', 'ngsw-worker.js', 'safety-worker.js', 'worker-basic.min.js', 'manifest.webmanifest'].includes(fileName);
      response.writeHead(200, {
        'Content-Type': CONTENT_TYPES[extname(file)] ?? 'application/octet-stream',
        'Content-Length': info.size,
        'Cache-Control': neverStale ? 'no-cache, no-store, must-revalidate' : 'public, max-age=3600',
        'X-Content-Type-Options': 'nosniff',
      });
      if (request.method === 'HEAD') {
        response.end();
        return;
      }
      const stream = createReadStream(file);
      stream.on('error', () => response.destroy());
      stream.pipe(response);
    } catch {
      sendText(response, 500, 'No se pudo servir la aplicación. Comprueba el build de producción.');
    }
  });
}

async function main() {
  const args = process.argv.slice(2);
  let port = 4201;
  if (args.length) {
    if (args.length !== 2 || args[0] !== '--port') throw new Error('Uso: node scripts/serve-pwa.mjs [--port 4301]');
    port = Number(args[1]);
    if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('El puerto debe estar entre 1 y 65535.');
  }
  try {
    await access(resolve(defaultBuildRoot, 'index.html'));
    await access(resolve(defaultBuildRoot, 'ngsw.json'));
  } catch {
    throw new Error('Primero genera el build de producción con npm.cmd run build.');
  }
  const server = createPwaServer();
  server.on('error', () => {
    console.error('No se pudo iniciar la vista previa. Comprueba que el puerto esté libre.');
    process.exitCode = 1;
  });
  server.listen(port, '127.0.0.1', () => {
    console.log(`VestiNova PWA: http://127.0.0.1:${port}/catalogo`);
  });
  for (const signal of ['SIGINT', 'SIGTERM']) {
    process.once(signal, () => server.close(() => process.exit(0)));
  }
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  main().catch(error => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
