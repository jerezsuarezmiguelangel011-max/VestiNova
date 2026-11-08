"""Inferencia sobre JSON numérico verificado; no se cargan pickle ni modelos subidos."""
from collections import defaultdict
from functools import lru_cache
from hashlib import sha256
import json
from math import isfinite
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import func, select

from app.config import BACKEND_ROOT
from app.models import Existencia, VarianteProducto
from app.analitica_ia.queries import accepted_sales, period, scope
from app.analitica_ia.schemas import Filters
from app.analitica_ia.training import DATASET_ID, MODEL_VERSION, FEATURES
from app.analitica_ia.data_origin import purchase_origin

ARTIFACT = BACKEND_ROOT / "app/analitica_ia/artifacts/modelos_v1.json"
DATASET = BACKEND_ROOT / "data/sinteticos_analitica_v1.csv"


@lru_cache(maxsize=1)
def load_models():
    try:
        value = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        assert value["version"] == MODEL_VERSION and value["dataset"] == DATASET_ID
        assert value["origen"] == "sintetico" and value["habilitado"] is True
        assert value["features"] == FEATURES
        assert value["dataset_sha256"] == sha256(DATASET.read_bytes()).hexdigest()
        assert value["entrenamiento"] > 0 and value["evaluacion"] > 0
        assert all(isfinite(value["metricas"][name]) for name in ("mae", "rmse", "r2", "silhouette"))
        assert value["metricas"]["r2"] > 0 and value["metricas"]["silhouette"] > .25
        reg, groups = value["supervisado"], value["no_supervisado"]
        assert len(reg["media"]) == len(reg["escala"]) == len(reg["coeficientes"]) == 4
        assert len(groups["media"]) == len(groups["escala"]) == 3
        assert len(groups["centroides"]) == len(groups["etiquetas"]) == 3
        assert all(len(center) == 3 for center in groups["centroides"])
        numbers = [reg["intercepto"], *reg["media"], *reg["escala"], *reg["coeficientes"],
                   *groups["media"], *groups["escala"], *[number for center in groups["centroides"] for number in center]]
        assert all(isfinite(number) for number in numbers)
        assert all(number > 0 for number in [*reg["escala"], *groups["escala"]])
        return value
    except (OSError, KeyError, ValueError, TypeError, AssertionError):
        raise HTTPException(503, "Los modelos no están disponibles o no tienen una evaluación válida. Ejecuta python -m scripts.train_analytics.") from None


def infer(features, artifact):
    if len(features) != 4 or not all(isfinite(value) for value in features):
        raise ValueError("Entradas incompatibles.")
    # Límites de generación declarados: incluyen cero como ausencia real de demanda/stock.
    limits = [(0, 100), (0, 130), (0, 400), (0, 120)]
    if any(not low <= value <= high for value, (low, high) in zip(features, limits)):
        raise ValueError("Datos fuera del dominio de entrenamiento sintético.")
    reg, grouping = artifact["supervisado"], artifact["no_supervisado"]
    normalized = [(value-mean)/scale for value, mean, scale in zip(features, reg["media"], reg["escala"])]
    demand = max(0, reg["intercepto"] + sum(a*b for a, b in zip(normalized, reg["coeficientes"])))
    cluster_features = [features[index] for index in grouping["features_indexes"]]
    cluster_features = [(value-mean)/scale for value, mean, scale in zip(cluster_features, grouping["media"], grouping["escala"])]
    cluster_id = min(range(3), key=lambda index: sum((a-b)**2 for a, b in zip(cluster_features, grouping["centroides"][index])))
    return round(demand, 2), grouping["etiquetas"][cluster_id]


