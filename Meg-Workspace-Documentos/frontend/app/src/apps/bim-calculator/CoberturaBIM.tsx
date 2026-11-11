import { useEffect, useState } from 'react';
import { megalodonClient } from '@/lib/api-client';
import type { CoberturaProductoBIM, CoberturaRevisionBIM, DecisionMedicionBIM, LineaDecisionBIM, ModeloBIM, ParametrosCosteoInput, Presupuesto, CatalogoAPUOut } from '@/lib/megalodon-client';

const labels: Record<string,string> = {ADMITIDO:'Admitidos', CUBIERTO_POR_CONJUNTO:'Cubiertos por conjuntos',
  REPRESENTACION_PROPIA_PENDIENTE:'Con representación pendiente', CONJUNTO_PENDIENTE:'Conjuntos pendientes', SIN_REPRESENTACION:'Sin representación'};
const causeLabels: Record<string,string> = {CAMBIO_REVISION_MODELO:'Cambió la revisión del modelo',
  MODELO_EN_PROCESAMIENTO_O_ERROR:'El modelo requiere procesamiento', DECISION_SUSTITUIDA:'Hay una decisión posterior',
  CAMBIO_CONCEPTO_O_PRECIO:'Cambió el concepto o precio', CAMBIO_SUSTENTO_CONTRACTUAL:'Cambió el documento contractual'};
const field = 'block w-full min-w-0 rounded border border-(--border-subtle) bg-(--surface-elevated) p-2';
const button = 'rounded border border-(--border-subtle) px-3 py-2 disabled:opacity-40';
const msg = (e:unknown) => e instanceof Error ? e.message : 'No se pudo completar la operación';

