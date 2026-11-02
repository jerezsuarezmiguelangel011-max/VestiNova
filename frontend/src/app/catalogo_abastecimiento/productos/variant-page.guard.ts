import { CanDeactivateFn } from '@angular/router';
import type { VariantPage } from './variant-page';

export const variantLeaveGuard: CanDeactivateFn<VariantPage> = component => component.canLeave();
