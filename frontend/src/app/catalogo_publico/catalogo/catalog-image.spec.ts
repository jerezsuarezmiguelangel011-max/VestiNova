import { TestBed } from '@angular/core/testing';
import { CatalogImage } from './catalog-image';

describe('Imagen pública de prenda', () => {
  async function setup(url: string | null) {
    await TestBed.configureTestingModule({ imports: [CatalogImage] }).compileComponents();
    const fixture = TestBed.createComponent(CatalogImage);
    fixture.componentRef.setInput('name', 'Camisa de lino');
    fixture.componentRef.setInput('url', url);
    fixture.detectChanges();
    return { fixture, root: fixture.nativeElement as HTMLElement };
  }

  it('muestra una alternativa identificada sin inventar una fotografía si no hay imagen', async () => {
    const { root } = await setup(null);
    expect(root.querySelector('img')).toBeNull();
    expect(root.querySelector('[role="img"]')?.getAttribute('aria-label')).toBe('Sin imagen de Camisa de lino');
    expect(root.textContent).toContain('Imagen no disponible');
  });

  it('utiliza la imagen recibida con texto alternativo y recupera el estado si falla', async () => {
    const { fixture, root } = await setup('https://imagenes.test/camisa.jpg');
    const image = root.querySelector('img') as HTMLImageElement;
    expect(image.getAttribute('src')).toBe('https://imagenes.test/camisa.jpg');
    expect(image.alt).toBe('Camisa de lino');
    image.dispatchEvent(new Event('error'));
    fixture.detectChanges();
    expect(root.querySelector('img')).toBeNull();
    expect(root.textContent).toContain('Imagen no disponible');
    fixture.componentRef.setInput('url', 'https://imagenes.test/camisa-nueva.jpg');
    fixture.detectChanges();
    expect(root.querySelector('img')?.getAttribute('src')).toBe('https://imagenes.test/camisa-nueva.jpg');
  });
});
