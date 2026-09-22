# Retenção de backups

Ativação explícita: `PANEL_BACKUP_KEEP=10` no ambiente do painel. O padrão é `0`
(desativado). A demonstração nunca executa limpeza. O limite global inclui snapshots.

O painel verifica `backups/*.zip` aproximadamente a cada 60 segundos. Mantém os
dez backups concluídos mais recentes pela data `createTime` do catálogo FTB;
arquivos antigos fora do catálogo usam a data do nome FTB, nunca a data da cópia.
Snapshots entram na mesma ordem cronológica. Diretórios `world` e `.panel-recovery`
não são removidos. Relatórios spark também não entram neste limite.

Antes de apagar qualquer excedente, verifica estrutura, CRC e SHA-1 quando presente
de todos os dez arquivos preservados e dos alvos. A verificação é reaproveitada
somente enquanto a identidade, tamanho, data e hash do arquivo não mudarem.
Catálogo inválido, backup incompleto/recente, ZIP inválido, nome desconhecido ou
mudança durante a leitura adiam a limpeza. Durante gravação pode haver mais de
dez arquivos temporariamente; a política prioriza não descartar cópias válidas
em favor de uma cópia nova defeituosa.

A limpeza compartilha exclusão mútua com comandos do painel, inspeção, downloads
e restaurações. O FTB continua independente: configura-se `max_backups=10` e
`retention_mode=MAX_BACKUPS` para que sua política não continue reduzindo as cópias
automáticas a cinco. O painel complementa o mod incluindo snapshots e ZIPs antigos
que o catálogo não conhece. Não modifica o catálogo em memória do jogo.

Cada exclusão é registrada como `retention_delete` em Atividade. Arquivos excluídos
são removidos permanentemente, sem lixeira. Desativar a política não recupera ZIPs
já apagados. O status e a última verificação aparecem na aba Backups, com dados de
`retention` em `GET /api/status`.

## Configurar

`deploy/configure_retention.py --app /caminho/do/painel` exibe apenas uma prévia.
Adicionar `--apply-settings` configura o FTB e `.env` com cópias locais de segurança
dos arquivos anteriores. Não apaga ZIPs por si só. Reinicie somente o serviço do
painel após a configuração; não é necessário reiniciar o Minecraft.

Nunca versione o `.env` real, as cópias de configuração ou o catálogo dos backups.
