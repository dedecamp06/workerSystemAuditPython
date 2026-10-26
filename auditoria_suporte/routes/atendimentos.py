"""Cadastro, consulta e importacao de atendimentos."""
from datetime import date

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from ..extensions import db
from ..models import Atendimento, Auditoria, Cliente
from ..seguranca import login_required
from ..services import atendimento_service
from ..services.atendimento_service import CABECALHO_CSV, ErroImportacao

bp = Blueprint("atendimentos", __name__, url_prefix="/atendimentos")

MODELO_CSV = (
    CABECALHO_CSV
    + "\n"
    + "ATD-2026-001;Maria Souza;2026-10-20;telefone;"
    + '"Cliente: bom dia, meu acesso esta bloqueado. Atendente: bom dia! '
    "Meu nome e Maria, vou verificar. Confirmando seus dados... Realizei o "
    'desbloqueio e o acesso foi testado. Protocolo registrado. Posso ajudar em algo mais?"'
    + "\n"
    + "ATD-2026-002;Joao Lima;20/10/2026;chat;"
    + '"Cliente: minha fatura veio em duplicidade. Atendente: vou analisar o '
    'historico e retorno o contato em ate 24 horas."'
    + "\n"
)


def _clientes(ativos=False):
    consulta = db.select(Cliente).order_by(Cliente.nome)
    if ativos:
        consulta = consulta.where(Cliente.ativo.is_(True))
    return db.session.scalars(consulta).all()


@bp.get("/")
@login_required
def listar():
    cliente_id = request.args.get("cliente_id", type=int)
    busca = (request.args.get("busca") or "").strip()
    situacao = request.args.get("situacao") or "todos"
    pagina = request.args.get("pagina", type=int, default=1)

    consulta = db.select(Atendimento)
    if cliente_id:
        consulta = consulta.where(Atendimento.cliente_id == cliente_id)
    if busca:
        padrao = f"%{busca}%"
        consulta = consulta.where(
            db.or_(Atendimento.protocolo.ilike(padrao), Atendimento.atendente.ilike(padrao))
        )
    existe_auditoria = db.exists().where(Auditoria.atendimento_id == Atendimento.id)
    if situacao == "pendentes":
        consulta = consulta.where(~existe_auditoria)
    elif situacao == "auditados":
        consulta = consulta.where(existe_auditoria)

    paginacao = db.paginate(
        consulta.order_by(Atendimento.data_atendimento.desc(), Atendimento.id.desc()),
        page=pagina,
        per_page=15,
        error_out=False,
    )

    return render_template(
        "atendimentos/listar.html",
        paginacao=paginacao,
        atendimentos=paginacao.items,
        clientes=_clientes(),
        cliente_id=cliente_id,
        busca=busca,
        situacao=situacao,
    )


@bp.route("/novo", methods=["GET", "POST"])
@login_required
def novo():
    erros = []
    dados = {
        "cliente_id": request.args.get("cliente_id", type=int) or "",
        "data_atendimento": date.today().strftime("%Y-%m-%d"),
    }
    if request.method == "POST":
        dados = request.form.to_dict()
        cliente = db.session.get(Cliente, request.form.get("cliente_id", type=int) or 0)
        if cliente is None:
            erros.append("Selecione um cliente valido.")
        elif not cliente.ativo:
            erros.append("O cliente selecionado esta inativo.")
        else:
            try:
                atendimento = atendimento_service.criar_atendimento(cliente, dados)
                flash(
                    f"Atendimento {atendimento.protocolo} cadastrado com sucesso.", "sucesso"
                )
                return redirect(
                    url_for("atendimentos.detalhe", atendimento_id=atendimento.id)
                )
            except ValueError as erro:
                db.session.rollback()
                erros = erro.args[0] if isinstance(erro.args[0], list) else [str(erro)]
    return render_template(
        "atendimentos/form.html",
        atendimento=None,
        dados=dados,
        erros=erros,
        clientes=_clientes(ativos=True),
    )


@bp.get("/<int:atendimento_id>")
@login_required
def detalhe(atendimento_id):
    atendimento = db.get_or_404(Atendimento, atendimento_id)
    return render_template("atendimentos/detalhe.html", atendimento=atendimento)


