"""Prueba migraciones y API en un cluster temporal; no usa la base del usuario."""
import argparse
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pg-bin', required=True, type=Path)
    parser.add_argument('--mobile-http', action='store_true', help='Incluye cliente Dart/Flutter contra la API HTTP y PostgreSQL aislados.')
    parser.add_argument('--flutter-bin', type=Path, help='Ruta a flutter.bat o flutter; necesaria con --mobile-http.')
    args = parser.parse_args()
    extension = '.exe' if os.name == 'nt' else ''
    initdb = args.pg_bin / f'initdb{extension}'
    pg_ctl = args.pg_bin / f'pg_ctl{extension}'
    if not initdb.is_file() or not pg_ctl.is_file():
        parser.error('--pg-bin debe contener initdb y pg_ctl.')
    if args.mobile_http and (args.flutter_bin is None or not args.flutter_bin.is_file()):
        parser.error('--mobile-http requiere --flutter-bin con una ruta existente.')

    runtime = ROOT / '.runtime'
    runtime.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='postgres-test-', dir=runtime)).resolve()
    if work.parent != runtime.resolve():
        raise RuntimeError('Directorio temporal fuera del MVP.')
    data = work / 'data'
    log = work / 'postgres.log'
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]

    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    def run(command, **kwargs):
        return subprocess.run(command, cwd=ROOT, creationflags=flags, **kwargs)

    started = False
    try:
        with (work / 'init.log').open('w', encoding='utf-8') as output:
            run([str(initdb), '-D', str(data), '-A', 'trust', '-U', 'mvp_test',
                 '--encoding=UTF8', '--no-locale'], stdout=output, stderr=subprocess.STDOUT,
                check=True, timeout=40)
        # En Windows el servidor puede heredar pipes de pg_ctl: usar archivo,
        # no capture_output, para que communicate no espere al servidor completo.
        with (work / 'control.log').open('w', encoding='utf-8') as control:
            run([str(pg_ctl), '-D', str(data), '-l', str(log), '-o',
                 f'-p {port} -h 127.0.0.1', '-w', '-t', '20', 'start'],
                stdout=control, stderr=subprocess.STDOUT, check=True, timeout=30)
        started = True
        import psycopg
        with psycopg.connect(host='127.0.0.1', port=port, user='mvp_test',
                             dbname='postgres', autocommit=True) as connection:
            connection.execute('CREATE DATABASE vestinova_mvp')
        env = os.environ.copy()
        env.update({
            'DATABASE_URL': f'postgresql+psycopg://mvp_test@127.0.0.1:{port}/vestinova_mvp',
            'JWT_SECRET': secrets.token_urlsafe(48),
            'MVP_ISOLATED_POSTGRES': '1',
            'PYTHONUTF8': '1',
        })
        if args.mobile_http:
            env['MVP_MOBILE_HTTP_CHECK'] = '1'
            env['MVP_FLUTTER_BIN'] = str(args.flutter_bin.resolve())
        print('Pruebas sobre PostgreSQL temporal. No se usa .env ni la base operativa.', flush=True)
        result = run([sys.executable, '-m', 'pytest', 'tests_postgres', '-q', '--tb=short'],
                     env=env, capture_output=True, text=True, encoding='utf-8', timeout=300 if args.mobile_http else 180)
        (work / 'tests.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        print(result.stdout, end='', flush=True)
        if result.stderr:
            print(result.stderr, file=sys.stderr, end='', flush=True)
        return result.returncode
    except (subprocess.SubprocessError, OSError):
        print(f'No se completó la instancia aislada. Revisa los registros en {work}.', file=sys.stderr)
        return 1
    finally:
        if started:
            with (work / 'control.log').open('a', encoding='utf-8') as control:
                result = run([str(pg_ctl), '-D', str(data), '-m', 'fast', '-w', '-t', '20', 'stop'],
                             stdout=control, stderr=subprocess.STDOUT, timeout=30)
            if result.returncode:
                print(f'Revisa la parada de la instancia temporal: {data}', file=sys.stderr)
        # Se conservan los registros para diagnóstico en .runtime (ignorado por Git).


if __name__ == '__main__':
    raise SystemExit(main())
