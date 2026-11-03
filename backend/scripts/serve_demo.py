"""Arranca FastAPI en modo demo usando exclusivamente vestinova_pruebas local."""
import uvicorn

from scripts.demo_environment import use_demo_database


def main():
    use_demo_database()
    print("VestiNova DEMO -> PostgreSQL local: vestinova_pruebas")
    print("La base vestinova_mvp se conserva sin cambios.")
    uvicorn.run("app.main:create_app", factory=True, host="127.0.0.1", port=8001)


if __name__ == "__main__":
    main()
