class AppError(Exception):
    """Classe para tratamento de exceções do sistema"""
    def __inti__(self, message: str = "Ocorreu um erro no sistema."):
        super().__init__(message)
        self.message = message

class BusinessError(AppError):
    """Exceção para violação de regra de negócios"""
    pass

class UsuarioNaoEncontrado(BusinessError):
    """lançada quando não é encontrado o usuário no banco de dados"""
    def __init__(self, login: str = ""):
        mensagem = f"Usuário'{login}' não foi encontrado." if login else "Usuário não encontrado."
        super().__init__(mensagem)

class SenhaInvalida(BusinessError):
    """Lançado quando a senha informada é muito fraca"""
    def __init__(self, message: str = "Senha Inválida"):
        super().__init__(message)

    class AcessoNegado(AppError):
        """Lançado para tentativas de acesso não autorizadas"""
        def __init__(self, message: str = "Acesso Negado"):
            super().__init__(message)
