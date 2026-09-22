# Alterações

## 2026-09-22 - Retenção

- Retenção automática opt-in dos dez backups concluídos mais recentes, incluindo
  snapshots, com verificação prévia de integridade e auditoria de exclusões.
- Bloqueio compartilhado com inspeções, downloads, comandos e restaurações.
- Política nativa do FTB Backups 2 ajustável para `MAX_BACKUPS` com limite 10.
- Status e última verificação exibidos na aba Backups.
- Comportamento fail-closed para catálogo inválido, cópia incompleta, ZIP alterado
  ou nome sem data segura; nesses casos a exclusão é adiada.

## 2026-09-22

- Publicação independente do painel, sem histórico de outros projetos.
- Aba spark com coleta local de 60 segundos pelo PM2, lista de relatórios,
  tempo direto e incluindo chamadas, busca por componente e detalhes de métodos.
- Parser protobuf com validação de estrutura, limites de tamanho, cache limitado
  e exclusão de configurações/identidade da resposta HTTP.
- Testes de atribuição, dupla contagem, formato inválido, autorização e comando fixo.
- Documentação de instalação, segurança, API e limitações dos relatórios.
- Exemplos de configuração sem endereço real do servidor; arquivos operacionais
  e relatórios excluídos do versionamento.

## Versão inicial

- Status, métricas Java, logs e comandos PM2 com autorização Tailscale.
- Consulta e verificação de backups do modpack; restauração com preservação do
  mundo atual e confirmação explícita.
- Registro aproximado de CPU/RAM ao detectar novos backups e auditoria SQLite.
- Interface responsiva com tema automático e demonstração local somente leitura.
