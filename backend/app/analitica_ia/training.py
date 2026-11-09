"""Entrenamiento reproducible con datos exclusivamente sintéticos, sin conexión a PostgreSQL."""
import csv
from hashlib import sha256
import json
from pathlib import Path

FEATURES = ["unidades_7d", "unidades_previas_7d", "precio_bob", "stock_disponible"]
DATASET_ID = "escenarios-prendas-sinteticos-v1"
MODEL_VERSION = "vestinova-sintetico-v1"
SEED = 20261107


def train(output: Path, dataset_path: Path):
    import numpy as np
    from sklearn.cluster import KMeans
    from sklearn.linear_model import Ridge
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, silhouette_score
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler
    from importlib.metadata import version
    rng = np.random.default_rng(SEED)
    rows = []
    for i in range(3000):
        group = i % 3
        units = float(rng.uniform(*[(0, 8), (15, 35), (55, 100)][group]))
        previous = units * float(rng.uniform(.7, 1.3))
        price = float(rng.uniform(*[(30, 90), (80, 180), (180, 400)][group]))
        stock = float(rng.uniform(*[(50, 120), (15, 50), (0, 20)][group]))
        demand = max(0, .7*units + .3*previous + .03*stock - .005*price + float(rng.normal(0, 3)))
        rows.append([round(value, 4) for value in (units, previous, price, stock, demand)])
    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    with dataset_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow([*FEATURES, "demanda_7d_sintetica"])
        writer.writerows(rows)
    values = np.array(rows)
    train_ids, test_ids = train_test_split(np.arange(len(rows)), test_size=.2, random_state=SEED)
    scaler = StandardScaler().fit(values[train_ids, :4])
    model = Ridge(alpha=1).fit(scaler.transform(values[train_ids, :4]), values[train_ids, 4])
    predicted = np.maximum(0, model.predict(scaler.transform(values[test_ids, :4])))
    cluster_indexes = [0, 2, 3]
    cluster_scaler = StandardScaler().fit(values[train_ids][:, cluster_indexes])
    cluster_train = cluster_scaler.transform(values[train_ids][:, cluster_indexes])
    cluster_test = cluster_scaler.transform(values[test_ids][:, cluster_indexes])
    clusters = KMeans(n_clusters=3, random_state=SEED, n_init=10).fit(cluster_train)
    labels = clusters.predict(cluster_test)
    centers = cluster_scaler.inverse_transform(clusters.cluster_centers_)
    order = np.argsort(centers[:, 0])
    names = {int(index): name for index, name in zip(order, ["Rotación baja", "Rotación media", "Rotación alta"])}
    metrics = {"mae": float(mean_absolute_error(values[test_ids, 4], predicted)),
               "rmse": float(mean_squared_error(values[test_ids, 4], predicted)**.5),
               "r2": float(r2_score(values[test_ids, 4], predicted)),
               "silhouette": float(silhouette_score(cluster_test, labels)), "inercia_entrenamiento": float(clusters.inertia_)}
    artifact = {
        "version": MODEL_VERSION, "dataset": DATASET_ID, "origen": "sintetico",
        "dataset_sha256": sha256(dataset_path.read_bytes()).hexdigest(), "semilla": SEED,
        "muestras": len(rows), "entrenamiento": len(train_ids), "evaluacion": len(test_ids),
        "division": "80/20 aleatoria reproducible de escenarios independientes; no es validación temporal real",
        "scikit_learn": version("scikit-learn"), "features": FEATURES,
        "habilitado": metrics["r2"] > 0 and metrics["silhouette"] > .25,
        "metricas": metrics,
        "supervisado": {"nombre": "Ridge", "objetivo": "demanda estimada de unidades en próximos 7 días",
                        "media": scaler.mean_.tolist(), "escala": scaler.scale_.tolist(),
                        "coeficientes": model.coef_.tolist(), "intercepto": float(model.intercept_)},
        "no_supervisado": {"nombre": "KMeans", "features_indexes": cluster_indexes,
                           "media": cluster_scaler.mean_.tolist(), "escala": cluster_scaler.scale_.tolist(),
                           "centroides": clusters.cluster_centers_.tolist(),
                           "etiquetas": [names[index] for index in range(3)]},
        "rangos": [[float(values[:, index].min()), float(values[:, index].max())] for index in range(4)],
        "ejemplos_sinteticos": [{"entrada": values[index, :4].tolist(), "objetivo_sintetico": float(values[index, 4]),
                                  "estimacion": float(predicted[position])} for position, index in enumerate(test_ids[:5])],
        "limitaciones": ["Las métricas solo miden escenarios sintéticos; no acreditan precisión comercial.",
                         "No modela promociones, estacionalidad ni causas de demanda. No garantiza ventas ni existencias.",
                         "No se entrena con datos de otras empresas ni se escriben operaciones comerciales."]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    return artifact
