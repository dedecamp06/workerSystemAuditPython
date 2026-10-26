"""Ponto de entrada da aplicacao.

Execucao local (Windows):
    python app.py
ou
    flask --app app run
"""
from auditoria_suporte import create_app

app = create_app()


if __name__ == "__main__":
    # debug=True apenas para uso local em desenvolvimento
    app.run(host="127.0.0.1", port=5000, debug=True)
