# Segurança e publicação

Este painel é administrativo e exclusivo de um proprietário via Tailscale.
Não exponha a porta na internet ou na LAN e não use proxy que altere a origem TCP.

Nunca versione `.env`, chaves SSH, senhas, tokens, mundos, backups, relatórios spark,
logs, bancos SQLite, capturas do ambiente real ou arquivos da instalação do jogo.
`.env.example` contém apenas valores de exemplo. Configure os reais no servidor.

Relatórios e logs podem conter caminhos, nomes e dados operacionais de terceiros.
O painel limita os campos dos relatórios apresentados, mas isso não transforma
os arquivos originais em dados públicos. O acesso aos backups e logs exige a
mesma autorização do proprietário.

Antes de publicar, revise `git diff --cached`, a lista `git ls-files` e o histórico.
Se alguma credencial tiver sido exposta, revogue-a: apagar o arquivo no último
commit não a remove das revisões anteriores.

Para reportar falhas, use um canal privado do mantenedor e exemplos sintéticos.
Não publique logs reais, tokens ou relatórios do servidor em issues públicas.
