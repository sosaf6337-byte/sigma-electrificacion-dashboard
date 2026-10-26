export const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const fmt = (value, digits=1) => typeof value !== 'number' || !Number.isFinite(value) ? 'Sin dato' : new Intl.NumberFormat('es-MX',{maximumFractionDigits:digits,minimumFractionDigits:digits}).format(value);
export const num = value => value === '' ? null : Number(value);
export function toast(message){const t=document.querySelector('#toast');t.textContent=message;t.classList.add('show');clearTimeout(window.toastTimer);window.toastTimer=setTimeout(()=>t.classList.remove('show'),5500);}
export async function api(path,options={}){const r=await fetch('/api'+path,{...options,headers:{'Content-Type':'application/json','X-Sigma-Request':'local',...options.headers}});const data=await r.json();if(!r.ok){const error=new Error(typeof data.detail==='string'?data.detail:'Revisa los campos indicados.');error.detail=data.detail;throw error;}return data;}
export function banner(title,body,type=''){return `<div class="banner ${type}"><span aria-hidden="true">${type==='blue'?'ⓘ':'!'}</span><div><strong>${esc(title)}</strong><p>${esc(body)}</p></div></div>`;}
export function metric(label,value,unit,hint){return `<div class="metric"><div class="label">${esc(label)}</div><div class="value">${esc(value)} <span>${esc(unit||'')}</span></div><div class="hint">${esc(hint||'')}</div></div>`;}
export function pageHead(eyebrow,title,subtitle,action=''){return `<div class="page-head"><div><div class="eyebrow">${esc(eyebrow)}</div><h1>${esc(title)}</h1><p>${esc(subtitle)}</p></div><div class="actions">${action}</div></div>`;}
export function badge(text,type='neutral'){return `<span class="badge ${type}">${esc(text)}</span>`;}
export function dialog(title,body){document.querySelector('#dialog-title').textContent=title;document.querySelector('#dialog-content').innerHTML=body;document.querySelector('#detail-dialog').showModal();}
export function chart(series,lines,{unit='',height=210,min=null,max=null}={}){
 if(!series?.length)return '<p>Sin serie disponible.</p>';
 const values=series.flatMap(r=>lines.map(l=>r[l.key])).filter(x=>x!==null&&Number.isFinite(x));
 let lo=min??Math.min(...values),hi=max??Math.max(...values);if(!Number.isFinite(lo))lo=0;if(!Number.isFinite(hi))hi=1;if(hi-lo<.01)hi=lo+1;
 if(min===null){const pad=(hi-lo)*.08;lo-=pad;hi+=pad;}
 const w=640,left=49,right=15,top=15,bottom=32,pw=w-left-right,ph=height-top-bottom,end=series.at(-1).time_s||1;
 const x=t=>left+t/end*pw,y=v=>top+(hi-v)/(hi-lo)*ph;
 let grid='';for(let i=0;i<5;i++){const v=lo+(hi-lo)*i/4,yy=y(v);grid+=`<line class="grid" x1="${left}" y1="${yy}" x2="${w-right}" y2="${yy}"/><text x="${left-8}" y="${yy+4}" text-anchor="end">${fmt(v,hi-lo>100?0:1)}</text>`;}
 for(let i=0;i<5;i++){const t=end*i/4;grid+=`<text x="${x(t)}" y="${height-8}" text-anchor="middle">${fmt(t/3600,1)} h</text>`;}
 const paths=lines.map(l=>{let d='',open=false;for(const r of series){const v=r[l.key];if(v===null||!Number.isFinite(v)){open=false;continue;}d+=`${open?'L':'M'}${x(r.time_s).toFixed(2)},${y(v).toFixed(2)} `;open=true;}return `<path class="series" stroke="${l.color}" d="${d}"/>`;}).join('');
 return `<svg class="chart" viewBox="0 0 ${w} ${height}" role="img" aria-label="${esc(lines.map(l=>l.label).join(', '))}, ${esc(unit)}"><text x="4" y="10">${esc(unit)}</text>${grid}${paths}<line class="chart-cursor" data-chart-end="${end}" x1="${left}" x2="${left}" y1="${top}" y2="${height-bottom}"/></svg><div class="chart-legend">${lines.map(l=>`<span><i class="legend-dot" style="background:${l.color}"></i>${esc(l.label)}</span>`).join('')}</div>`;
}
export const groupNames={vehicle:'Vehículo y tracción',battery:'Batería principal',refrigerator_battery:'Batería de refrigeración',box:'Caja y producto',refrigeration:'Equipo frigorífico',weather:'Condiciones ambientales',charging:'Recarga e infraestructura',economics:'Costos de referencia',criteria:'Criterios térmicos'};
