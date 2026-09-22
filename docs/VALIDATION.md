# Validação

## Retenção de backups, 22/09/2026

- Política solicitada: manter dez ZIPs no total, incluindo snapshots.
- Windows: 44 testes aprovados e 1 teste exclusivo de Linux ignorado.
- Ubuntu isolado: a prévia apontou somente o ZIP mais antigo; 42 testes da
  versão anterior ao reforço final passaram antes da ativação.
- Antes da ativação, foi preservado e validado um arquivo da versão anterior do
  código do painel. Os mundos e backups preservados não foram incluídos nele.
- FTB Backups 2 configurado com `retention_mode=MAX_BACKUPS` e `max_backups=10`.
- O painel confirmou retenção ativa, 10 backups disponíveis e Minecraft pronto
  após a primeira limpeza. A exclusão foi registrada no SQLite de auditoria.
- A cópia mais antiga foi removida permanentemente; não há lixeira ou
  recuperação pelo painel. O nome operacional não foi versionado.

## Aba spark, 22/09/2026

- Windows: 32 testes aprovados e 1 teste exclusivo de Linux ignorado.
- Ubuntu: 33 testes aprovados em pasta isolada, sem restauração de mundo real.
- Relatório real do spark Forge 1.10.53: coleta de 60 segundos salva localmente,
  formato protobuf lido no próprio servidor e soma de percentuais diretos validada.
  O arquivo e suas informações operacionais não fazem parte do repositório.
- Interface com fixtures sintéticas: 390 × 900 e 1440 × 900, claro/escuro,
  busca, ordenação, expansão dos métodos e ausência de overflow/erros JavaScript.
- Coleta não reinicia o Minecraft. Nenhuma exclusão de entidades ou alteração de
  mundo/mods foi realizada para validar a aba.
- Documentação do formato, limites, API e segurança em `SPARK.md` e `SECURITY.md`.

### Implantação

- Código publicado em `main`, commit inicial `a51385e`, em histórico novo.
- Arquivo de implantação gerado diretamente do commit (`git archive`).
- Cópia anterior do código preservada no servidor, arquivo tar verificado e
  checksum SHA-256 calculado antes da instalação.
- Serviço do painel ativo após atualização; 33 testes repetidos com sucesso.
- Acesso à rota spark por origem sem identidade autorizada retorna 403.
- Uptime e PID do Minecraft preservados; somente o painel web foi reiniciado.
- A leitura do relatório real foi validada no host do jogo. Após autorização
  explícita do proprietário, o navegador também confirmou o carregamento do
  relatório real, expansão dos detalhes e ausência de overflow em 390 px.
  Conteúdo real e snapshots do navegador não foram versionados.
- Revisão de 29 arquivos antes do primeiro push: sem arquivos operacionais,
  credenciais detectadas ou endereços reais. Exemplos e testes usam valores
  fictícios; autor Git usa endereço público `noreply`.

## Testes realizados

- Resultado: 18 testes aprovados no Windows e 19 no Ubuntu (incluindo a restauração de nomes com dois-pontos, específicos do Linux).

- Windows: testes unitários de restauração em mundos temporários, preservação do mundo anterior, rollback, bloqueio de criação acidental de mundo vazio, caminhos maliciosos, links ZIP, backup incompleto, hash divergente, métricas idempotentes, identidade e CSRF.
- Interface: Playwright em 390 × 900 e 1440 × 900, claro/escuro, sem overflow horizontal. Navegação, filtro de logs, conteúdo do backup e confirmação de restauração verificados com API simulada; nenhum comando real de restauração foi emitido.
- Ubuntu: serviço de usuário ativo; `Linger=yes`; porta vinculada somente ao IP Tailscale; identidade do proprietário resolvida com `tailscale whois`.
- Integração de leitura real: processo Java/PM2, protocolo Minecraft, 10 ZIPs existentes e verificação de integridade do ZIP mais recente. O FTB grava nomes como `world/data/dankstorage:max_id.dat`: permitidos no Linux; extração Windows recusa nomes incompatíveis.
- Requisição do próprio servidor sem identidade pessoal autorizada recebe 403.

## Acesso externo validado em 18/09/2026

A política da tailnet recebeu uma regra específica para permitir TCP 8787 do login do proprietário ao IP Tailscale do servidor. As demais regras foram preservadas. Após salvar, o acesso externo à API identificou corretamente o proprietário e retornou os 10 backups. A página real abriu no navegador com métricas e logs.

Não foi necessário alterar o UFW. O painel permanece vinculado somente ao IP Tailscale, sem exposição na LAN. A validação de identidade no backend continua ativa independentemente da política da rede.

## Limites da validação

Não foi realizado stop/restart do Minecraft real nem restauração sobre o mundo em produção. As operações destrutivas foram validadas exclusivamente em diretórios temporários e com controles simulados. A captura futura de métricas foi implementada; backups antigos não recebem valores inventados.
