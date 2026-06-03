from typing import List, Optional
from core.extensions import db
from core.exceptions import UsuarioNaoEncontrado
from models import Usuario

class UsuarioRepository:
    @staticmethod
    def buscar_por_id(usuario_id: int) -> Optional[Usuario]:
        return db.session.get(Usuario, usuario_id)

    @staticmethod
    def buscar_por_login(login: str) -> Optional[Usuario]:
        return Usuario.query.filter_by(login=login).first()

    @staticmethod
    def listar_todos_admins() -> list[Usuario]:
        return Usuario.query.filter_by(is_admin=True).order_by(Usuario.login.asc()).all()

    @staticmethod
    def contar_outros_superadmins(excluir_id: int) -> int:
        return Usuario.query.filter(
            Usuario.is_superadmin == True,
            Usuario.id != excluir_id
        ).count()

    @staticmethod
    def salvar(usuario: Usuario) -> None:
        db.session.add(usuario)
        db.session.commit()

    @staticmethod
    def excluir(usuario: Usuario) -> None:
        db.session.delete(usuario)
        db.session.commit()
