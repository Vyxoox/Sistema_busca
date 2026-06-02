import os
from PIL import Image, UnidentifiedImageError
import magic
from flask import current_app

Image.MAX_IMAGE_PIXELS = 20_000_000
MIMES_PERMITIDOS = ['image/jpeg', 'image/png','image/webp']

def caminho_foto_funcionario(root_path, funcionario_id):
    return os.path.join(root_path, 'static', 'fotos_funcionarios', f'{int(funcionario_id)}.jpg')

def salvar_foto(root_path, file, funcionario_id):
    if not file or file.filename == '':
        return

    pasta = os.path.join(root_path, 'static', 'fotos_funcionarios')
    os.makedirs(pasta, exist_ok=True)

    caminho = caminho_foto_funcionario(root_path, funcionario_id)

    mime = magic.from_buffer(
        file.read(2048),
        mime=True
    )

    file.seek(0)

    if mime not in MIMES_PERMITIDOS:
        raise ValueError("Tipo de arquivo inválido.")

    try:
        img = Image.open(file)
    except UnidentifiedImageError:
        raise ValueError("Imagem Inválida.")
    except Exception as e:
        current_app.logger.exception(
            f"ERRO REAL: {type(e).__name__}"
        )
        raise ValueError("Erro ao processar imagem.")
    img = img.convert("RGB")
    img.thumbnail((500, 500))
    img.save(caminho, "JPEG", quality=85, optimize=True)

def remover_foto(root_path, funcionario_id):
    caminho = caminho_foto_funcionario(root_path, funcionario_id)
    if os.path.exists(caminho):
        os.remove(caminho)
        return True
    return False
