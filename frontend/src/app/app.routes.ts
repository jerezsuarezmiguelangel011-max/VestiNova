import { Routes } from '@angular/router';
import { adminGuard, guestGuard } from './auth/auth.guards';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'admin/productos' },
  {
    path: 'catalogo',
    loadComponent: () => import('./catalog/catalog-layout').then(m => m.CatalogLayout),
    children: [
      { path: '', pathMatch: 'full', loadComponent: () => import('./catalog/catalog-list').then(m => m.CatalogListPage) },
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
      { path: 'productos', loadComponent: () => import('./products/product-list').then(m => m.ProductListPage) },
      { path: 'productos/nuevo', loadComponent: () => import('./products/product-form').then(m => m.ProductFormPage) },
      { path: 'productos/:id/editar', loadComponent: () => import('./products/product-form').then(m => m.ProductFormPage) },
    ],
  },
  { path: '**', loadComponent: () => import('./layout/not-found-page').then(m => m.NotFoundPage) },
];
