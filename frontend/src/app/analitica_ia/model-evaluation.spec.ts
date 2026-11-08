import { TestBed } from '@angular/core/testing';
import { EvaluationModel } from './analytics.service';
import { ModelEvaluation } from './model-evaluation';

const model: EvaluationModel = {
  version:'modelo-prueba-v1',dataset:'ejemplos-simulados',origen:'sintetico',muestras:3000,entrenamiento:2400,evaluacion:600,
  division:'80/20 de ejemplos independientes',preprocesamiento:'Escala ajustada solo con entrenamiento.',features:['unidades_7d','precio_bob'],
  metricas:{mae:2.37,rmse:2.95,r2:0.991,silhouette:0.616},
  ejemplos_sinteticos:[{entrada:[23.1,24,106,38],objetivo_sintetico:21.1,estimacion:24.1}],
  limitaciones:['Estas pruebas no acreditan precisión comercial.'],supervisado:{nombre:'Ridge',objetivo:'Demanda 7 días'},no_supervisado:{nombre:'KMeans',grupos:3},
};

describe('Ficha de evaluación comprensible',()=>{
  function render(){const fixture=TestBed.createComponent(ModelEvaluation);fixture.componentRef.setInput('model',model);fixture.detectChanges();return fixture;}
  it('explica aprendizaje y evaluación con cantidades reales del metadato',()=>{
    const fixture=render();const text=fixture.nativeElement.textContent;
    expect(fixture.nativeElement.querySelectorAll('.learning-steps li').length).toBe(3);
    expect(text).toContain('3.000');expect(text).toContain('2.400');expect(text).toContain('600');
    expect(text).toContain('2,37');expect(text).toContain('unidades de diferencia media');
    expect(fixture.nativeElement.querySelector('.sample-badge').textContent).toContain('datos simulados');
    expect(text).toContain('todavía deben validarse con ventas reales');
  });
  it('mantiene las métricas técnicas y la versión en un apartado desplegable',()=>{
    const fixture=render();const details=fixture.nativeElement.querySelector('.technical-details') as HTMLDetailsElement;
    expect(details.open).toBe(false);details.querySelector('summary')!.click();expect(details.open).toBe(true);
    expect(details.textContent).toContain('modelo-prueba-v1');expect(details.textContent).toContain('RMSE');
    expect(details.textContent).toContain('no es un porcentaje de aciertos');
  });
  it('compara objetivo y estimación con la diferencia del ejemplo',()=>{
    const fixture=render();const example=fixture.nativeElement.querySelector('.example-row');
    expect(example.textContent).toContain('21,10');expect(example.textContent).toContain('24,10');expect(example.textContent).toContain('3,00 unidades');
    for(const bar of example.querySelectorAll('.bar')) {const width=Number.parseFloat((bar as HTMLElement).style.width);expect(width).toBeGreaterThanOrEqual(0);expect(width).toBeLessThanOrEqual(100);}
    fixture.componentRef.setInput('model',{...model,ejemplos_sinteticos:[{entrada:[],objetivo_sintetico:21.104,estimacion:24.096}]});fixture.detectChanges();
    expect(example.textContent).toContain('21,10');expect(example.textContent).toContain('24,10');expect(example.textContent).toContain('3,00 unidades');
  });
  it('actualiza la explicación cuando cambia la versión de evaluación',()=>{
    const fixture=render();fixture.componentRef.setInput('model',{...model,version:'v2',muestras:100,entrenamiento:75,evaluacion:25});fixture.detectChanges();
    expect(fixture.componentInstance.trainingPercent()).toBe(75);expect(fixture.nativeElement.querySelector('.dataset-split').textContent).toContain('75 %');
    expect(fixture.nativeElement.querySelector('.technical-details').textContent).toContain('v2');
  });
});
