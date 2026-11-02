import { Routes } from '@angular/router';
import { adminGuard, guestGuard, platformGuard } from './auth/auth.guards';
import { cashierGuard, companyAdminGuard, companyGuard, productsGuard } from './company/company.guards';
import { customerGuard } from './customer/customer.guards';
import { productFormLeaveGuard } from './products/product-form.guard';
import { variantLeaveGuard } from './products/variant-page.guard';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'admin/productos' },
  { path: 'tienda/:tienda/acceso', loadComponent: () => import('./customer/customer-access-page').then(m => m.CustomerAccessPage) },
  { path: 'tienda/:tienda/cuenta', canActivate: [customerGuard], loadComponent: () => import('./customer/customer-account-page').then(m => m.CustomerAccountPage) },
  {
    path: 'catalogo',
    loadComponent: () => import('./catalog/catalog-layout').then(m => m.CatalogLayout),
    children: [
      { path: '', pathMatch: 'full', loadComponent: () => import('./catalog/catalog-list').then(m => m.CatalogListPage) },
      { path: 'acciones/reserva', loadComponent: () => import('./reservations/reservation-draft').then(m => m.ReservationDraftPage) },
      { path: 'acciones/compra', loadComponent: () => import('./purchases/purchase-page').then(m => m.PurchasePage) },
      { path: 'acciones/sincronizacion', loadComponent: () => import('./sync/sync-page').then(m => m.SyncPage) },
      { path: ':slug', loadComponent: () => import('./catalog/catalog-detail').then(m => m.CatalogDetailPage) },
    ],
  },
  {
    path: 'admin/login', canActivate: [guestGuard],
    loadComponent: () => import('./auth/login-page').then(m => m.LoginPage),
  },
  {
    path: 'admin', canActivate: [adminGuard], canActivateChild: [adminGuard],
    loadComponent: () => import('./layout/admin-layout').then(m => m.AdminLayout),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'productos' },
      { path: 'empresa', loadComponent: () => import('./company/company-page').then(m => m.CompanyPage) },
      { path: 'plataforma', canActivate: [platformGuard], loadComponent: () => import('./auth/platform-access-page').then(m => m.PlatformAccessPage) },
      { path: 'acceso', canActivate: [companyGuard], loadComponent: () => import('./auth/staff-access-page').then(m => m.StaffAccessPage) },
      { path: 'caja', canActivate: [cashierGuard], loadComponent: () => import('./cash-sale/cash-sale.page').then(m => m.CashSalePage) },
      { path: 'inventario', canActivate: [companyGuard], loadComponent: () => import('./inventory/inventory-page').then(m => m.InventoryPage) },
      { path: 'productos', canActivate: [productsGuard], loadComponent: () => import('./products/product-list').then(m => m.ProductListPage) },
      { path: 'productos/nuevo', canActivate: [companyAdminGuard], canDeactivate: [productFormLeaveGuard], loadComponent: () => import('./products/product-form').then(m => m.ProductFormPage) },
      { path: 'productos/:id/variantes', canActivate: [productsGuard], canDeactivate: [variantLeaveGuard], loadComponent: () => import('./products/variant-page').then(m => m.VariantPage) },
      { path: 'productos/:id/editar', canActivate: [companyAdminGuard], canDeactivate: [productFormLeaveGuard], loadComponent: () => import('./products/product-form').then(m => m.ProductFormPage) },
    ],
  },
  { path: '**', loadComponent: () => import('./layout/not-found-page').then(m => m.NotFoundPage) },
];
