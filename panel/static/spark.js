let services, report = null, loadedName = '', generation = 0;
const node = (tag, value, className) => {
  const item = document.createElement(tag);
  item.textContent = value;
  if(className) item.className = className;
  return item;
};
const $ = id => document.getElementById(id);
const number = n => n.toLocaleString('pt-BR', {maximumFractionDigits:2});

function render() {
  const list = $('spark-ranking');
  list.replaceChildren();
  if(!report) return;
  const query = $('spark-search').value.toLocaleLowerCase('pt-BR');
  const metric = $('spark-order').value;
  const rows = report.rows.filter(row => `${row.name} ${row.id}`.toLocaleLowerCase('pt-BR').includes(query))
    .sort((a,b) => b[`${metric}_ms`] - a[`${metric}_ms`] || a.name.localeCompare(b.name));
  if(!rows.length) list.append(node('p','Nenhum componente corresponde à busca.'));
  for(const row of rows) {
    const item = node('details','','panel spark-row');
    const summary = node('summary','');
    const title = node('span','');
    title.append(node('strong',row.name),node('small',`${row.id}${row.version ? ` · ${row.version}` : ''}`));
    const value = node('span','','spark-value');
    value.append(node('strong',`${number(row[`${metric}_percent`])}%`),node('small',`${number(row[`${metric}_ms`])} ms amostrados`));
    summary.append(title,value);
    const meter = node('meter',''); meter.min=0; meter.max=100; meter.value=row[`${metric}_percent`];
    meter.setAttribute('aria-label',`${row.name}: ${number(meter.value)}% do tempo amostrado`);
    summary.append(meter); item.append(summary);
    item.append(node('p',`Direto: ${number(row.direct_ms)} ms (${number(row.direct_percent)}%). Incluindo chamadas: ${number(row.inclusive_ms)} ms (${number(row.inclusive_percent)}%).`,'hint'));
    item.append(node('h3','Métodos com maior tempo direto'));
    if(!row.methods.length) item.append(node('p','Sem métodos com tempo direto atribuído nesta amostra.'));
    for(const method of row.methods) {
      const methodRow = node('div','','spark-method');
      methodRow.append(node('code',method.name),node('span',`${number(method.direct_ms)} ms · ${number(method.percent)}% do relatório`));
      item.append(methodRow);
    }
    list.append(item);
  }
}

async function selectReport() {
  const name = $('spark-report').value, request = ++generation;
  report=null; loadedName=''; $('spark-result').hidden=true;
  if(!name) return;
  $('spark-state').textContent='Lendo e calculando o relatório…';
  try {
    const result = await services.api(`spark/${encodeURIComponent(name)}`);
    if(request !== generation) return;
    report=result; loadedName=name;
    $('spark-period').textContent=`Coleta: ${services.date(report.start)}${report.end ? ` até ${services.date(report.end)}` : ''}`;
    $('spark-scope').textContent=`${number(report.sampled_ms)} ms amostrados · Threads: ${report.threads.join(', ')}`;
    $('spark-attribution').textContent=report.mapped ? 'Identificação baseada nos mapas de classes, métodos e linhas fornecidos pelo spark. Mixins e bibliotecas compartilhadas podem limitar a atribuição.' : 'Este relatório não possui mapas de atribuição a mods. O painel mantém o tempo não identificado separado; não estima nomes de mods.';
    $('spark-state').textContent=`Relatório carregado: ${name}`;
    $('spark-result').hidden=false; render();
  } catch(error) {
    if(request===generation) $('spark-state').textContent=error.message;
  }
}

export async function refreshSpark() {
  try {
    const entries=await services.api('spark');
    const select=$('spark-report'), selected=select.value;
    select.replaceChildren();
    if(!entries.length) {
      generation++; loadedName=''; report=null;
      select.append(node('option','Nenhum relatório local'));
      select.options[0].value=''; select.disabled=true;
      $('spark-result').hidden=true;
      $('spark-state').textContent='Nenhum relatório finalizado. Use Analisar por 60 segundos. Se o jogo travar ou reiniciar durante a coleta, o arquivo pode não ser gerado.';
      return;
    }
    select.disabled=false;
    entries.forEach(entry=>{const option=node('option',`${services.date(entry.modified)} · ${entry.name}`); option.value=entry.name; select.append(option);});
    if(entries.some(entry=>entry.name===selected)) select.value=selected;
    if(loadedName!==select.value) await selectReport();
  } catch(error) { $('spark-state').textContent=`Não foi possível consultar relatórios: ${error.message}`; }
}

export function initSpark(dependencies) {
  services=dependencies;
  $('spark-report').addEventListener('change',selectReport);
  $('spark-refresh').addEventListener('click',()=>{loadedName=''; refreshSpark();});
  $('spark-search').addEventListener('input',render);
  $('spark-order').addEventListener('change',render);
}
