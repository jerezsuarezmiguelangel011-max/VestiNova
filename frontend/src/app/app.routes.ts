import { Routes } from '@angular/router';
import { adminGuard, guestGuard, platformGuard } from './autenticacion_usuarios/autenticacion/auth.guards';
import { cashierGuard, managerGuard, adminHomeGuard, companyAdminGuard, companyGuard, productsGuard } from './organizacion_empresarial/empresa/company.guards';
import { customerGuard } from './compras_reservas/clientes/customer.guards';
import { productFormLeaveGuard } from './catalogo_abastecimiento/productos/product-form.guard';
import { variantLeaveGuard } from './catalogo_abastecimiento/productos/variant-page.guard';
import { staffLeaveGuard, staffPermissionGuard } from './autenticacion_usuarios/personal/staff.guards';

export const routes: Routes = [
  { path: '', pathMatch: 'full', loadComponent: () => import('./catalogo_publico/catalogo/public-portal').then(m => m.PublicPortalPage) },
  { path: 'tienda/:tienda/acceso', loadComponent: () => import('./compras_reservas/clientes/customer-access-page').then(m => m.CustomerAccessPage) },
  { path: 'tienda/:tienda/cuenta', canActivate: [customerGuard], loadComponent: () => import('./compras_reservas/clientes/customer-account-page').then(m => m.CustomerAccountPage) },
  { path: 'tienda/:tienda/compras', canActivate: [customerGuard], loadComponent: () => import('./compras_reservas/compras/purchase-history-page').then(m => m.PurchaseHistoryPage) },
  { path: 'tienda/:tienda/deseos', canActivate: [customerGuard], loadComponent: () => import('./compras_reservas/deseos/customer-wishlist-page').then(m => m.CustomerWishlistPage) },
  { path: 'tienda/:tienda/valoraciones', canActivate: [customerGuard], loadComponent: () => import('./compras_reservas/compras/purchase-reviews-page').then(m => m.PurchaseReviewsPage) },
  { path: 'tienda/:tienda/alertas', canActivate: [customerGuard], loadComponent: () => import('./compras_reservas/alertas_push/restock-alerts-page').then(m => m.RestockAlertsPage) },
  {
    path: 'tienda/:tienda',
    loadComponent: () => import('./catalogo_publico/catalogo/storefront-layout').then(m => m.StorefrontLayout),
    children: [
      { path: '', pathMatch: 'full', loadComponent: () => import('./catalogo_publico/catalogo/storefront-home').then(m => m.StorefrontHomePage) },
      { path: 'catalogo', loadComponent: () => import('./catalogo_publico/catalogo/catalog-list').then(m => m.CatalogListPage) },
      { path: 'recomendaciones', loadComponent: () => import('./catalogo_publico/recomendaciones/recommendations-page').then(m => m.RecommendationsPage) },
      { path: 'comparar', loadComponent: () => import('./catalogo_publico/catalogo/catalog-comparison-page').then(m => m.CatalogComparisonPage) },
      { path: 'prenda/:slug', loadComponent: () => import('./catalogo_publico/catalogo/catalog-detail').then(m => m.CatalogDetailPage) },
    ],
  },
  {
    path: 'catalogo',
    loadComponent: () => import('./catalogo_publico/catalogo/catalog-layout').then(m => m.CatalogLayout),
    children: [
      { path: '', pathMatch: 'full', loadComponent: () => import('./catalogo_publico/catalogo/catalog-list').then(m => m.CatalogListPage) },
      { path: 'acciones/reserva', loadComponent: () => import('./compras_reservas/reservas/reservation-draft').then(m => m.ReservationDraftPage) },
      { path: 'acciones/compra', loadComponent: () => import('./compras_reservas/compras/stripe-purchase-page').then(m => m.StripePurchasePage) },
      { path: 'acciones/comparar', loadComponent: () => import('./catalogo_publico/catalogo/catalog-comparison-page').then(m => m.CatalogComparisonPage) },
      { path: 'acciones/sincronizacion', loadComponent: () => import('./operacion_sin_conexion/sincronizacion/sync-page').then(m => m.SyncPage) },
      { path: 'vestidor/:slug', loadComponent: () => import('./catalogo_publico/vestidor_virtual/virtual-fitting-room-page').then(m => m.VirtualFittingRoomPage) },
      { path: ':slug', loadComponent: () => import('./catalogo_publico/catalogo/catalog-detail').then(m => m.CatalogDetailPage) },
    ],
  },
  {
    path: 'admin/login', canActivate: [guestGuard],
    loadComponent: () => import('./autenticacion_usuarios/autenticacion/login-page').then(m => m.LoginPage),
  },
  {
    path: 'admin', canActivate: [adminGuard], canActivateChild: [adminGuard],
    loadComponent: () => import('./autenticacion_usuarios/estructura/admin-layout').then(m => m.AdminLayout),
    children: [
      { path: '', pathMatch: 'full', canActivate: [adminHomeGuard],
        loadComponent: () => import('./autenticacion_usuarios/autenticacion/staff-access-page').then(m => m.StaffAccessPage) },
      { path: 'empresa', loadComponent: () => import('./organizacion_empresarial/empresa/company-page').then(m => m.CompanyPage) },
      {
        path: 'plataforma', canActivate: [platformGuard], children: [
          { path: '', pathMatch: 'full', redirectTo: 'empresas' },
          { path: 'empresas', loadComponent: () => import('./organizacion_empresarial/plataforma/platform-companies-page').then(m => m.PlatformCompaniesPage) },
          { path: 'planes', loadComponent: () => import('./organizacion_empresarial/plataforma/platform-plans-page').then(m => m.PlatformPlansPage) },
        ],
      },
      { path: 'acceso', canActivate: [companyGuard], loadComponent: () => import('./autenticacion_usuarios/autenticacion/staff-access-page').then(m => m.StaffAccessPage) },
      { path: 'caja', canActivate: [cashierGuard], loadComponent: () => import('./operacion_sin_conexion/caja/cash-sale.page').then(m => m.CashSalePage) },
      { path: 'atencion-reservas', canActivate: [cashierGuard], loadComponent: () => import('./compras_reservas/reservas/reservation-attention-page').then(m => m.ReservationAttentionPage) },
      { path: 'conciliacion', canActivate: [managerGuard], loadComponent: () => import('./operacion_sin_conexion/sincronizacion/reconciliation-page').then(m => m.ReconciliationPage) },
      { path: 'reportes-comerciales', canActivate: [staffPermissionGuard], data: { permission: 'reportes.consultar' }, loadComponent: () => import('./reportes_comerciales/reports-page').then(m => m.ReportsPage) },
      {
        path: 'catalogo-consulta', canActivate: [companyGuard],
        loadComponent: () => import('./catalogo_publico/catalogo/admin-catalog-page').then(m => m.AdminCatalogPage),
        children: [
          { path: '', pathMatch: 'full', loadComponent: () => import('./catalogo_publico/catalogo/catalog-list').then(m => m.CatalogListPage) },
          { path: ':slug', loadComponent: () => import('./catalogo_publico/catalogo/catalog-detail').then(m => m.CatalogDetailPage) },
        ],
      },
      { path: 'inventario', canActivate: [companyGuard], loadComponent: () => import('./inventario/inventory-page').then(m => m.InventoryPage) },
      { path: 'sucursales', canActivate: [staffPermissionGuard], data: { permission: 'sucursales.gestionar' }, loadComponent: () => import('./organizacion_empresarial/sucursales/branch-page').then(m => m.BranchPage) },
      { path: 'usuarios', canActivate: [staffPermissionGuard], canDeactivate: [staffLeaveGuard], data: { permission: 'usuarios.consultar' }, loadComponent: () => import('./autenticacion_usuarios/personal/staff-users-page').then(m => m.StaffUsersPage) },
      { path: 'roles', canActivate: [staffPermissionGuard], canDeactivate: [staffLeaveGuard], data: { permission: 'roles.consultar' }, loadComponent: () => import('./autenticacion_usuarios/personal/staff-roles-page').then(m => m.StaffRolesPage) },
      { path: 'auditoria', canActivate: [staffPermissionGuard], data: { permission: 'auditoria.consultar' }, loadComponent: () => import('./organizacion_empresarial/auditoria/audit-page').then(m => m.AuditPage) },
      { path: 'reservas', canActivate: [companyGuard], loadComponent: () => import('./compras_reservas/reservas/reservation-staff-page').then(m => m.ReservationStaffPage) },
      { path: 'reportes-ia', canActivate: [staffPermissionGuard], data: { permission: 'reportes.ia.consultar' }, loadComponent: () => import('./analitica_ia/reports-page').then(m => m.ReportsPage) },
      { path: 'dashboard-predictivo', canActivate: [staffPermissionGuard], data: { permission: 'analitica.consultar' }, loadComponent: () => import('./analitica_ia/dashboard-page').then(m => m.DashboardPage) },
      { path: 'postventa', canActivate: [staffPermissionGuard], data: { permission: 'postventa.consultar' }, loadComponent: () => import('./compras_reservas/postventa/postventa-page').then(m => m.PostventaPage) },
      { path: 'entregas-compras', canActivate: [companyGuard], loadComponent: () => import('./compras_reservas/compras/purchase-deliveries-page').then(m => m.PurchaseDeliveriesPage) },
      { path: 'promociones', canActivate: [staffPermissionGuard], data: { permission: 'promociones.consultar' }, loadComponent: () => import('./catalogo_abastecimiento/promociones/promotions-page').then(m => m.PromotionsPage) },
      { path: 'abastecimiento', canActivate: [staffPermissionGuard], data: { permission: 'abastecimiento.consultar' }, loadComponent: () => import('./catalogo_abastecimiento/abastecimiento/procurement-page').then(m => m.ProcurementPage) },
      { path: 'mi-plan', canActivate: [staffPermissionGuard], data: { permission: 'plan.consultar' }, loadComponent: () => import('./organizacion_empresarial/plataforma/my-plan-page').then(m => m.MyPlanPage) },
      { path: 'categorias', canActivate: [staffPermissionGuard], data: { permission: 'catalogo.gestionar' }, loadComponent: () => import('./catalogo_abastecimiento/categorias/category-page').then(m => m.CategoryPage) },
      { path: 'productos', canActivate: [productsGuard], loadComponent: () => import('./catalogo_abastecimiento/productos/product-list').then(m => m.ProductListPage) },
      { path: 'productos/nuevo', canActivate: [companyAdminGuard], canDeactivate: [productFormLeaveGuard], loadComponent: () => import('./catalogo_abastecimiento/productos/product-form').then(m => m.ProductFormPage) },
      { path: 'productos/:id/variantes', canActivate: [productsGuard], canDeactivate: [variantLeaveGuard], loadComponent: () => import('./catalogo_abastecimiento/productos/variant-page').then(m => m.VariantPage) },
      { path: 'productos/:id/editar', canActivate: [companyAdminGuard], canDeactivate: [productFormLeaveGuard], loadComponent: () => import('./catalogo_abastecimiento/productos/product-form').then(m => m.ProductFormPage) },
    ],
  },
  { path: '**', loadComponent: () => import('./autenticacion_usuarios/estructura/not-found-page').then(m => m.NotFoundPage) },
];
