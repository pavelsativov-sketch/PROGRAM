import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import ReactFlow, {
  Background, Controls, MiniMap, addEdge, updateEdge, useNodesState, useEdgesState,
  Handle, Position, MarkerType,
} from 'reactflow';
import { api } from '../api';

const NODE_TYPES = [
  { kind: 'start', label: 'Старт', desc: 'Точка входа' },
  { kind: 'message', label: 'Сообщение', desc: 'Отправить текст' },
  { kind: 'ai', label: 'AI-ответ', desc: 'LLM-ответ по промпту' },
  { kind: 'collect', label: 'Вопрос → переменная', desc: 'Сохранить ответ в variable' },
  { kind: 'catalog', label: 'Каталог', desc: 'Показать товары' },
  { kind: 'condition', label: 'Условие', desc: 'Ветвление true/false' },
  { kind: 'order_summary', label: 'Сводка заказа', desc: 'Показать собранные данные' },
  { kind: 'invoice', label: 'Выставить счёт', desc: 'Создать заказ и ссылку на оплату' },
  { kind: 'handoff', label: 'Передать оператору', desc: 'Стоп — менеджер' },
  { kind: 'end', label: 'Завершить', desc: 'Конец диалога' },
];

function CustomNode({ data }) {
  const kind = data.kind || 'message';
  const subText = data.text || data.question || data.system_prompt || data.variable || '';
  return (
    <div className={`node-box ${kind}`}>
      <Handle type="target" position={Position.Top} />
      <div className="node-title">{data.label || kind}</div>
      <div className="node-sub">{subText}</div>
      {kind === 'condition' ? (
        <>
          <Handle id="true" type="source" position={Position.Bottom} style={{ left: '25%' }} />
          <Handle id="false" type="source" position={Position.Bottom} style={{ left: '75%' }} />
        </>
      ) : (
        <Handle type="source" position={Position.Bottom} />
      )}
    </div>
  );
}

const nodeTypes = { default: CustomNode };

