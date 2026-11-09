"""Entrena CU22 de forma reproducible sin abrir ninguna base de datos."""
from app.config import BACKEND_ROOT
from app.analitica_ia.training import train


def main():
    result = train(BACKEND_ROOT / "app/analitica_ia/artifacts/modelos_v1.json",
                   BACKEND_ROOT / "data/sinteticos_analitica_v1.csv")
    print("Modelos entrenados y evaluados exclusivamente con escenarios sintéticos.")
    print("Versión:", result["version"], "; habilitado:", result["habilitado"])
    print("Métricas medidas:", result["metricas"])


if __name__ == "__main__":
    main()
