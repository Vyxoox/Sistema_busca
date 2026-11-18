# ============================================================
# diagnostico_porta.ps1 - por que o app.py nao faz bind na porta?
#
# Sintoma: python app.py morre com
#   PermissionError: [WinError 10013] Foi feita uma tentativa de
#   acesso a um soquete de uma maneira que e proibida pelas
#   permissoes de acesso
#
# O 10013 (WSAEACCES) e NEGACAO DE BIND - diferente de "porta em
# uso" (esse e o 10048). Causas tipicas no Windows, em ordem:
#   1. A porta caiu dentro de uma FAIXA EXCLUIDA do Windows:
#      Hyper-V/WSL/NAT reservam blocos dinamicos que mudam a cada
#      reboot - 8080 e vitima classica;
#   2. Antivirus/protecao de endpoint bloqueando o bind do python;
#   3. (raro) politica de rede/terceiro reservando a porta.
#
# Uso (na raiz do projeto; NAO precisa de admin):
#   powershell -ExecutionPolicy Bypass -File scripts\diagnostico_porta.ps1
#
# O script APENAS DIAGNOSTICA - nao altera nada no sistema.
# ============================================================

$ErrorActionPreference = 'Continue'

function Test-Bind {
    # Tenta abrir um listener de verdade e devolve OK ou o erro exato.
    param([string]$Ip, [int]$Porta)
    try {
        $listener = New-Object System.Net.Sockets.TcpListener(
            ([System.Net.IPAddress]::Parse($Ip)), $Porta)
        $listener.Start()
        $listener.Stop()
        return @{ Ok = $true; Erro = '' }
    }
    catch {
        $ex = $_.Exception
        while ($ex -and $ex -isnot [System.Net.Sockets.SocketException]) {
            $ex = $ex.InnerException
        }
        if ($ex) {
            return @{ Ok = $false;
                      Erro = ('{0} (WinError {1})' -f $ex.SocketErrorCode, $ex.ErrorCode) }
        }
        return @{ Ok = $false; Erro = $_.Exception.Message }
    }
}

# --- 0. porta/host alvo (le o .env, como o app.py faz) ---------
$raiz = Split-Path -Parent $PSScriptRoot
$arquivoEnv = Join-Path $raiz '.env'
$portaAlvo = 8080
$hostEnv = ''

if (Test-Path $arquivoEnv) {
    foreach ($linha in Get-Content $arquivoEnv) {
        if ($linha -match '^\s*PORT\s*=\s*(\d+)')     { $portaAlvo = [int]$Matches[1] }
        if ($linha -match '^\s*HOST\s*=\s*([^\s#]+)') { $hostEnv = $Matches[1] }
    }
    $hostMostrado = $hostEnv
    if (-not $hostMostrado) { $hostMostrado = '0.0.0.0 (padrao do app.py)' }
    Write-Host (".env lido: PORT={0}  HOST={1}" -f $portaAlvo, $hostMostrado)
}
else {
    Write-Host ("'.env' nao encontrado em {0} - usando os padroes do app.py (PORT=8080, HOST=0.0.0.0)" -f $arquivoEnv)
}

Write-Host ''
Write-Host ('== Diagnostico da porta {0} ==' -f $portaAlvo) -ForegroundColor Cyan
Write-Host ''

# --- 1. algo ja esta escutando na porta? -----------------------
$ouvintes = Get-NetTCPConnection -LocalPort $portaAlvo -State Listen -ErrorAction SilentlyContinue
if ($ouvintes) {
    Write-Host '1) JA TEM PROCESSO ESCUTANDO nesta porta:' -ForegroundColor Yellow
    foreach ($c in $ouvintes) {
        $proc = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
        $nome = if ($proc) { $proc.ProcessName } else { '?' }
        Write-Host ("   PID {0} - {1} (local {2}:{3})" -f
            $c.OwningProcess, $nome, $c.LocalAddress, $c.LocalPort)
    }
    Write-Host '   Se for um python antigo travado: Stop-Process -Id <PID> -Force'
}
else {
    Write-Host '1) Nenhum processo escutando nesta porta (ok).'
}
Write-Host ''

# --- 2. faixas de portas excluidas pelo Windows ----------------
$faixas = @()
$saidaNetsh = netsh interface ipv4 show excludedportrange protocol=tcp 2>$null
foreach ($linha in $saidaNetsh) {
    if ($linha -match '^\s*(\d{1,5})\s+(\d{1,5})\s*$') {
        $faixas += [pscustomobject]@{ Inicio = [int]$Matches[1]; Fim = [int]$Matches[2] }
    }
}

Write-Host ('2) Faixas de portas reservadas pelo Windows (Hyper-V/WSL/NAT): {0} faixa(s).' -f $faixas.Count)
$naFaixa = $faixas | Where-Object { $portaAlvo -ge $_.Inicio -and $portaAlvo -le $_.Fim }
if ($naFaixa) {
    Write-Host ("   >>> CAUSA ACHADA: a porta {0} esta DENTRO da faixa reservada {1}-{2}!" -f
        $portaAlvo, $naFaixa[0].Inicio, $naFaixa[0].Fim) -ForegroundColor Red
    Write-Host '   O Windows recusa QUALQUER bind nessa faixa (WinError 10013),' -ForegroundColor Red
    Write-Host '   mesmo como Administrador. Correcoes no final deste relatorio.' -ForegroundColor Red
}
else {
    Write-Host '   Nenhuma faixa cobre a porta alvo (ok).'
}
Write-Host ''

