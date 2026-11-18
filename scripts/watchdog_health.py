#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""Watchdog de saude do Sistema de Busca.

Verifica http://localhost:<PORT>/healthz e, quando o servico esta fora do ar,
envia um e-mail de alerta usando as mesmas configuracoes SMTP do .env do app.

Projete para rodar pelo Agendador de Tarefas do Windows a cada 5 minutos:

    python scripts\watchdog_health.py

Comportamento:
  - Servico saudavel            -> sai com codigo 0 (sem e-mail)
  - Servico falhou (1a vez)     -> espera WATCHDOG_FALHAS_CONSECUTIVAS cheques
                                   seguidos antes de alarmar (evita falso
                                   positivo em reinicio curto)
  - Alarme com cooldown         -> reavisa no maximo 1x a cada
                                   WATCHDOG_COOLDOWN_MIN minutos
  - Recuperacao                 -> envia e-mail de "voltou ao ar" se havia
                                   alarme aberto

Flags uteis:
  --check-only : apenas verifica e imprime, nao envia e-mail nem grava estado
  --url X      : sobrescreve a URL verificada (padrao http://localhost:<PORT>/healthz)

Codigos de saida: 0 = saudavel | 1 = fora do ar | 2 = erro de uso/config

Somente biblioteca padrao — nenhuma dependencia do projeto e importada
(para o watchdog funcionar mesmo com o app inteiro caido).
"""
from __future__ import annotations

import argparse
import json
import os
import smtplib
import socket
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ARQUIVO_ESTADO = RAIZ / "logs" / "watchdog_estado.json"


def carregar_env() -> None:
    """Carrega o .env da raiz sem depender de python-dotenv."""
    caminho = RAIZ / ".env"
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8", errors="replace").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        chave = chave.strip()
        valor = valor.strip().strip('"').strip("'")
        os.environ.setdefault(chave, valor)


def verificar(url: str, timeout: float) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "watchdog-sistema-busca/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            corpo = resp.read(200).decode("utf-8", "replace")
            if resp.status == 200:
                return True, f"HTTP 200 {corpo.strip()}"
            return False, f"HTTP {resp.status}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code} (servidor respondeu, rota com erro)"
    except Exception as exc:  # timeout, recusa de conexao, DNS...
        return False, f"{type(exc).__name__}: {exc}"


def ler_estado() -> dict:
    try:
        return json.loads(ARQUIVO_ESTADO.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "ok", "falhas_consecutivas": 0, "ultima_notificacao": None}


def gravar_estado(estado: dict) -> None:
    try:
        ARQUIVO_ESTADO.parent.mkdir(parents=True, exist_ok=True)
        ARQUIVO_ESTADO.write_text(
            json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        print(f"[watchdog] AVISO: nao consegui gravar estado ({exc})")


def enviar_email_alerta(assunto: str, corpo: str) -> bool:
    host = os.getenv("SMTP_HOST", "").strip()
    if not host:
        print("[watchdog] SMTP_HOST vazio no .env — alerta registrado apenas no estado/log.")
        return False

    destinatario = os.getenv("WATCHDOG_EMAIL_DESTINO", "").strip() or os.getenv("SMTP_USER", "").strip()
    usuario = os.getenv("SMTP_USER", "").strip()
    if not destinatario:
        print("[watchdog] Sem destinatario (WATCHDOG_EMAIL_DESTINO/SMTP_USER) — e-mail nao enviado.")
        return False

    msg = EmailMessage()
    msg["Subject"] = assunto
    msg["From"] = usuario or "watchdog@localhost"
    msg["To"] = destinatario
    msg.set_content(corpo)

    porta = int(os.getenv("SMTP_PORT", "587"))
    usa_ssl = os.getenv("SMTP_USE_SSL", "false").strip().lower() == "true"
    usa_tls = os.getenv("SMTP_USE_TLS", "true").strip().lower() == "true"
    timeout_smtp = int(os.getenv("SMTP_TIMEOUT", "10"))

    try:
        if usa_ssl:
            servidor = smtplib.SMTP_SSL(host, porta, timeout=timeout_smtp)
        else:
            servidor = smtplib.SMTP(host, porta, timeout=timeout_smtp)
            if usa_tls:
                servidor.starttls()
        senha = os.getenv("SMTP_PASSWORD", "")
        if usuario and senha:
            servidor.login(usuario, senha)
        servidor.send_message(msg)
        servidor.quit()
        print(f"[watchdog] E-mail enviado para {destinatario}")
        return True
    except Exception as exc:
        print(f"[watchdog] Falha ao enviar e-mail: {type(exc).__name__}: {exc}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Watchdog de saude do Sistema de Busca")
    parser.add_argument("--check-only", action="store_true", help="nao envia e-mail nem grava estado")
    parser.add_argument("--url", default=None, help="URL alternativa do healthz")
    args = parser.parse_args()

    carregar_env()

    porta = os.getenv("PORT", "8080").strip()
    url = args.url or os.getenv("WATCHDOG_URL") or f"http://localhost:{porta}/healthz"
    timeout_http = float(os.getenv("WATCHDOG_TIMEOUT_HTTP", "10"))
    falhas_para_alarme = max(1, int(os.getenv("WATCHDOG_FALHAS_CONSECUTIVAS", "2")))
    cooldown = timedelta(minutes=max(1, int(os.getenv("WATCHDOG_COOLDOWN_MIN", "30"))))

    ok, detalhe = verificar(url, timeout_http)
    agora = datetime.now()
    estado = ler_estado()
    host = socket.gethostname()

    if ok:
        print(f"[watchdog] OK  {url}  ({detalhe})")
        if estado.get("status") == "falha" and not args.check_only:
            corpo = (
                f"O servico voltou ao ar.\n\n"
                f"Maquina: {host}\nURL: {url}\n"
                f"Verificacao: {agora:%d/%m/%Y %H:%M:%S}\n"
                f"Resposta: {detalhe}\n"
            )
            enviar_email_alerta(
                "[Sistema de Busca] RECUPERADO: servico voltou ao ar", corpo
            )
        if not args.check_only:
            gravar_estado(
                {
                    "status": "ok",
                    "falhas_consecutivas": 0,
                    "ultima_verificacao": agora.isoformat(),
                    "ultima_notificacao": estado.get("ultima_notificacao"),
                }
            )
        return 0

    falhas = int(estado.get("falhas_consecutivas", 0)) + 1
    print(f"[watchdog] FALHA ({falhas}x seguidas): {url} -> {detalhe}")

    if args.check_only:
        return 1

    deve_alarmar = (
        falhas >= falhas_para_alarme
        and (
            not estado.get("ultima_notificacao")
            or agora - datetime.fromisoformat(estado["ultima_notificacao"]) >= cooldown
        )
    )

    if deve_alarmar:
        corpo = (
            f"O Sistema de Busca esta fora do ar.\n\n"
            f"Maquina: {host}\nURL verificada: {url}\n"
            f"Falhas consecutivas: {falhas}\n"
            f"Verificacao: {agora:%d/%m/%Y %H:%M:%S}\n"
            f"Erro: {detalhe}\n\n"
            f"Como investigar:\n"
            f"  1. logs\\app.log na maquina {host}\n"
            f"  2. Servico do Windows / console do waitress esta aberto?\n"
            f"  3. GET /healthz manual no navegador\n"
        )
        enviado = enviar_email_alerta(
            "[Sistema de Busca] FORA DO AR: /healthz falhando", corpo
        )
        if enviado:
            estado["ultima_notificacao"] = agora.isoformat()
    else:
        print("[watchdog] Alarme em espera (cooldown ou contagem insuficiente).")

    estado.update(
        {
            "status": "falha",
            "falhas_consecutivas": falhas,
            "ultima_verificacao": agora.isoformat(),
        }
    )
    gravar_estado(estado)
    return 1


if __name__ == "__main__":
    sys.exit(main())
