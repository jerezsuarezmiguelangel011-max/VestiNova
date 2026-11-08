# Implementación web CU25 y CU26 de VestiNova

## CU25: compras verificadas y valoración

La compra digital confirmada no se considera entregada hasta que el personal autorizado de la sucursal lo registre en /admin/entregas-compras. El registro exige confirmar la identidad y conserva constancia y auditoría. El Cliente entra a /tienda/{slug}/valoraciones desde Mis compras para publicar (1 a 5) o editar su valoración. El backend exige compra pagada, entregada, propia y con la prenda en el comprobante; impide duplicaciones y acceso a opiniones ajenas. El catálogo ofrece una API pública de opiniones verificadas sin exponer datos privados del autor.

## CU26: avisos Web Push

Requiere Chrome/Firefox/Safari compatible, origen seguro HTTPS (o localhost), y Angular PWA compilada con Service Worker habilitado; ng serve en modo de desarrollo no activa ese Service Worker. Para completar la configuración debe establecerse en backend/.env privado o secretos del despliegue:

VAPID_PUBLIC_KEY=clave pública base64url
VAPID_PRIVATE_KEY=clave privada DER base64url o ruta a PEM
VAPID_CONTACT=mailto:correo@dominio

Nunca colocar la clave privada en el frontend ni commitearla. La API solo registra canales de proveedores Web Push admitidos. Los Clientes seleccionan variante y sucursal con saldo registrado agotado; el navegador pide permiso al pulsar la opción y registra el canal. Las reposiciones que cambian disponibilidad de cero a positiva en recepción de abastecimiento o entradas/ajustes generan eventos en la misma transacción de inventario. El dispatcher periódico procesa la cola; un mismo movimiento, suscripción y canal producen una sola fila. Los avisos son informativos y no reservan unidades. La cancelación de alertas se gestiona en /tienda/{slug}/alertas.

Comandos de actualización y validación desde backend: pip install -r requirements.lock.txt; python -m alembic upgrade head; python -m pytest -q tests.

Queda por verificar manualmente la recepción push con un navegador real, claves VAPID correctas y un entorno seguro.

La revisión de convergencia de Alembic es c26merge2026 (une las cadenas de CU25/CU26 y caja). Aplicar con python -m alembic upgrade head tras hacer copia de respaldo.