# --- 3. teste real de bind -------------------------------------
Write-Host '3) Teste real de bind (o mesmo que o waitress faz):'
$testaLoop = Test-Bind -Ip '127.0.0.1' -Porta $portaAlvo
$testaAny  = Test-Bind -Ip '0.0.0.0'   -Porta $portaAlvo

if ($testaLoop.Ok) { Write-Host ("   127.0.0.1:{0} -> OK"        -f $portaAlvo) -ForegroundColor Green }
else               { Write-Host ("   127.0.0.1:{0} -> FALHOU: {1}" -f $portaAlvo, $testaLoop.Erro) -ForegroundColor Red }

if ($testaAny.Ok)  { Write-Host ("   0.0.0.0:{0}   -> OK"        -f $portaAlvo) -ForegroundColor Green }
else               { Write-Host ("   0.0.0.0:{0}   -> FALHOU: {1}" -f $portaAlvo, $testaAny.Erro) -ForegroundColor Red }
Write-Host ''

# --- 4. portas alternativas livres ------------------------------
Write-Host '4) Portas alternativas livres agora (bind testado em 0.0.0.0 e 127.0.0.1):'
$livres = @()
foreach ($candidata in 8081, 8085, 8090, 9080, 9095) {
    $t1 = Test-Bind -Ip '127.0.0.1' -Porta $candidata
    $t2 = Test-Bind -Ip '0.0.0.0'   -Porta $candidata
    if ($t1.Ok -and $t2.Ok) {
        $livres += $candidata
        Write-Host ("   {0} -> livre" -f $candidata) -ForegroundColor Green
    }
    else {
        Write-Host ("   {0} -> indisponivel" -f $candidata) -ForegroundColor DarkGray
    }
}
Write-Host ''

# --- 5. veredito ------------------------------------------------
Write-Host '== VEREDITO E CORRECOES ==' -ForegroundColor Cyan

if ($naFaixa) {
    Write-Host ''
    Write-Host 'CAUSA: faixa reservada do Windows cobre a porta (cenario 1).' -ForegroundColor Yellow
    Write-Host 'Escolha UMA das correcoes:'
    Write-Host ''
    Write-Host '  A) Fixa definitiva (PowerShell COMO ADMIN, depois reiniciar o PC):'
    Write-Host '       netsh int ipv4 set dynamicport tcp start=49152 num=16384'
    Write-Host '     O Windows para de reservar faixas abaixo de 49152 e o 8080'
    Write-Host '     volta a funcionar de forma estavel.'
    Write-Host ''
    Write-Host '  B) Liberacao rapida (COMO ADMIN; pode ser re-reservada no proximo boot):'
    Write-Host '       net stop winnat'
    Write-Host '       net start winnat'
    Write-Host '     Rode o python app.py logo apos.'
    Write-Host ''
    Write-Host '  C) Trocar a porta do app (sem admin; lembre de alinhar o Caddy):'
    $sugestao = if ($livres) { $livres[0] } else { 8081 }
    Write-Host ("       1. No .env: PORT={0}" -f $sugestao)
    Write-Host ("       2. No Caddyfile: reverse_proxy 127.0.0.1:{0}" -f $sugestao)
    Write-Host '       3. Reiniciar o app (e o Caddy, se ja instalado:'
    Write-Host '          C:\caddy\caddy.exe reload --config C:\caddy\Caddyfile).'
}
elseif (-not $testaLoop.Ok -and -not $testaAny.Ok) {
    if ($ouvintes) {
        Write-Host ''
        Write-Host 'CAUSA: a porta ja esta ocupada por outro processo (lista acima).' -ForegroundColor Yellow
        Write-Host 'Encerre o processo (Stop-Process -Id <PID> -Force) e suba o app de novo.'
    }
    else {
        Write-Host ''
        Write-Host 'CAUSA PROVAVEL: antivirus/protecao de endpoint bloqueando o bind' -ForegroundColor Yellow
        Write-Host 'do python (sem faixa reservada e sem processo na porta).'
        Write-Host ''
        Write-Host '  1. Teste uma vez num terminal COMO ADMIN:'
        Write-Host ('       python app.py   (bind na {0})' -f $portaAlvo)
        Write-Host '     Se subir como admin, e politica de permissao: peca ao TI para'
        Write-Host '     liberar o python.exe do projeto (bind de rede local).'
        Write-Host '  2. Ou troque a porta (opcao C acima).'
    }
}
elseif ($testaLoop.Ok -and (-not $testaAny.Ok)) {
    Write-Host ''
    Write-Host 'Bind no loopback OK, mas 0.0.0.0 bloqueado (protecao de endpoint).' -ForegroundColor Yellow
    Write-Host 'Como o Lote 9 deixa o waitress SO no loopback mesmo'
    Write-Host '(.env: HOST=127.0.0.1), voce ja pode seguir o corte HTTPS:'
    Write-Host '  HOST=127.0.0.1 e TRUST_XFF=true no .env, com o Caddy na frente.'
}
elseif ($testaLoop.Ok -and $testaAny.Ok) {
    Write-Host ''
    Write-Host 'O bind nesta porta FUNCIONA agora - o problema era transitorio' -ForegroundColor Green
    Write-Host '(ex.: faixa reservada no boot anterior). Rode python app.py de novo.'
}

Write-Host ''
Write-Host 'Nota: o E2E usa porta livre automatica (python scripts\e2e_https.py) -'
Write-Host 'se ele mostra 9/9, o app esta sadio e o problema e so a porta.'
