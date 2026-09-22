import { initSpark, refreshSpark } from './spark.js';
const $ = (id) => document.getElementById(id);
const labels = {overview:'Visão geral', backups:'Backups do mundo', logs:'Logs ao vivo', audit:'Atividade', spark:'Desempenho · spark'};
const verbs = {start:'Iniciar', stop:'Parar', restart:'Reiniciar', verify:'Verificar integridade', restore:'Restaurar mundo', download:'Download', spark:'Analisar processamento', retention_delete:'Limpeza automática'};
let currentView = 'overview', status = null, rawLogs = '', paused = false, pending = null, tick = 0;
const date = (n) => n ? new Date(n*1000).toLocaleString('pt-BR') : 'Não disponível';
const bytes = (n) => n == null ? 'Não disponível' : n >= 1024**3 ? `${(n/1024**3).toFixed(2)} GB` : `${(n/1024**2).toFixed(1)} MB`;
const duration = (n) => n ? `${Math.floor(n/3600)}h ${Math.floor(n%3600/60)}min` : '0min';
const text = (id, value) => { $(id).textContent = value; };
function notice(message) { text('notice',message); $('notice').hidden = !message; }
function element(tag, value, className) { const node=document.createElement(tag); node.textContent=value; if(className) node.className=className; return node; }
async function api(path, options={}) {
  const response = await fetch(`/api/${path}`, {cache:'no-store', ...options, headers:{'Content-Type':'application/json','X-Panel-CSRF':status?.csrf || '',...options.headers}});
  const data = await response.json();
  if(!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Falha na operação (${response.status})`);
  return data;
}
function view(name) {
  currentView=name; text('title', labels[name]);
  document.querySelectorAll('.view').forEach(node=>node.hidden=node.id!==name);
  document.querySelectorAll('.nav').forEach(node=>{node.classList.toggle('active',node.dataset.view===name); if(node.dataset.view===name) node.setAttribute('aria-current','page'); else node.removeAttribute('aria-current');});
  if(name==='backups') refreshBackups().catch(error=>notice(error.message));
  if(name==='audit') refreshAudit().catch(error=>notice(error.message));
  if(name==='spark') refreshSpark().catch(error=>notice(error.message));
}
document.querySelectorAll('[data-view]').forEach(node=>node.addEventListener('click',()=>view(node.dataset.view)));
document.querySelectorAll('[data-open]').forEach(node=>node.addEventListener('click',()=>view(node.dataset.open)));
function renderStatus(data) {
  status=data; text('identity',data.actor); text('connection',data.demo ? 'Demonstração local' : data.error ? 'Leitura indisponível' : 'Conectado');
  text('status',data.ready ? 'Online e respondendo' : data.running ? 'Processo ativo' : data.sampled_at ? 'Offline' : 'Aguardando leitura');
  $('status').classList.toggle('ready',data.ready);
  text('status-help',data.error || (data.ready ? 'O Minecraft está aceitando consultas de status.' : data.running ? 'O processo Java existe, mas o jogo ainda não respondeu. Pode estar iniciando ou com falha.' : 'O processo Java não está em execução.'));
  text('version',data.version || 'Minecraft Java com mods');
  text('players',data.players ?? '—'); text('max-players',data.max_players ? `Capacidade de ${data.max_players} jogadores` : 'Aguardando resposta do jogo');
  text('ram',data.sampled_at ? bytes(data.ram_bytes) : '—'); text('cpu',data.sampled_at ? `${data.cpu_percent}%` : '—'); text('uptime',data.sampled_at ? duration(data.uptime_seconds) : '—');
  text('restarts',data.manager ? `${data.manager.restarts} reinicializações registradas no PM2` : 'Desde o início do processo Java');
  text('updated',`Última leitura: ${date(data.sampled_at)}`);
  text('retention-status',data.retention?.enabled ? `${data.retention.message} Última verificação: ${date(data.retention.checked_at)}.` : 'Retenção automática do painel desativada. O modpack pode ter sua própria política.');
  const job=data.job;
  $('job').hidden=job.state==='idle'; text('job',job.message || '');
  document.querySelectorAll('[data-action]').forEach(button=>button.disabled=!!data.demo || job.state==='running' || !data.sampled_at || !!data.error);
}
function renderLogs() {
  const query=$('search').value.toLowerCase(), level=$('level').value;
  const rows=rawLogs.split('\n');
  text('recent-log',rows.slice(-16).join('\n') || 'Nenhuma mensagem disponível.');
  text('full-log',rows.filter(row=>(!query || row.toLowerCase().includes(query)) && (!level || row.includes(level))).join('\n') || 'Nenhuma mensagem corresponde aos filtros.');
}
$('search').addEventListener('input',renderLogs); $('level').addEventListener('change',renderLogs);
$('pause').addEventListener('click',()=>{paused=!paused; text('pause',paused?'Retomar atualização':'Pausar atualização');});
function ask(action, backup='') {
  pending={action,backup};
  text('confirm-title',verbs[action]);
  text('confirm-description',action==='restore' ? `Restaurar ${backup}? O jogo será parado, o mundo atual será preservado e os dados do mundo serão substituídos pelos deste backup. Depois, o Minecraft permanecerá parado.` : action==='verify' ? `Verificar todos os arquivos de ${backup}? Isso fará uma leitura do ZIP para conferir a integridade.` : `${verbs[action]} o Minecraft? ${action==='start' ? 'O carregamento do modpack pode levar alguns minutos.' : 'Os jogadores conectados serão desconectados. Aguarde o salvamento e a conclusão da operação.'}`);
  if(action==='spark') text('confirm-description','Analisar a thread principal por 60 segundos? A coleta tem custo adicional e exige que o jogo responda. O relatório fica no servidor, sem upload público. Nenhum reinício do Minecraft será solicitado.');
  $('restore-label').hidden=action!=='restore'; $('restore-confirm').value='';
  $('confirm-dialog').showModal();
}
document.querySelectorAll('[data-action]').forEach(node=>node.addEventListener('click',()=>ask(node.dataset.action)));
$('cancel').addEventListener('click',()=>$('confirm-dialog').close());
$('confirm-form').addEventListener('submit',async event=>{
  event.preventDefault();
  if(pending.action==='restore' && $('restore-confirm').value!=='RESTAURAR') { $('restore-confirm').setCustomValidity('Digite RESTAURAR exatamente.'); $('restore-confirm').reportValidity(); return; }
  $('confirm-submit').disabled=true;
  try { const job=await api('actions',{method:'POST',body:JSON.stringify({...pending,confirm:pending.action==='restore'?pending.backup:pending.action})}); status.job=job; renderStatus(status); $('confirm-dialog').close(); notice(''); }
  catch(error){ $('confirm-dialog').close(); notice(error.message); }
  finally { $('confirm-submit').disabled=false; }
});
$('restore-confirm').addEventListener('input',()=>$('restore-confirm').setCustomValidity(''));
async function refreshBackups() {
  const items=await api('backups'); const list=$('backup-list'); list.replaceChildren();
  text('last-backup',items.length ? date(items[0].modified) : 'Nenhum backup encontrado');
  text('backup-count',`${items.length} arquivos disponíveis • ${bytes(items.reduce((sum,item)=>sum+item.size,0))}`);
  if(!items.length) list.append(element('p','Nenhum ZIP foi encontrado no diretório de backups do modpack.'));
  for(const item of items) {
    const card=element('article','','panel backup-item'), info=element('div','');
    info.append(element('h2',item.name)); const meta=element('div','','backup-meta');
    [date(item.modified),bytes(item.size),item.complete?'Disponível':'Em gravação / aguardando conclusão'].forEach(value=>meta.append(element('span',value)));
    info.append(meta);
    const m=item.metrics;
    info.append(element('p',m ? `Ao detectar o ZIP: Minecraft ${m.cpu_percent}% CPU / ${bytes(m.ram_bytes)} RAM. Computador ${m.host_cpu_percent}% CPU / ${bytes(m.host_ram_bytes)} RAM. Aproximado, observado em ${date(m.observed_at)}.` : 'Métricas no início: não disponíveis para este backup.','backup-metrics'));
    const actions=element('div','','actions');
    const content=element('button','Conteúdo'); content.disabled=!item.complete;
    content.addEventListener('click',async()=>{try{const d=await api(`backups/${encodeURIComponent(item.name)}/content`); text('details-title',item.name); text('details-summary',`${d.files} entradas • ${bytes(d.uncompressed)} descompactados${d.truncated?' • exibindo as primeiras 150':''}`); text('details-files',d.entries.join('\n')); $('details-dialog').showModal();}catch(error){notice(error.message);}});
    const download=element('a','Baixar','button'); download.href=`/api/backups/${encodeURIComponent(item.name)}/download`; download.setAttribute('download','');
    actions.append(content); if(item.complete) actions.append(download);
    for(const action of ['verify','restore']) {const button=element('button',action==='verify'?'Verificar':'Restaurar',action==='restore'?'danger':''); button.disabled=!item.complete || status?.demo || status?.job.state==='running'; button.addEventListener('click',()=>ask(action,item.name)); actions.append(button);}
    card.append(info,actions); list.append(card);
  }
}
$('close-details').addEventListener('click',()=>$('details-dialog').close());
$('refresh-backups').addEventListener('click',()=>refreshBackups().catch(error=>notice(error.message)));
async function refreshAudit() {
  const entries=await api('audit'); $('audit-list').replaceChildren();
  if(!entries.length) $('audit-list').append(element('p','Nenhuma ação registrada no painel.'));
  entries.forEach(entry=>{const row=element('article','','audit-entry'); row.append(element('strong',`${verbs[entry.action] || entry.action}: ${entry.result}`),element('small',`${date(entry.time)} • ${entry.target}`),element('small',entry.actor)); $('audit-list').append(row);});
}
async function poll() {
  try {
    renderStatus(await api('status'));
    if(!paused && (currentView==='logs' || currentView==='overview')) {rawLogs=(await api('logs')).text; renderLogs();}
    if(tick%5===0) {if(currentView==='overview' || currentView==='backups') await refreshBackups(); if(currentView==='audit') await refreshAudit(); if(currentView==='spark') await refreshSpark();}
    tick++;
  } catch(error) {text('connection','Sem conexão'); notice(error.message); document.querySelectorAll('[data-action]').forEach(button=>button.disabled=true);}
  finally {setTimeout(poll,document.hidden?15000:3000);}
}
initSpark({api, notice, date});
poll();
