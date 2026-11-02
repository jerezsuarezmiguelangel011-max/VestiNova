import { HttpErrorResponse } from '@angular/common/http';
import { DatePipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { finalize } from 'rxjs';
import { CompanyService } from '../empresa/company.service';
import { MyPlan, PlatformPlanService } from './plan.service';

@Component({ selector: 'vn-my-plan-page', imports: [DatePipe], templateUrl: './my-plan-page.html', styleUrl: './platform.css' })
export class MyPlanPage {
  readonly companies = inject(CompanyService);
  private readonly api = inject(PlatformPlanService);
  private readonly destroyRef = inject(DestroyRef);
  readonly plan = signal<MyPlan | null>(null);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  ngOnInit(): void { this.reload(); }
  reload(): void {
    this.loading.set(true); this.error.set(null);
    this.api.myPlan().pipe(finalize(() => this.loading.set(false)), takeUntilDestroyed(this.destroyRef)).subscribe({
      next: value => this.plan.set(value),
      error: error => this.error.set(error instanceof HttpErrorResponse && typeof error.error?.detail === 'string' ? error.error.detail : 'No pudimos consultar el plan de esta empresa.'),
    });
  }
}
