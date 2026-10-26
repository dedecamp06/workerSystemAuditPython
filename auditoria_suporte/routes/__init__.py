"""Blueprints (rotas) da aplicacao."""
from .atendimentos import bp as atendimentos_bp
from .auditorias import bp as auditorias_bp
from .auth import bp as auth_bp
from .clientes import bp as clientes_bp
from .criterios import bp as criterios_bp
from .dashboard import bp as dashboard_bp
from .resultados import bp as resultados_bp

BLUEPRINTS = (
    auth_bp,
    dashboard_bp,
    clientes_bp,
    atendimentos_bp,
    criterios_bp,
    auditorias_bp,
    resultados_bp,
)
