# Painel privado do Minecraft

Aplicação independente para o Project Infinity. Interface responsiva em HTML/CSS/JavaScript, API FastAPI e SQLite próprio para auditoria e métricas. Não depende de outros sistemas e não altera o agendamento do FTB Backups 2.

## Acesso e segurança

O processo escuta somente no IPv4 Tailscale configurado, porta 8787. Cada requisição resolve a identidade do endereço TCP real com `tailscale whois --json` e compara `UserProfile.LoginName` com `PANEL_OWNER`. Outros usuários, dispositivos com tags e endereços LAN são recusados. Cabeçalhos de identidade e proxy do navegador não são confiados. O Uvicorn roda com `proxy_headers=False` e um único worker.

O acesso padrão é HTTP dentro da conexão criptografada do Tailscale. Não há certificado HTTPS instalado por este projeto. Não publicar na internet, não colocar atrás de proxy sem redesenhar a autenticação e não liberar o modo demonstração fora de loopback. Configure nas políticas da tailnet a permissão TCP 8787 somente para o proprietário. O painel executa como `mine`, sem root e sem acesso ao Docker. Comandos PM2 são fixos, há token anti-CSRF, confirmação e exclusão mútua das operações. O titular do usuário Linux `mine` continua tendo as permissões normais sobre os próprios arquivos.

## Funções

- Consulta de status Java em 2 segundos; protocolo Minecraft e PM2 em cerca de 10 segundos. Um processo em execução não significa jogo pronto.
- Jogadores e versão retornados pelo status do Minecraft, sem configurar RCON.
- CPU do processo Java (100% por núcleo), memória RSS, uptime e reinícios PM2.
- Logs recentes (até 128 KiB), busca, filtro, pausa e download. Redação básica de campos de senha/token; não é garantia de remoção de toda informação sensível de logs de terceiros.
- Start/stop/restart do processo PM2 `project-infinity`; parada exige `kill_timeout >= 120000`. O PM2 pode forçar a parada após esse limite. Não há terminal ou comandos arbitrários na API.
- Backups ZIP existentes de `backups/`: data, tamanho, catálogo FTB, conteúdo (primeiras 150 entradas), download, CRC e SHA-1 quando disponível no catálogo do modpack. SHA-1 aqui serve para comparação com o catálogo existente, não como assinatura de autenticidade.
- Monitoramento do surgimento de novos ZIPs: guarda CPU/RAM do Java e CPU/RAM global em SQLite. Medição aproximada no primeiro avistamento, normalmente em até um ciclo de 2 segundos; consultas lentas ao PM2/protocolo podem aumentar o atraso. Não captura retroativamente backups existentes ou criados enquanto o painel estava desligado.
- Histórico das últimas 100 ações, com retenção de até 10.000 registros.
- Retenção opcional de dez backups concluídos, com validação, auditoria e bloqueio
  durante downloads/restaurações. [Política e configuração](docs/RETENTION.md).
- Aba Desempenho: coleta spark local de 60 segundos, ranking por componente,
  busca e métodos principais. [Formato, API e limitações](docs/SPARK.md).

## Restauração

1. Exige confirmação com o nome do arquivo no backend e digitação de `RESTAURAR` na interface.
2. Valida formato, catálogo, CRC, limites de extração e espaço disponível. Só aceita ZIP completo contendo `world/level.dat` e entradas sob `world/`. Caminhos externos, links, entradas duplicadas e arquivos criptografados são recusados.
3. Extrai para diretório temporário no mesmo disco, antes de parar o jogo.
4. Para o processo PM2 e confirma a ausência do Java do diretório configurado.
5. Move o mundo atual para `.panel-recovery/<data-id>/world` e instala o mundo preparado. Se a segunda renomeação falhar, tenta recolocar o mundo anterior.
6. Mantém o jogo parado. O administrador usa Iniciar após conferir o resultado.

Mods, configuração do servidor e ZIPs originais não são substituídos. As configurações contidas dentro do próprio mundo (como `world/serverconfig`) acompanham a restauração. O agendamento/retentor do modpack continua responsável pelos backups. Cópias `.panel-recovery` não são removidas automaticamente: consomem espaço e permitem recuperação manual. Falha elétrica entre renomeações pode exigir recolocar a cópia preservada com o jogo parado. Não reinicie o serviço do painel durante uma restauração.

