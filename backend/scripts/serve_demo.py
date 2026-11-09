"""Arranca FastAPI en modo demo usando exclusivamente vestinova_pruebas local."""
import argparse
import uvicorn

from scripts.demo_environment import use_demo_database


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host',choices=['127.0.0.1','0.0.0.0'],default='127.0.0.1')
    args=parser.parse_args()
    use_demo_database()
    print("VestiNova DEMO -> PostgreSQL local: vestinova_pruebas")
    print("La base vestinova_mvp se conserva sin cambios.")
    uvicorn.run("app.main:create_app", factory=True, host=args.host, port=8001)


if __name__ == "__main__":
    main()
