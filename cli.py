# cli.py
import argparse
from control_actas_local import get_backend

def main():
    parser = argparse.ArgumentParser(description="Control Actas - runner")
    parser.add_argument("--modo", choices=["normal", "critico"], default="normal")
    parser.add_argument("--proyecto", required=True)
    parser.add_argument("--carpeta_mes", required=True)
    args = parser.parse_args()

    backend = get_backend(args.modo)

    BASE_ROOT = backend["BASE_ROOT"]
    correr_todo = backend["correr_todo"]

    # En ambos modos, correr_todo debe existir
    # Ajusta firma según tu pipeline (si requiere valores_referencia, etc.)
    # Aquí lo dejo genérico; si tu correr_todo pide más cosas, lo adaptamos.
    info = correr_todo(BASE_ROOT, args.proyecto, args.carpeta_mes)

    print("OK")
    print(info)

if __name__ == "__main__":
    main()
