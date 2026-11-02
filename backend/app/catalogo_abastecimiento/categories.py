"""CU04: categorías propias de cada catálogo empresarial."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.organizacion_empresarial.audit import record_audit_event
from app.db import get_db
from app.models import CategoriaProducto
from app.tenancy import TenantContext, require_permission


router = APIRouter(prefix="/api/admin/categorias", tags=["CU04 · Catálogo de prendas"])


class CategoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CategoryCreate(CategoryInput):
    nombre: str = Field(min_length=2, max_length=100)
    descripcion: str = Field(default="", max_length=500)


class CategoryPatch(CategoryInput):
    nombre: str | None = Field(default=None, min_length=2, max_length=100)
    descripcion: str | None = Field(default=None, max_length=500)
    activo: bool | None = Field(default=None, strict=True)

    @model_validator(mode="after")
    def validate_changes(self):
        if not self.model_fields_set or any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Envía al menos un cambio no nulo.")
        return self


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    empresa_id: int
    nombre: str
    descripcion: str
    activo: bool


def get_category(db: Session, context: TenantContext, category_id: int, *, active: bool = False) -> CategoriaProducto:
    category = db.scalar(select(CategoriaProducto).where(
        CategoriaProducto.id == category_id,
        CategoriaProducto.empresa_id == context.empresa_id,
    ))
    if category is None or (active and not category.activo):
        raise HTTPException(404, "La categoría no está disponible en esta empresa.")
    return category


@router.get("", response_model=list[CategoryResponse])
def list_categories(context: TenantContext = Depends(require_permission("catalogo.consultar")), db: Session = Depends(get_db)):
    return db.scalars(select(CategoriaProducto).where(
        CategoriaProducto.empresa_id == context.empresa_id,
    ).order_by(CategoriaProducto.nombre_clave, CategoriaProducto.id)).all()


@router.post("", response_model=CategoryResponse, status_code=201)
def create_category(payload: CategoryCreate, context: TenantContext = Depends(require_permission("catalogo.gestionar", mutation=True)), db: Session = Depends(get_db)):
    category = CategoriaProducto(
        empresa_id=context.empresa_id,
        nombre=payload.nombre,
        nombre_clave=payload.nombre.casefold(),
        descripcion=payload.descripcion,
        activo=True,
    )
    db.add(category)
    try:
        db.flush()
        record_audit_event(db, context, accion="categoria.creada", entidad="categoria", entidad_id=category.id,
                           detalles={"nombre": category.nombre})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe una categoría con ese nombre en esta empresa.") from None
    return category


@router.patch("/{categoria_id}", response_model=CategoryResponse)
def update_category(categoria_id: int, payload: CategoryPatch,
                    context: TenantContext = Depends(require_permission("catalogo.gestionar", mutation=True)),
                    db: Session = Depends(get_db)):
    category = get_category(db, context, categoria_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(category, field, value)
    if "nombre" in changes:
        category.nombre_clave = category.nombre.casefold()
    record_audit_event(db, context, accion="categoria.actualizada", entidad="categoria", entidad_id=category.id,
                       detalles={"campos": sorted(changes), "nombre": category.nombre})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe una categoría con ese nombre en esta empresa.") from None
    return category