export default function CoberturaBIM({expedienteId,modelo,canWrite,onProcessed,onBudget,parametros}: {
  expedienteId:string; modelo:ModeloBIM; canWrite:boolean; onProcessed:(m:ModeloBIM)=>void;
  onBudget:(p:Presupuesto)=>void; parametros:(reference:string)=>ParametrosCosteoInput;
}) {
  const [open,setOpen]=useState(false);
  const [revisions,setRevisions]=useState<Array<{id:string;actual:boolean;creado_en:string;fuente_sha256:string}>>([]);
  const [revision,setRevision]=useState('');
  const [coverage,setCoverage]=useState<CoberturaRevisionBIM|null>(null);
  const [filter,setFilter]=useState('');
  const [skip,setSkip]=useState(0);
  const [decisions,setDecisions]=useState<DecisionMedicionBIM[]>([]);
  const [docs,setDocs]=useState<Array<{id:string;nombre:string;tipo:string}>>([]);
  const [family,setFamily]=useState<CoberturaProductoBIM[]>([]);
  const [familyId,setFamilyId]=useState('');
  const [criterion,setCriterion]=useState<'PADRE'|'COMPONENTES'>('PADRE');
  const [lines,setLines]=useState<LineaDecisionBIM[]>([]);
  const [exclusions,setExclusions]=useState<Record<string,string>>({});
  const [document,setDocument]=useState('');
  const [reference,setReference]=useState('');
  const [budgetReference,setBudgetReference]=useState('');
  const [search,setSearch]=useState('');
  const [concepts,setConcepts]=useState<CatalogoAPUOut[]>([]);
  const [selected,setSelected]=useState<string[]>([]);
  const [busy,setBusy]=useState(false);
  const [completedQuery,setCompletedQuery]=useState('');
  const [formRevision,setFormRevision]=useState('');
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [reload,setReload]=useState(0);
  const queryKey=`${revision}:${filter}:${skip}:${reload}`;
  const loading=completedQuery!==queryKey;
  useEffect(()=>{if(!open)return;let active=true;
    void Promise.all([megalodonClient.bim.revisiones(expedienteId,modelo.id),megalodonClient.bim.referenciasContractuales(expedienteId,modelo.id)])
      .then(([r,d])=>{if(active){setRevisions(r);setDocs(d);setRevision(r.find(i=>i.actual)?.id||r[0]?.id||'');}})
      .catch(e=>{if(active)setError(msg(e));});return()=>{active=false;};
  },[open,expedienteId,modelo.id,reload,modelo.estado_procesamiento]);
  useEffect(()=>{if(!open||!revision)return;let active=true;
    void Promise.all([megalodonClient.bim.cobertura(expedienteId,modelo.id,revision,filter,skip),megalodonClient.bim.decisionesMedicion(expedienteId,modelo.id,revision)])
      .then(([c,d])=>{if(active){setCoverage(c);setDecisions(d);setError('');}}).catch(e=>{if(active)setError(msg(e));})
      .finally(()=>{if(active)setCompletedQuery(queryKey);});return()=>{active=false;};
  },[open,expedienteId,modelo.id,revision,filter,skip,reload,queryKey]);
  const editable=canWrite&&!loading&&coverage?.actual&&modelo.estado_procesamiento==='COMPLETADO'&&!busy;
  async function action(run:()=>Promise<void>){setBusy(true);setError('');setNotice('');try{await run();}catch(e){setError(msg(e));}finally{setBusy(false);}}
  async function chooseFamily(gid:string){await action(async()=>{
    const members=await megalodonClient.bim.familia(expedienteId,modelo.id,gid,revision);
    setFormRevision(revision);setFamily(members);setFamilyId(gid);setLines([]);setExclusions({});setReference('');setDocument('');setCriterion('PADRE');
  });}
  function updateLine(index:number,patch:Partial<LineaDecisionBIM>){setLines(previous=>previous.map((l,i)=>i===index?{...l,...patch}:l));}
  async function save(confirm:boolean){await action(async()=>{
    await megalodonClient.bim.guardarDecision(expedienteId,modelo.id,{revision_id:revision,familia_global_id:familyId,
      criterio:criterion,confirmar:confirm,lineas:lines,referencia_contractual:reference,documento_id:document||null,exclusiones:exclusions});
    setNotice(confirm?'Decisión confirmada con sus fuentes. Puedes generar una nueva versión del presupuesto.':'Propuesta guardada; la aprobación económica continúa pendiente.');setReload(n=>n+1);
  });}
  const activeSelected=selected.filter(id=>decisions.some(d=>d.id===id&&d.estado==='VIGENTE'));
  const eligible=family.filter(r=>r.admitido&&r.malla_disponible&&r.tipo!=='IfcBuildingElementProxy'&&(criterion==='PADRE'?r.global_id===familyId:r.global_id!==familyId));
  return <details className="bim-coverage" onToggle={e=>setOpen(e.currentTarget.open)}>
    <summary className="cursor-pointer py-2 font-medium">Cobertura y decisiones por revisión</summary>
    {open&&<section aria-label="Cobertura IFC por revisión" className="space-y-3 py-3">
      {error&&<p role="alert" className="text-(--danger)">{error}</p>}
      {notice&&<p role="status">{notice}</p>}
      {!revisions.length&&!error&&<p>Este modelo necesita reprocesarse para registrar su cobertura.
        {canWrite&&<button className={button} disabled={busy} onClick={()=>void action(async()=>onProcessed(await megalodonClient.bim.reprocesarModelo(expedienteId,modelo.id)))}>Registrar cobertura del modelo</button>}</p>}
      {!!revisions.length&&<>
        <label>Revisión del modelo<select className={field} value={revision} onChange={e=>{setRevision(e.target.value);setSkip(0);setFamily([]);setFamilyId('');setLines([]);setSelected([]);}}>
          {revisions.map((r,i)=><option key={r.id} value={r.id}>{r.actual?'Actual':'Histórica'} · {new Date(r.creado_en).toLocaleString('es-MX')} · {i+1}</option>)}
        </select></label>
        {loading&&<p role="status">Consultando cobertura y vigencia…</p>}
        {coverage&&<>
          <p className="break-all text-(--text-muted)">Fuente IFC SHA-256: {coverage.fuente_sha256}</p>
          {!coverage.actual&&<p role="status" className="text-(--warning)">Revisión histórica. Sus decisiones deben revisarse antes de usarlas en el modelo actual.</p>}
          <div className="grid grid-cols-2 gap-2">{Object.entries(coverage.resumen).map(([state,n])=><div key={state} className="rounded border border-(--border-subtle) p-2"><strong>{n}</strong><br/>{labels[state]||state}</div>)}</div>
          <p>La cobertura gráfica y la aprobación económica se revisan por separado. Los Proxy requieren clasificación funcional antes de su mapeo económico.</p>
          {coverage.actual&&canWrite&&<div className="flex flex-wrap gap-2">{coverage.incorporables.filter(t=>!coverage.tipos_admitidos.includes(t)).map(t=><button key={t} className={button} disabled={!editable} onClick={()=>void action(async()=>onProcessed(await megalodonClient.bim.incorporarTipos(expedienteId,modelo.id,revision,[t])))}>Incorporar {t}</button>)}</div>}
          <label>Filtrar cobertura<select className={field} value={filter} onChange={e=>{setFilter(e.target.value);setSkip(0);}}><option value="">Todos los estados</option>{Object.entries(labels).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>
          <ul className="max-h-64 overflow-auto space-y-2" aria-label="Productos de la revisión">{coverage.items.map(row=><li key={row.global_id} className="rounded border border-(--border-subtle) p-2">
            <strong>{row.nombre||row.tipo}</strong> · {row.tipo}<br/>{labels[row.estado_cobertura]} · {row.malla_disponible?'Malla disponible':'Sin malla propia admitida'}
            <details><summary>Ver causa y procedencia</summary><p className="break-all">{row.global_id}</p><p>{row.causa||row.tratamiento_adicional}</p><p className="break-all">Cubierto por: {row.cubierto_por.join(', ')||'Sin conjunto de cobertura confirmado'}</p><p className="break-all">Padres: {row.padres.join(', ')||'Sin padre IFC'}</p><p>{row.regla_candidata}</p></details>
            <button className={button} disabled={!editable} onClick={()=>void chooseFamily(row.global_id)}>Revisar medición de esta familia</button>
          </li>)}</ul>
          <div className="flex flex-wrap items-center gap-2"><button className={button} disabled={!skip||loading} onClick={()=>setSkip(n=>Math.max(0,n-50))}>Página anterior</button><span>{skip+1}–{Math.min(skip+50,coverage.total)} de {coverage.total}</span><button className={button} disabled={skip+50>=coverage.total||loading} onClick={()=>setSkip(n=>n+50)}>Página siguiente</button></div>
        </>}
        {formRevision===revision&&!!family.length&&<fieldset disabled={!editable} className="rounded border border-(--border-subtle) p-3 space-y-3">
          <legend className="font-semibold">Decisión de medición · {family.find(r=>r.global_id===familyId)?.nombre||familyId}</legend>
          <label>Criterio de pago<select className={field} value={criterion} onChange={e=>{setCriterion(e.target.value as 'PADRE'|'COMPONENTES');setLines([]);}}><option value="PADRE">Conjunto integral</option><option value="COMPONENTES">Conceptos por componentes</option></select></label>
          <p>Guarda una propuesta si falta sustento. Confirmar exige documento de esta obra, conceptos, mediciones y alcance. Se conserva una versión nueva y su responsable.</p>
          <label>Documento contractual de esta obra<select className={field} value={document} onChange={e=>setDocument(e.target.value)}><option value="">Sin documento contractual vinculado</option>{docs.map(d=><option key={d.id} value={d.id}>{d.tipo} · {d.nombre}</option>)}</select></label>
          <label>Referencia contractual<input className={field} value={reference} maxLength={2000} onChange={e=>setReference(e.target.value)} placeholder="Concepto, cláusula de medición y pago, APU o aclaración"/></label>
          <label>Buscar concepto en el catálogo<input className={field} value={search} onChange={e=>setSearch(e.target.value)}/></label>
          <button className={button} disabled={!search.trim()||busy} onClick={()=>void action(async()=>{const result=await megalodonClient.catalogoAPU.listar({q:search,limit:30});setConcepts(result as CatalogoAPUOut[]);})}>Buscar conceptos para la decisión</button>
          <div className="space-y-3">{lines.map((line,i)=><fieldset key={i} className="rounded border border-(--border-subtle) p-2 space-y-2">
            <legend>Medición {i+1}</legend>
            <label>Elemento medido<select className={field} value={line.global_id} onChange={e=>updateLine(i,{global_id:e.target.value})}>{eligible.map(r=><option key={r.global_id} value={r.global_id}>{r.tipo} · {r.nombre||r.global_id}</option>)}</select></label>
            <label>Concepto vinculado<select className={field} value={line.catalogo_apu_id||''} onChange={e=>updateLine(i,{catalogo_apu_id:e.target.value||null})}><option value="">Pendiente de vincular</option>{concepts.map(c=><option key={c.id} value={c.id}>{c.clave} · {c.descripcion} · {c.unidad}</option>)}</select></label>
            <label>Cantidad revisada<input className={field} type="number" min="0" step="any" value={line.cantidad} onChange={e=>updateLine(i,{cantidad:e.target.value})}/></label>
            <label>Referencia de medición<input className={field} value={line.referencia_medicion} maxLength={1000} onChange={e=>updateLine(i,{referencia_medicion:e.target.value})}/></label>
            <label>Alcance e inclusiones del concepto<input className={field} value={line.alcance} maxLength={1000} onChange={e=>updateLine(i,{alcance:e.target.value})}/></label>
            <button className={button} onClick={()=>setLines(previous=>previous.filter((_,n)=>n!==i))}>Quitar medición {i+1}</button>
          </fieldset>)}</div>
          <button className={button} disabled={!eligible.length} onClick={()=>setLines(previous=>[...previous,{global_id:eligible[0].global_id,catalogo_apu_id:null,cantidad:'',referencia_medicion:'',alcance:''}])}>Añadir medición</button>
          {criterion==='COMPONENTES'&&<details><summary>Exclusiones contractuales de componentes</summary>{family.filter(r=>!r.componentes.length).map(r=><label key={r.global_id} className="block">{r.nombre||r.global_id}<input className={field} value={exclusions[r.global_id]||''} placeholder="Dejar vacío si se mide; indicar la exclusión contractual si no se incluye" onChange={e=>setExclusions(previous=>{const next={...previous};if(e.target.value)next[r.global_id]=e.target.value;else delete next[r.global_id];return next;})}/></label>)}</details>}
          <div className="flex flex-wrap gap-2"><button className={button} onClick={()=>void save(false)}>Guardar propuesta</button><button className={button} disabled={!document||reference.trim().length<5||!lines.length||lines.some(l=>!l.catalogo_apu_id)} onClick={()=>void save(true)}>Confirmar decisión con sustento</button></div>
        </fieldset>}
        <section aria-label="Historial de decisiones" className="space-y-2"><h3 className="font-semibold">Decisiones y vigencia</h3>
          {!decisions.length&&<p>Sin decisiones registradas para esta revisión.</p>}
          {decisions.map(d=><article key={d.id} className="rounded border border-(--border-subtle) p-2 space-y-1">
            <label className="flex gap-2"><input type="checkbox" checked={d.estado==='VIGENTE'&&activeSelected.includes(d.id)} disabled={!editable||d.estado!=='VIGENTE'} onChange={e=>setSelected(previous=>e.target.checked?[...previous,d.id]:previous.filter(id=>id!==d.id))}/>{d.criterio==='PADRE'?'Conjunto':'Componentes'} · versión {d.version} · {d.estado}</label>
            <p className="break-all">Familia: {d.familia_global_id}</p><p>{d.causas.map(c=>causeLabels[c]||c).join(' · ')}</p>
            <p className="break-all">Responsable: {d.usuario_id} · {new Date(d.creado_en).toLocaleString('es-MX')}</p>
            <details><summary>Ver mediciones y sustento registrado</summary><p>{d.datos.referencia_contractual||'Sustento contractual pendiente'}</p>{d.datos.lineas.map((l,i)=><p key={i} className="break-all">{l.global_id} · {l.cantidad} · {l.alcance} · {l.referencia_medicion}</p>)}</details>
          </article>)}
          <label>Referencia de factores para esta versión<input className={field} value={budgetReference} maxLength={1000} onChange={e=>setBudgetReference(e.target.value)} placeholder="Se utilizarán los factores que hayas revisado en Preparar presupuesto"/></label>
          <button className={button} disabled={!editable||!activeSelected.length||budgetReference.trim().length<5} onClick={()=>void action(async()=>{const budget=await megalodonClient.bim.presupuestoDecisiones(expedienteId,modelo.id,activeSelected,parametros(budgetReference));onBudget(budget);setNotice('Nueva versión del presupuesto creada desde las decisiones vigentes.');})}>Crear versión del presupuesto con decisiones</button>
        </section>
      </>}
    </section>}
  </details>;
}