@bp.route("/<int:atendimento_id>/editar", methods=["GET", "POST"])
@login_required
def editar(atendimento_id):
    atendimento = db.get_or_404(Atendimento, atendimento_id)

    # Regra explicita: atendimentos ja auditados nao podem ser alterados,
    # para que o conteudo avaliado permaneca igual ao registrado na auditoria.
    if atendimento.auditado:
        flash(
            f"O atendimento {atendimento.protocolo} ja foi auditado e nao pode mais "
            "ser alterado. Cadastre um novo atendimento caso o conteudo tenha mudado.",
            "aviso",
        )
        return redirect(url_for("atendimentos.detalhe", atendimento_id=atendimento.id))

    erros = []
    dados = {
        "cliente_id": atendimento.cliente_id,
        "protocolo": atendimento.protocolo,
        "atendente": atendimento.atendente,
        "data_atendimento": atendimento.data_atendimento.strftime("%Y-%m-%d"),
        "canal": atendimento.canal,
        "conteudo": atendimento.conteudo,
    }
    if request.method == "POST":
        dados = request.form.to_dict()
        dados["cliente_id"] = atendimento.cliente_id  # o vinculo nao muda
        try:
            atendimento_service.atualizar_atendimento(atendimento, dados)
            flash("Atendimento atualizado com sucesso.", "sucesso")
            return redirect(url_for("atendimentos.detalhe", atendimento_id=atendimento.id))
        except ValueError as erro:
            db.session.rollback()
            erros = erro.args[0] if isinstance(erro.args[0], list) else [str(erro)]

    return render_template(
        "atendimentos/form.html",
        atendimento=atendimento,
        dados=dados,
        erros=erros,
        clientes=_clientes(),
    )


@bp.post("/<int:atendimento_id>/excluir")
@login_required
def excluir(atendimento_id):
    atendimento = db.get_or_404(Atendimento, atendimento_id)
    if atendimento.auditado:
        flash(
            "Atendimentos auditados nao podem ser excluidos: o historico de auditoria "
            "deve ser preservado.",
            "erro",
        )
        return redirect(url_for("atendimentos.detalhe", atendimento_id=atendimento.id))
    protocolo = atendimento.protocolo
    db.session.delete(atendimento)
    db.session.commit()
    flash(f"Atendimento {protocolo} excluido.", "sucesso")
    return redirect(url_for("atendimentos.listar"))


@bp.route("/importar", methods=["GET", "POST"])
@login_required
def importar():
    erros = []
    resultado = None
    dados = {
        "cliente_id": request.args.get("cliente_id", type=int) or "",
        "data_atendimento": date.today().strftime("%Y-%m-%d"),
    }

    if request.method == "POST":
        dados = request.form.to_dict()
        cliente = db.session.get(Cliente, request.form.get("cliente_id", type=int) or 0)
        arquivo = request.files.get("arquivo")

        if cliente is None:
            erros.append("Selecione o cliente ao qual os atendimentos pertencem.")
        elif not cliente.ativo:
            erros.append("O cliente selecionado esta inativo.")

        if arquivo is None or not (arquivo.filename or "").strip():
            erros.append("Selecione um arquivo CSV ou TXT.")

        if not erros:
            try:
                resultado = atendimento_service.importar_arquivo(
                    cliente,
                    arquivo,
                    current_app.config["EXTENSOES_IMPORTACAO"],
                    atendente_padrao=dados.get("atendente"),
                    data_padrao=dados.get("data_atendimento"),
                )
                if resultado["importados"]:
                    flash(
                        f"{resultado['importados']} atendimento(s) importado(s) para "
                        f"{cliente.nome}.",
                        "sucesso",
                    )
                if resultado["erros"]:
                    flash(
                        f"{len(resultado['erros'])} registro(s) com erro nao foram importados.",
                        "aviso",
                    )
                if not resultado["importados"] and not resultado["erros"]:
                    flash("Nenhum registro encontrado no arquivo.", "aviso")
            except ErroImportacao as erro:
                erros.append(str(erro))

    return render_template(
        "atendimentos/importar.html",
        clientes=_clientes(ativos=True),
        dados=dados,
        erros=erros,
        resultado=resultado,
        cabecalho_csv=CABECALHO_CSV,
    )


@bp.get("/modelo.csv")
@login_required
def modelo_csv():
    return Response(
        MODELO_CSV,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=modelo_atendimentos.csv"},
    )
