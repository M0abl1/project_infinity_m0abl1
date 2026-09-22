# Alterações

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
