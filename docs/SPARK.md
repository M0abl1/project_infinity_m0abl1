# Relatórios spark

## Leitura e interpretação

A aba Desempenho lê até 100 arquivos `.sparkprofile` recentes em
`MINE_ROOT/config/spark`. O conteúdo permanece no servidor: o painel não envia
arquivos, mapas ou configurações ao visualizador público do spark.

- **Direto:** tempo do método menos suas chamadas filhas, atribuído ao mod
  identificado nos mapas de métodos, linhas ou classes do próprio relatório.
- **Incluindo chamadas:** tempo da árvore chamada pelo componente. Recursão do
  mesmo componente na mesma cadeia não é somada novamente. Há sobreposição entre
  componentes; esta coluna não deve ser somada.
- Percentuais usam o total amostrado das threads selecionadas pelo profiler.
  Não são percentuais de CPU do computador nem medidas exatas de RAM por mod.
- Minecraft, Java e código sem atribuição ficam separados. Métodos com mixins,
  código nativo e bibliotecas compartilhadas podem limitar a identificação.
- Mod com zero nesta amostra não é prova de custo zero. O relatório é uma
  fotografia do período, não monitoramento contínuo por mod.

Cada componente expande os 15 métodos com maior tempo direto. Busca por nome/ID,
ordenação das duas métricas, data da coleta e threads estão disponíveis em telas
grandes e celulares, com tema automático claro/escuro.

## Coleta

O botão solicita exclusivamente este comando pelo ID numérico do processo PM2:

```text
spark profiler start --timeout 60 --save-to-file
```

A coleta padrão usa a thread principal. Não abre RCON nem aceita comandos
arbitrários. Requer proprietário Tailscale, CSRF e usa a mesma exclusão mútua
das operações de backup/controle. Solicitação e resultado são auditados.

O painel aguarda até 100 segundos por um novo arquivo e confere sua leitura antes
de indicar sucesso. PM2 aceitar o comando não garante que o Minecraft o executou.
Se houver travamento, reinício ou outro profiler ativo, o painel informa ausência
de relatório. Não reinicia o jogo nem cancela uma coleta externa automaticamente.
A coleta adiciona trabalho e pode substituir o profiler automático de fundo do spark.
Confira os logs antes de repetir em um servidor sobrecarregado.

## API

- `GET /api/spark`: nomes, tamanhos e datas dos relatórios locais disponíveis.
- `GET /api/spark/{name}`: período, threads, total amostrado, mapas disponíveis,
  linhas por componente e métodos principais. Metadados de identidade, argumentos
  JVM e configurações do servidor não são expostos pela resposta.
- `POST /api/actions` com `{"action":"spark"}`: 202; acompanhar `job` em
  `/api/status`. Demonstração recusa a operação com 403.

Arquivos maiores que 32 MiB, nomes externos, links simbólicos, alocações de memória,
referências inválidas/cíclicas, tempos não finitos e estruturas antigas incompatíveis
são recusados. Limites: 200 mil métodos e profundidade 512. Cache em memória somente
do último relatório, invalidado por nome/tamanho/data. Nenhum arquivo é executado.

## Formato e referência

O parser usa uma descrição protobuf mínima dos campos públicos do formato
`spark_sampler.proto`. Não carrega configurações do relatório nem executa código Java.

- [Comandos oficiais](https://spark.lucko.me/docs/Command-Usage)
- [Dados brutos do spark](https://spark.lucko.me/docs/misc/Raw-spark-data)
- [Contrato protobuf](https://github.com/lucko/spark/blob/master/spark-common/src/main/proto/spark/spark_sampler.proto)

Relatórios reais são dados operacionais e não devem ser enviados ao GitHub.
