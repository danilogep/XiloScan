@echo off
REM ============================================================================
REM  XiloScan - refaz o dataset_lpf.json a partir do cache, SEM baixar nada.
REM
REM  Use depois de atualizar o parser. Le o HTML das paginas ja guardado em
REM  data\.cache, reprocessa tudo e mostra um relatorio de cobertura.
REM
REM  Como usar: de dois cliques neste arquivo, ou rode no cmd:
REM      cd /d C:\caminho\para\xiloscan
REM      refazer_dataset.bat
REM ============================================================================
setlocal
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo.
echo === XiloScan: reprocessando o dataset a partir do cache ===
echo Pasta: %CD%
echo.

REM --- 1. achar o Python -------------------------------------------------
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo [ERRO] Python nao encontrado no PATH.
    echo        Instale em https://www.python.org/downloads/ e marque
    echo        "Add python.exe to PATH" na primeira tela do instalador.
    goto :fim
)
echo [1/5] Python: %PY%
%PY% --version
echo.

REM --- 2. conferir que estamos na raiz do projeto ------------------------
if not exist "scraper\lpf_scraper.py" (
    echo [ERRO] Nao achei scraper\lpf_scraper.py.
    echo        Este .bat precisa estar na RAIZ do projeto, ao lado das
    echo        pastas scraper\, backend\ e data\.
    goto :fim
)
echo [2/5] Projeto encontrado.

REM --- 3. cache presente? ------------------------------------------------
if not exist "data\.cache" (
    echo.
    echo [ERRO] data\.cache nao existe - nao ha o que reprocessar offline.
    echo        Para baixar o catalogo do zero ^(precisa de internet^):
    echo            %PY% -m scraper.lpf_scraper --out data
    goto :fim
)
echo [3/5] Cache encontrado em data\.cache
echo.

REM --- 4. dependencias ---------------------------------------------------
echo [4/5] Conferindo dependencias...
%PY% -c "import httpx, bs4, lxml" >nul 2>&1
if errorlevel 1 (
    echo       instalando httpx / beautifulsoup4 / lxml ...
    %PY% -m pip install --quiet --disable-pip-version-check -r scraper\requirements.txt
    if errorlevel 1 (
        echo [ERRO] Falha ao instalar as dependencias.
        goto :fim
    )
)
echo       ok.
echo.

REM --- 5. reprocessar + merge + relatorio --------------------------------
echo [5/5] Reprocessando ^(offline, sem rede^)...
echo.
%PY% -m scraper.lpf_scraper --offline --out data
if errorlevel 1 (
    echo.
    echo [ERRO] O scraper terminou com erro. Nada foi sobrescrito.
    goto :fim
)

echo.
echo --- aplicando a camada MCB ---
%PY% -m scraper.mcb_merge
if errorlevel 1 (
    echo [ERRO] O merge falhou - veja a mensagem acima.
    goto :fim
)

echo.
echo --- relatorio de cobertura ---
%PY% -m scraper.relatorio
if errorlevel 1 (
    echo.
    echo O dataset ainda esta incompleto. Veja os campos marcados acima.
    goto :fim
)

echo.
echo === PRONTO === data\dataset_lpf.json regenerado.

:fim
echo.
pause
endlocal