def dashboard(db, context, filters: Filters, analisis):
    artifact = load_models()
    ids, _ = scope(db, context, filters)
    start, end = period(filters)
    from datetime import date
    if end != date.today():
        raise HTTPException(422, "Las inferencias usan precio y existencias actuales: la fecha final debe ser hoy.")
    observations = defaultdict(lambda: {"days": set(), "operations": set(), "current": 0, "previous": 0})
    rows = accepted_sales(db, context, filters, ids, start, end)
    boundary = end - timedelta(days=6)
    previous_start = end - timedelta(days=13)
    for purchase, line, product in rows:
        if not product.activo or purchase.creado_en.date() < previous_start:
            continue
        observation = observations[product.id]
        observation["product"] = product
        observation["days"].add(purchase.creado_en.date())
        observation["operations"].add(purchase.id)
        observation["current" if purchase.creado_en.date() >= boundary else "previous"] += line.cantidad
    stock_rows = db.execute(select(VarianteProducto.producto_id, func.sum(Existencia.cantidad-Existencia.cantidad_comprometida), func.count(Existencia.variante_id))
        .join(Existencia, (Existencia.variante_id == VarianteProducto.id) & (Existencia.empresa_id == context.empresa_id))
        .where(VarianteProducto.empresa_id == context.empresa_id, Existencia.sucursal_id.in_(ids),
               VarianteProducto.producto_id.in_(list(observations))).group_by(VarianteProducto.producto_id)).all()
    stock = {identifier: quantity for identifier, quantity, _ in stock_rows}
    registered = {identifier: count for identifier, _, count in stock_rows}
    variant_counts = dict(db.execute(select(VarianteProducto.producto_id, func.count(VarianteProducto.id))
        .where(VarianteProducto.empresa_id == context.empresa_id, VarianteProducto.producto_id.in_(list(observations)))
        .group_by(VarianteProducto.producto_id)).all())
    output, omitted = [], []
    for product_id, observation in observations.items():
        product = observation["product"]
        if (end-start).days < 13 or len(observation["operations"]) < 3 or len(observation["days"]) < 2:
            omitted.append({"producto": product.nombre, "motivo": "Se requieren 14 días de ámbito, 3 compras aceptadas y 2 fechas distintas en las últimas dos semanas."})
            continue
        # No se infiere sobre existencias desconocidas como si estuvieran registradas.
        if product_id not in stock or registered[product_id] != variant_counts.get(product_id, 0) * len(ids):
            omitted.append({"producto": product.nombre, "motivo": "Faltan existencias registradas para alguna variante o sucursal seleccionada."})
            continue
        features = [observation["current"], observation["previous"], float(product.precio), stock[product_id]]
        try:
            predicted, grouping = infer(features, artifact)
        except ValueError:
            omitted.append({"producto": product.nombre, "motivo": "Los valores están fuera del dominio de los modelos sintéticos."})
            continue
        output.append({"producto_id": product_id, "producto": product.nombre,
                       "unidades_reales_7d": observation["current"], "unidades_reales_previas_7d": observation["previous"],
                       "stock_disponible_real": stock[product_id], "precio_real_bob": f"{product.precio:.2f}",
                       "demanda_estimada_7d": predicted if analisis != "agrupaciones" else None,
                       "agrupacion_estimada": grouping if analisis != "prediccion" else None})
    public_model = {key: artifact[key] for key in ("version", "dataset", "origen", "semilla", "muestras", "entrenamiento", "evaluacion", "division", "scikit_learn", "features", "metricas", "ejemplos_sinteticos", "limitaciones")}
    public_model["supervisado"] = {"nombre": artifact["supervisado"]["nombre"], "objetivo": artifact["supervisado"]["objetivo"]}
    public_model["no_supervisado"] = {"nombre": "KMeans", "grupos": 3}
    public_model["no_supervisado"]["etiquetas"] = [artifact["no_supervisado"]["etiquetas"][index] for index in sorted(range(3), key=lambda index: artifact["no_supervisado"]["centroides"][index][0])]
    public_model["preprocesamiento"] = "StandardScaler ajustado solamente con los escenarios de entrenamiento: (valor − media) / desviación. Ridge usa las cuatro variables; KMeans usa unidades de 7 días, precio y stock. Las ventas se agrupan por fecha UTC y solo se usa stock registrado en todo el ámbito consultado."
    return {"empresa": {"id": context.empresa_id, "nombre": context.empresa.nombre}, "analisis": analisis,
            "origen_datos": purchase_origin(row[0] for row in rows),
            "filtros": filters.model_copy(update={"desde": start, "hasta": end}).model_dump(mode="json"),
            "estado": "resultados" if output else "datos_insuficientes", "filas": output[:200], "omitidos": omitted[:200],
            "mensaje": "Resultados calculados con el historial seleccionado. Las estimaciones son experimentales." if output else "Todavía no hay un historial suficiente o compatible para este análisis. Revisa los criterios y los motivos indicados.",
            "modelo": public_model}