export default function FlowEditor() {
  const { id } = useParams();
  const nav = useNavigate();
  const [flow, setFlow] = useState(null);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  // selected: { kind: 'node'|'edge', data: node|edge } | null
  const [selected, setSelected] = useState(null);
  const [saving, setSaving] = useState(false);
  const wrapRef = useRef();
  const edgeUpdateSuccessful = useRef(true);
  const [rfInstance, setRfInstance] = useState(null);

  const defaultEdgeOptions = useMemo(() => ({
    type: 'smoothstep',
    markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
    style: { strokeWidth: 2 },
  }), []);

  const decorateEdge = (e) => ({
    type: 'smoothstep',
    markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18 },
    style: { strokeWidth: 2 },
    label: e.sourceHandle === 'true' ? 'да' : e.sourceHandle === 'false' ? 'нет' : undefined,
    labelStyle: { fontSize: 11, fill: '#555' },
    labelBgPadding: [4, 2],
    labelBgStyle: { fill: '#fff', fillOpacity: 0.85 },
    ...e,
  });

  useEffect(() => {
    api.flows.get(id).then(f => {
      setFlow(f);
      setNodes(f.graph?.nodes || []);
      setEdges((f.graph?.edges || []).map(decorateEdge));
    });
  }, [id]);

  const onConnect = useCallback((c) => setEdges(eds => addEdge(
    decorateEdge({ ...c, sourceHandle: c.sourceHandle || null }),
    eds,
  )), []);

  const onEdgeUpdateStart = useCallback(() => { edgeUpdateSuccessful.current = false; }, []);
  const onEdgeUpdate = useCallback((oldEdge, newConn) => {
    edgeUpdateSuccessful.current = true;
    setEdges(eds => updateEdge(oldEdge, newConn, eds).map(e => e.id === oldEdge.id ? decorateEdge({ ...e }) : e));
  }, []);
  const onEdgeUpdateEnd = useCallback((_, edge) => {
    if (!edgeUpdateSuccessful.current) {
      // отпустили мимо хэндла — удаляем связь
      setEdges(eds => eds.filter(e => e.id !== edge.id));
      setSelected(s => (s?.kind === 'edge' && s.data.id === edge.id ? null : s));
    }
    edgeUpdateSuccessful.current = true;
  }, []);

  const onDragStart = (e, kind) => {
    e.dataTransfer.setData('application/kind', kind);
    e.dataTransfer.effectAllowed = 'move';
  };

  const onDrop = (e) => {
    e.preventDefault();
    const kind = e.dataTransfer.getData('application/kind');
    if (!kind || !rfInstance) return;
    const bounds = wrapRef.current.getBoundingClientRect();
    const position = rfInstance.screenToFlowPosition({ x: e.clientX - bounds.left, y: e.clientY - bounds.top });
    const id = `n_${Date.now()}`;
    const meta = NODE_TYPES.find(t => t.kind === kind);
    setNodes(nds => nds.concat({
      id, type: 'default', position,
      data: { kind, label: meta?.label || kind },
    }));
  };

  const onDragOver = (e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; };

  const save = async () => {
    setSaving(true);
    try {
      const updated = await api.flows.update(id, {
        name: flow.name, description: flow.description, is_active: flow.is_active,
        graph: { nodes, edges },
      });
      setFlow(updated);
    } finally {
      setSaving(false);
    }
  };

  const activate = async () => { await api.flows.activate(id); const f = await api.flows.get(id); setFlow(f); };

  const updateNodeData = (patch) => {
    if (!selected || selected.kind !== 'node') return;
    const nid = selected.data.id;
    setNodes(nds => nds.map(n => n.id === nid ? { ...n, data: { ...n.data, ...patch } } : n));
    setSelected(s => ({ ...s, data: { ...s.data, data: { ...s.data.data, ...patch } } }));
  };

  const updateEdgeData = (patch) => {
    if (!selected || selected.kind !== 'edge') return;
    const eid = selected.data.id;
    setEdges(eds => eds.map(e => {
      if (e.id !== eid) return e;
      const merged = { ...e, ...patch };
      return decorateEdge({ ...merged, label: undefined });
    }));
    setSelected(s => ({ ...s, data: { ...s.data, ...patch } }));
  };

  const deleteSelected = () => {
    if (!selected) return;
    if (selected.kind === 'node') {
      const nid = selected.data.id;
      setNodes(nds => nds.filter(n => n.id !== nid));
      setEdges(eds => eds.filter(e => e.source !== nid && e.target !== nid));
    } else {
      const eid = selected.data.id;
      setEdges(eds => eds.filter(e => e.id !== eid));
    }
    setSelected(null);
  };

  if (!flow) return <div style={{padding:24}}>Загрузка...</div>;

  return (
    <div className="flow-wrap">
      <div className="flow-toolbar">
        <button className="secondary small" onClick={() => nav('/flows')}>← Назад</button>
        <input style={{maxWidth:320}} value={flow.name} onChange={e => setFlow({...flow, name: e.target.value})} />
        <span className="muted">{flow.is_active ? 'активен' : 'неактивен'}</span>
        <div style={{flex:1}} />
        {!flow.is_active && <button className="secondary" onClick={activate}>Сделать активным</button>}
        <button onClick={save} disabled={saving}>{saving ? 'Сохранение...' : 'Сохранить'}</button>
      </div>
      <div className="flow-main">
        <div className="flow-palette">
          <div style={{fontWeight:600, marginBottom:8}}>Узлы</div>
          {NODE_TYPES.map(t => (
            <div key={t.kind} className="palette-item" draggable onDragStart={e => onDragStart(e, t.kind)}>
              <div style={{fontWeight:600}}>{t.label}</div>
              <div className="muted" style={{fontSize:11}}>{t.desc}</div>
            </div>
          ))}
          <div className="muted" style={{fontSize:11, marginTop:12}}>Перетащите узел на холст. Соедините узлы стрелками.</div>
        </div>
        <div ref={wrapRef} onDrop={onDrop} onDragOver={onDragOver} style={{height:'100%'}}>
          <ReactFlow
            nodes={nodes} edges={edges}
            onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onInit={setRfInstance}
            onNodeClick={(_, n) => setSelected({ kind: 'node', data: n })}
            onEdgeClick={(_, e) => setSelected({ kind: 'edge', data: e })}
            onPaneClick={() => setSelected(null)}
            onEdgeUpdate={onEdgeUpdate}
            onEdgeUpdateStart={onEdgeUpdateStart}
            onEdgeUpdateEnd={onEdgeUpdateEnd}
            edgesUpdatable
            edgesFocusable
            nodesFocusable
            deleteKeyCode={['Delete', 'Backspace']}
            defaultEdgeOptions={defaultEdgeOptions}
            nodeTypes={nodeTypes}
            fitView
          >
            <Background /><Controls /><MiniMap pannable zoomable />
          </ReactFlow>
        </div>
        <div className="flow-inspector">
          {!selected && (
            <div className="muted">
              Выберите узел или стрелку для редактирования.<br/>
              <span style={{fontSize:11}}>Стрелку можно «перетащить» за конец на другой узел, либо удалить клавишей Delete / Backspace.</span>
            </div>
          )}
          {selected?.kind === 'node' && (
            <NodeInspector node={selected.data} onChange={updateNodeData} onDelete={deleteSelected} />
          )}
          {selected?.kind === 'edge' && (
            <EdgeInspector
              edge={selected.data}
              nodes={nodes}
              onChange={updateEdgeData}
              onDelete={deleteSelected}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function NodeInspector({ node, onChange, onDelete }) {
  const d = node.data || {};
  const kind = d.kind;
  return (
    <div>
      <div className="header">
        <h3 style={{margin:0}}>{d.label || kind}</h3>
        <button className="small danger" onClick={onDelete}>Удалить</button>
      </div>
      <label>Имя узла</label>
      <input value={d.label || ''} onChange={e => onChange({ label: e.target.value })} />
      <div className="muted" style={{marginTop:8}}>Тип: {kind}</div>

      {kind === 'message' && (
        <>
          <label>Текст сообщения</label>
          <textarea rows={6} value={d.text || ''} onChange={e => onChange({ text: e.target.value })} placeholder="Здравствуйте! ..." />
          <div className="muted">Доступны подстановки: {'{name}'}, {'{phone}'}, {'{address}'} и др.</div>
        </>
      )}

      {kind === 'ai' && (
        <>
          <label>System prompt</label>
          <textarea rows={8} value={d.system_prompt || ''} onChange={e => onChange({ system_prompt: e.target.value })} placeholder="Ты — вежливый флорист-консультант..." />
        </>
      )}

      {kind === 'collect' && (
        <>
          <label>Вопрос клиенту</label>
          <textarea rows={3} value={d.question || ''} onChange={e => onChange({ question: e.target.value })} />
          <label>Имя переменной</label>
          <input value={d.variable || ''} onChange={e => onChange({ variable: e.target.value })} placeholder="name / phone / address / delivery_date" />
          <label>Извлечение через AI (опционально)</label>
          <input value={d.extract_prompt || ''} onChange={e => onChange({ extract_prompt: e.target.value })} placeholder="например: извлеки номер телефона" />
        </>
      )}

      {kind === 'condition' && (
        <>
          <label>Переменная для проверки</label>
          <input value={d.variable || ''} onChange={e => onChange({ variable: e.target.value })} />
          <label>Ключевые слова (через запятую)</label>
          <input value={(d.keywords || []).join(', ')} onChange={e => onChange({ keywords: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })} />
          <div className="muted">Ветви: true (совпало) / false (не совпало)</div>
        </>
      )}

      {kind === 'invoice' && (
        <>
          <label>Товар по умолчанию (если не выбран)</label>
          <input value={d.default_product || ''} onChange={e => onChange({ default_product: e.target.value })} />
          <label>Запасная цена</label>
          <input type="number" value={d.fallback_price || 2500} onChange={e => onChange({ fallback_price: Number(e.target.value) })} />
          <label>Стоимость доставки</label>
          <input type="number" value={d.delivery_fee || 0} onChange={e => onChange({ delivery_fee: Number(e.target.value) })} />
        </>
      )}

      {kind === 'handoff' && (
        <>
          <label>Сообщение клиенту</label>
          <textarea rows={3} value={d.text || ''} onChange={e => onChange({ text: e.target.value })} />
        </>
      )}

      {kind === 'end' && (
        <>
          <label>Прощальное сообщение</label>
          <textarea rows={3} value={d.text || ''} onChange={e => onChange({ text: e.target.value })} />
        </>
      )}
    </div>
  );
}

function EdgeInspector({ edge, nodes, onChange, onDelete }) {
  const findLabel = (id) => {
    const n = nodes.find(x => x.id === id);
    return n ? (n.data?.label || n.data?.kind || n.id) : id;
  };
  const sourceNode = nodes.find(n => n.id === edge.source);
  const isCondition = sourceNode?.data?.kind === 'condition';
  return (
    <div>
      <div className="header">
        <h3 style={{margin:0}}>Связь</h3>
        <button className="small danger" onClick={onDelete}>Удалить</button>
      </div>
      <div className="muted" style={{marginBottom:8}}>
        <div><b>От:</b> {findLabel(edge.source)}</div>
        <div><b>К:</b> {findLabel(edge.target)}</div>
      </div>

      {isCondition && (
        <>
          <label>Ветвь условия</label>
          <select
            value={edge.sourceHandle || 'true'}
            onChange={e => onChange({ sourceHandle: e.target.value })}
          >
            <option value="true">да (true)</option>
            <option value="false">нет (false)</option>
          </select>
        </>
      )}

      <div className="muted" style={{fontSize:11, marginTop:12}}>
        Чтобы пересоединить — потяните конец стрелки на другой узел.<br/>
        Удалить также можно клавишей Delete / Backspace.
      </div>
    </div>
  );
}
