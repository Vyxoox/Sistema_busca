from typing import TYPE_CHECKING, Any

from core.extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, UTC


if TYPE_CHECKING:
    class _ConstrutorDeclarativo:
        """Stub de tipagem: o SQLAlchemy injeta o construtor __init__(**kw)
        nos models em tempo de execucao. Para Pylance/mypy esse construtor
        nao existe, o que gera falsos "No parameter named ..." em toda
        instanciacao de model (app.py, routes/, services/). Esta classe
        existe apenas na checagem estatica e nao altera o runtime."""

        def __init__(self, **kw: Any) -> None: ...
else:
    class _ConstrutorDeclarativo:
        pass


class Usuario(UserMixin, db.Model, _ConstrutorDeclarativo):
    __tablename__ = 'usuarios'

    id = db.Column(db.Integer, primary_key=True)
    login = db.Column(db.String(80), unique=True, nullable=False)
    hash_senha = db.Column(db.String(255), nullable=False)
    perfil = db.Column(db.String(20), nullable=False)
    permissoes = db.Column(db.Text, nullable=True)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    is_superadmin = db.Column(db.Boolean, default=False, nullable=False)

    def set_password(self, password: str) -> None:
        self.hash_senha = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.hash_senha, password)

    def get_id(self) -> str:
        return str(self.id)


class Funcionario(db.Model, _ConstrutorDeclarativo):
    __tablename__ = 'funcionarios'

    id = db.Column(db.Integer, primary_key=True)

    nome_completo = db.Column(db.String(200), nullable=False)
    cpf = db.Column(db.String(11), unique=True, nullable=False)
    rg = db.Column(db.String(20), nullable=True)
    cin = db.Column(db.String(30), nullable=True)
    titulo_eleitor = db.Column(db.String(20), nullable=True)
    pis_pasep = db.Column(db.String(20), nullable=True)

    data_nasc = db.Column(db.Date, nullable=True)
    endereco_residencial = db.Column(db.String(255), nullable=True)
    telefone_pessoal = db.Column(db.String(20), nullable=True)
    contato_emergencia = db.Column(db.String(20), nullable=True)
    email_pessoal = db.Column(db.String(150), nullable=True)
    foto_perfil = db.Column(db.String(255), nullable=True)

    email_institucional = db.Column(db.String(150), nullable=True)
    ramal = db.Column(db.String(20), nullable=True)

    vinculo = db.Column(db.String(20), nullable=False)  # SERVIDOR / TERCEIRIZADO
    tipo = db.Column(db.String(30), nullable=True)     # EFETIVO / CELETISTA / etc.
    subtipo_vinculo = db.Column(db.String(50), nullable=True)
    forma_ingresso = db.Column(db.String(30), nullable=True)
    prontuario_funcional = db.Column(db.String(50), nullable=True)
    matricula = db.Column(db.String(50), unique=True, nullable=True)

    cargo_exercicio = db.Column(db.String(200), nullable=True)
    cargo_origem = db.Column(db.String(200), nullable=True)

    lotacao = db.Column(db.String(200), nullable=True)
    area = db.Column(db.String(200), nullable=True)
    coordenadoria = db.Column(db.String(200), nullable=True)

    data_ingresso_der = db.Column(db.Date, nullable=True)
    data_inicio = db.Column(db.Date, nullable=True)
    data_admissao = db.Column(db.Date, nullable=True)

    situacao = db.Column(db.String(200), nullable=True)
    data_desligamento = db.Column(db.Date, nullable=True)

    doe_portaria = db.Column(db.String(200), nullable=True)

    empresa_contratada = db.Column(db.String(200), nullable=True)
    numero_contrato = db.Column(db.String(200), nullable=True)
    gestor_contrato = db.Column(db.String(200), nullable=True)
    fiscal_tecnico = db.Column(db.String(200), nullable=True)
    fiscal_administrativo = db.Column(db.String(200), nullable=True)
    preposto = db.Column(db.String(200), nullable=True)

    ativo = db.Column(db.Boolean, nullable=True, default=True)
    data_criacao = db.Column(db.DateTime, default=datetime.now)
    data_atualizacao = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)


class LogAuditoria(db.Model, _ConstrutorDeclarativo):
    __tablename__ = 'logs_auditoria'

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=True, index=True)
    usuario_login = db.Column(db.String(80), nullable=True, index=True)
    acao = db.Column(db.String(120), nullable=False, index=True)
    categoria = db.Column(db.String(50), nullable=False, default='seguranca', index=True)
    status = db.Column(db.String(20), nullable=False, default='sucesso', index=True)
    recurso = db.Column(db.String(80), nullable=True, index=True)
    recurso_id = db.Column(db.String(80), nullable=True, index=True)
    metodo_http = db.Column(db.String(10), nullable=True)
    rota = db.Column(db.String(255), nullable=True)
    ip_origem = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    detalhes = db.Column(db.Text, nullable=True)
    criado_em = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC).replace(tzinfo=None), index=True)
