"""Comandos de linha de comando do sistema."""
from datetime import date, timedelta

import click
from flask.cli import with_appcontext

from .extensions import db
from .services.autenticacao_service import ErroValidacao, criar_usuario, existe_administrador


def registrar_comandos(app) -> None:
    app.cli.add_command(criar_admin)
    app.cli.add_command(criar_usuario_cmd)
    app.cli.add_command(listar_usuarios)
    app.cli.add_command(init_db)
    app.cli.add_command(dados_exemplo)


@click.command("criar-admin")
@click.option("--nome", prompt="Nome completo")
@click.option("--usuario", prompt="Login de acesso")
@click.option("--email", prompt="E-mail")
@click.password_option("--senha", prompt="Senha (minimo 8 caracteres)", confirmation_prompt=True)
@with_appcontext
def criar_admin(nome, usuario, email, senha):
    """Cria o primeiro usuario administrador do sistema."""
    try:
        novo = criar_usuario(nome, usuario, email, senha, perfil="admin")
    except ErroValidacao as erro:
        for mensagem in erro.erros:
            click.secho(f"  - {mensagem}", fg="red")
        raise SystemExit(1)
    click.secho(f"Administrador '{novo.usuario}' criado com sucesso.", fg="green")


@click.command("criar-usuario")
@click.option("--nome", prompt="Nome completo")
@click.option("--usuario", prompt="Login de acesso")
@click.option("--email", prompt="E-mail")
@click.option("--perfil", type=click.Choice(["admin", "auditor"]), default="auditor")
@click.password_option("--senha", prompt="Senha (minimo 8 caracteres)", confirmation_prompt=True)
@with_appcontext
def criar_usuario_cmd(nome, usuario, email, perfil, senha):
    """Cria um usuario adicional (auditor ou administrador)."""
    try:
        novo = criar_usuario(nome, usuario, email, senha, perfil=perfil)
    except ErroValidacao as erro:
        for mensagem in erro.erros:
            click.secho(f"  - {mensagem}", fg="red")
        raise SystemExit(1)
    click.secho(f"Usuario '{novo.usuario}' ({novo.rotulo_perfil}) criado.", fg="green")


@click.command("listar-usuarios")
@with_appcontext
def listar_usuarios():
    """Lista os usuarios cadastrados."""
    from .models import Usuario

    usuarios = db.session.scalars(db.select(Usuario).order_by(Usuario.usuario)).all()
    if not usuarios:
        click.echo("Nenhum usuario cadastrado. Use: flask --app app criar-admin")
        return
    for usuario in usuarios:
        estado = "ativo" if usuario.ativo else "inativo"
        click.echo(f"{usuario.id:>3} | {usuario.usuario:<20} | {usuario.rotulo_perfil:<14} | {estado}")


@click.command("init-db")
@with_appcontext
def init_db():
    """Cria o banco de dados e as tabelas (nao apaga dados existentes)."""
    db.create_all()
    click.secho("Banco de dados pronto.", fg="green")
    if not existe_administrador():
        click.secho(
            "Nenhum administrador cadastrado. Execute: flask --app app criar-admin",
            fg="yellow",
        )