ZIPs fora do catálogo só ficam disponíveis após 120 segundos sem alteração; isso é uma heurística. A integridade é conferida novamente antes de restaurar. Não há exclusão manual individual; a retenção automática opt-in remove permanentemente os excedentes quando configurada. Consulte `docs/RETENTION.md`.

## Executar no Windows para visualização

```powershell
# Execute na raiz deste repositório.
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:PANEL_DEMO = "1"
$env:PANEL_BIND = "127.0.0.1"
$env:PANEL_STATE = "$PWD/.panel-state"
.\.venv\Scripts\python.exe run.py
```

Abra `http://127.0.0.1:8787`. A demonstração é somente leitura e não inventa métricas. O modo operacional depende de Linux, Tailscale e PM2.

## Instalar no Ubuntu

Copie esta pasta para `/home/mine/minecraft-panel`, sem `.venv`, estado ou credenciais. Crie ambiente virtual próprio e instale `requirements.txt`. Configure `.env` a partir de `.env.example` com o login real Tailscale do proprietário. O arquivo é ignorado pelo Git. Permissões recomendadas: `.env` 600, diretório de estado 700.

```bash
python3 -m venv /home/mine/minecraft-panel/.venv
/home/mine/minecraft-panel/.venv/bin/python -m pip install -r /home/mine/minecraft-panel/requirements.txt
mkdir -p /home/mine/.config/systemd/user
cp deploy/minecraft-panel.service /home/mine/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now minecraft-panel
```

Execute como `mine`. Para iniciar o serviço do usuário mesmo sem sessão aberta, um administrador deve habilitar `sudo loginctl enable-linger mine` uma vez. Sem isso, não há garantia de inicialização após reiniciar o computador. O serviço não inicia o jogo automaticamente; preserva seu mecanismo atual.

```bash
systemctl --user status minecraft-panel
journalctl --user -u minecraft-panel -n 100 --no-pager
```

## Contrato da API

Todas as rotas requerem identidade autorizada. `GET /api/status` retorna status, prontidão, métricas, operação atual e token CSRF; `GET /api/logs` e `/api/logs/download` retornam o trecho recente; `GET /api/backups` lista ZIPs; `GET /api/backups/{name}/content` lista entradas; `GET /api/backups/{name}/download` baixa um ZIP; `GET /api/audit` retorna o histórico.

`POST /api/actions`, com `X-Panel-CSRF`, aceita `{action, backup?, confirm?}`. Ações: `start`, `stop`, `restart`, `verify`, `restore`, `spark`. Para stop/restart, `confirm` deve ser igual à ação; para restore, deve ser igual ao nome do ZIP. Responde 202; acompanhar `job` em `/api/status`. 403 indica acesso/CSRF; 409 indica operação concorrente; 429 exige aguardar. Não há controle de energia do Ubuntu. Rotas de relatórios spark estão documentadas em [docs/SPARK.md](docs/SPARK.md).

## Testes

```powershell
.\.venv\Scripts\python.exe -m pip install pytest==9.1.1 httpx==0.28.1
.\.venv\Scripts\python.exe -m pytest tests -q
node --check panel/static/app.js
```

Testes de restauração usam mundos temporários isolados. Nunca use o mundo real para validar restauração. Não há migração Alembic: o SQLite é exclusivo do painel.

O teste de interface está em `tests/browser-check.js` e pode ser executado com
`playwright-cli run-code --filename=tests/browser-check.js` a partir
da raiz do repositório, em uma sessão aberta no painel local. Ele intercepta a API
com dados fictícios e nunca restaura um mundo real. Evidências e limitações da
implantação estão em [docs/VALIDATION.md](docs/VALIDATION.md).

### Liberação da rede

Se a porta 8787 não responder pelo Tailscale, conferir as duas camadas:

1. Política da tailnet: permitir TCP 8787 do login do proprietário para o dispositivo do servidor, preservando as demais regras.
2. Firewall Ubuntu: se UFW estiver ativo e bloqueando essa porta, liberar somente a interface Tailscale:

```bash
sudo ufw allow in on tailscale0 to any port 8787 proto tcp comment 'Minecraft panel via Tailscale'
```

Não liberar a porta nas interfaces LAN/WAN ou encaminhá-la no roteador. A API também valida o proprietário em cada requisição, mesmo que uma política de rede mais ampla já exista.
