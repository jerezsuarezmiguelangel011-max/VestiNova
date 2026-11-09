import { Component, computed, input } from '@angular/core';
import { EvaluationModel } from './analytics.service';

@Component({selector:'vn-model-evaluation',templateUrl:'./model-evaluation.html',styleUrl:'./model-evaluation.css'})
export class ModelEvaluation {
  readonly model = input.required<EvaluationModel>();
  readonly total = computed(() => this.model().muestras ?? this.model().entrenamiento + this.model().evaluacion);
  readonly trainingPercent = computed(() => 100*this.model().entrenamiento/Math.max(1,this.total()));
  readonly exampleMaximum = computed(() => Math.max(1,...this.model().ejemplos_sinteticos.flatMap(row => [row.objetivo_sintetico,row.estimacion])));
  readonly featureNames: Record<string,string> = {unidades_7d:'Ventas de la última semana',unidades_previas_7d:'Ventas de la semana anterior',precio_bob:'Precio de la prenda',stock_disponible:'Existencias disponibles'};
  format(value:number,digits=2): string { return new Intl.NumberFormat('es-BO',{minimumFractionDigits:digits,maximumFractionDigits:digits}).format(value); }
  width(value:number): number { return 100*value/this.exampleMaximum(); }
  difference(expected:number,estimated:number): string { return this.format(Math.abs(Math.round(expected*100)-Math.round(estimated*100))/100); }
}