@click.command("dados-exemplo")
@with_appcontext
def dados_exemplo():
    """Cria DADOS DE DEMONSTRACAO (cliente, criterios e atendimentos de exemplo).

    Uso opcional, apenas para conhecer o sistema. Os registros criados ficam
    identificados com o prefixo DEMO para que possam ser removidos depois.
    """
    from .models import Cliente
    from .services import atendimento_service, cliente_service

    if db.session.scalar(db.select(Cliente).where(Cliente.codigo == "DEMO")):
        click.secho("Os dados de demonstracao ja existem.", fg="yellow")
        return

    cliente = cliente_service.criar_cliente(
        {
            "nome": "DEMO - Telecom Exemplo",
            "codigo": "DEMO",
            "descricao": "Cliente de demonstracao criado pelo comando dados-exemplo.",
            "contato": "Central de Qualidade",
            "email": "qualidade@exemplo.com.br",
            "nota_minima": 70,
        }
    )

    criterios = [
        {
            "nome": "Saudacao inicial",
            "descricao": "O atendente deve se apresentar e saudar o cliente.",
            "peso": 1,
            "obrigatorio": "1",
            "termos_esperados": "bom dia, boa tarde, boa noite, meu nome e",
            "minimo_termos": 1,
        },
        {
            "nome": "Confirmacao de dados cadastrais",
            "descricao": "Confirmar a identidade do cliente antes de tratar o caso.",
            "peso": 2,
            "obrigatorio": "1",
            "termos_esperados": "confirmar seus dados, confirmando seus dados, cpf, data de nascimento",
            "minimo_termos": 1,
        },
        {
            "nome": "Registro de protocolo",
            "descricao": "Informar o numero de protocolo do atendimento.",
            "peso": 1.5,
            "termos_esperados": "protocolo, numero do atendimento",
            "minimo_termos": 1,
        },
        {
            "nome": "Cordialidade (sem termos inadequados)",
            "descricao": "Nao utilizar linguagem inadequada ou informal em excesso.",
            "peso": 2,
            "obrigatorio": "1",
            "termos_esperados": "por favor, obrigado, obrigada, as ordens",
            "termos_proibidos": "nao e problema meu, calma ai, ta louco",
            "minimo_termos": 1,
        },
        {
            "nome": "Oferta de solucao de cobranca",
            "descricao": "Aplicavel somente quando o atendimento trata de cobranca.",
            "peso": 1.5,
            "termos_esperados": "segunda via, estorno, reembolso, negociacao",
            "termos_contexto": "fatura, cobranca, pagamento, boleto",
            "permite_nao_aplicavel": "1",
            "minimo_termos": 1,
        },
    ]
    from .services import criterio_service

    for dados in criterios:
        criterio_service.criar_criterio(cliente, dados)

    hoje = date.today()
    atendimentos = [
        {
            "protocolo": "DEMO-0001",
            "atendente": "Maria Souza",
            "data_atendimento": (hoje - timedelta(days=3)).strftime("%Y-%m-%d"),
            "canal": "telefone",
            "conteudo": (
                "Atendente: Bom dia, central de suporte, meu nome e Maria. Em que posso ajudar? "
                "Cliente: Bom dia, meu acesso a internet esta fora desde ontem. "
                "Atendente: Entendo, vou confirmando seus dados, por favor me informe o CPF e a "
                "data de nascimento. Cliente: Informado. Atendente: Obrigada. Identifiquei uma "
                "instabilidade na regiao e ja abri o reparo. O protocolo do atendimento e 884512. "
                "Posso ajudar em algo mais? Cliente: Nao, obrigado. Atendente: As ordens, bom dia!"
            ),
        },
        {
            "protocolo": "DEMO-0002",
            "atendente": "Joao Lima",
            "data_atendimento": (hoje - timedelta(days=2)).strftime("%Y-%m-%d"),
            "canal": "chat",
            "conteudo": (
                "Cliente: minha fatura veio duplicada neste mes, preciso resolver a cobranca. "
                "Atendente: ja verifiquei aqui, vou solicitar o estorno e envio a segunda via do "
                "boleto correto. Cliente: e quanto tempo demora? Atendente: em ate cinco dias "
                "uteis. Cliente: ok. Atendente: encerrando o chamado."
            ),
        },
        {
            "protocolo": "DEMO-0003",
            "atendente": "Carla Dias",
            "data_atendimento": (hoje - timedelta(days=1)).strftime("%Y-%m-%d"),
            "canal": "email",
            "conteudo": (
                "Cliente: preciso de ajuda com o roteador. Atendente: calma ai, isso nao e problema "
                "meu, procura o fabricante. Cliente: mas o aparelho foi fornecido por voces. "
                "Atendente: ja respondi. Encerro aqui o contato."
            ),
        },
    ]
    for dados in atendimentos:
        atendimento_service.criar_atendimento(cliente, dados)

    click.secho(
        "Dados de demonstracao criados: 1 cliente (DEMO), 5 criterios e 3 atendimentos. "
        "Nenhuma auditoria foi executada automaticamente.",
        fg="green",
    )
