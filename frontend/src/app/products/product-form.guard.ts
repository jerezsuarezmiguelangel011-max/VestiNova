import { CanDeactivateFn } from '@angular/router';
import type { ProductFormPage } from './product-form';

export const productFormLeaveGuard: CanDeactivateFn<ProductFormPage> = component => component.canLeave();
