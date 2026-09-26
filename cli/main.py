"""Point d'entrée de l'exécutable (PyInstaller) ; le code vit dans le paquet hadi/."""
from hadi.app import app

if __name__ == "__main__":
    app(prog_name="hadi")
