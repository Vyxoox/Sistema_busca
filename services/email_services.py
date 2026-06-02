import smtplib

from email.message import EmailMessage
from flask import current_app

def enviar_email(destinatario, assunto, corpo):

    msg = EmailMessage()

    msg["Subject"] = assunto
    msg["From"] = current_app.config["SMTP_USER"]
    msg["To"] = destinatario

    msg.set_content(corpo)

    servidor = None
    try:

        if current_app.config["SMTP_USE_SSL"]:

            servidor = smtplib.SMTP_SSL(
                current_app.config["SMTP_HOST"],
                current_app.config["SMTP_PORT"],
                timeout=current_app.config["SMTP_TIMEOUT"]
            )
        else:

            servidor = smtplib.SMTP(
                current_app.config["SMTP_HOST"],
                current_app.config["SMTP_PORT"],
                timeout=current_app.config["SMTP_TIMEOUT"]
            )

            current_app.logger.info("Conectado ao servidor SMTP")

            if current_app.config["SMTP_USE_TLS"]:
                current_app.logger.info("Iniciando TLS")
                servidor.starttls()
                current_app.logger.info("TLS iniciado")

        if(
            current_app.config["SMTP_USER"]
            and current_app.config["SMTP_PASSWORD"]
        ):
            current_app.logger.info("Realizando login SMTP")

            servidor.login(
                current_app.config["SMTP_USER"],
                current_app.config["SMTP_PASSWORD"]
            )
            current_app.logger.info("Login SMTP concluído")

        servidor.send_message(msg)
        current_app.logger.info(
            f"E-mail enviado para {destinatario}"
        )

        return True

    except Exception as e:

        current_app.logger.error(
            f"Erro SMTP ao enviar para {destinatario}: {str(e)}"
        )
        return False

    finally:
        if servidor:
            servidor.quit()
