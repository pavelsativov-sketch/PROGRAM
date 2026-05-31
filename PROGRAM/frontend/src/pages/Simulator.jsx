import React, { useEffect, useMemo, useRef, useState } from 'react';
import ReactFlow, { Background, Handle, Position } from 'reactflow';
import { api } from '../api';
import { IconLab } from '../icons.jsx';

// Узел live-графа: подсвечивается, если совпадает с current_node_id.
function MiniNode({ data }) {
  const k = data.kind || 'message';
  const cls = `node-box ${k}` + (data.active ? ' active-node' : '');
  return (
    <div className={cls} style={{minWidth: 130, fontSize: 12, padding: '6px 10px'}}>
      <Handle type="target" position={Position.Top} />
      <div className="node-title" style={{fontSize: 12}}>{data.label || k}</div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}
const miniNodeTypes = { default: MiniNode };

export default function Simulator() {
  const [conv, setConv] = useState(null);
  const [text, setText] = useState('Здравствуйте');
  const [flows, setFlows] = useState([]);
  const [flowId, setFlowId] = useState('');
  const [flowGraph, setFlowGraph] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const endRef = useRef();

  useEffect(() => { api.flows.list().then(fs => { setFlows(fs); const a = fs.find(f => f.is_active); if (a) setFlowId(String(a.id)); }); }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [conv?.messages?.length]);

  // Загружаем граф выбранного флоу для отрисовки и подсветки активного узла.
  useEffect(() => {
    if (!flowId) { setFlowGraph(null); return; }
    api.flows.get(flowId).then(f => setFlowGraph(f.graph || null)).catch(() => setFlowGraph(null));
  }, [flowId]);

  const activeNodeId = conv?.current_node_id || '';
  const liveNodes = useMemo(() => {
    if (!flowGraph) return [];
    return (flowGraph.nodes || []).map(n => ({
      ...n,
      type: 'default',
      data: { ...n.data, active: n.id === activeNodeId },
    }));
  }, [flowGraph, activeNodeId]);
  const liveEdges = useMemo(() => {
    if (!flowGraph) return [];
    return (flowGraph.edges || []).map(e => ({
      ...e,
      animated: e.source === activeNodeId,
      style: e.source === activeNodeId
        ? { stroke: 'var(--terracotta)', strokeWidth: 2 }
        : { stroke: 'var(--line-2)', strokeWidth: 1.5 },
    }));
  }, [flowGraph, activeNodeId]);

  const send = async () => {
    if (!text.trim() || busy) return;
    setBusy(true); setError('');
    try {
      const payload = { text, external_id: 'sim-user' };
      if (conv?.conversation_id) payload.conversation_id = conv.conversation_id;
      if (flowId) payload.flow_id = Number(flowId);
      const r = await api.conversations.sim(payload);
      setConv(r);
      setText('');
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const reset = () => { setConv(null); setError(''); };

  // Чистим служебные слоты (начинаются с _)
  const visibleVars = conv?.variables
    ? Object.fromEntries(Object.entries(conv.variables).filter(([k]) => !k.startsWith('_')))
    : {};

  const status = conv?.status || 'idle';
  const statusLabel = {
    active: '🤖 AI ведёт диалог',
    handoff: '⚠ Переведено на менеджера',
    pending_payment: '💳 Ожидает оплаты',
    payment_review: '💳 Проверка оплаты',
    closed: '✅ Закрыт',
    idle: 'Не запущен',
  }[status] || status;

  return (
    <div className="fade-in">
      <div className="header">
        <div>
          <h2 style={{margin:0, fontStyle:'italic'}}>Симулятор</h2>
          <div className="muted">Тестируйте сценарий и AI-агента, не трогая реальные каналы.</div>
        </div>
        <div className="row">
          <select value={flowId} onChange={e => { setFlowId(e.target.value); setConv(null); }}>
            {flows.map(f => <option key={f.id} value={f.id}>{f.name}{f.is_active ? ' (активен)' : ''}</option>)}
          </select>
          <button className="secondary" onClick={reset}>↻ Начать заново</button>
        </div>
      </div>

      {error && <div className="card" style={{color:'var(--err)'}}>Ошибка: {error}</div>}

      <div className="sim-grid">
        <div className="card">
          <div className="row" style={{marginBottom:8, justifyContent:'space-between'}}>
            <span className={`badge ${status === 'idle' ? 'active' : status}`}>{statusLabel}</span>
            {conv?.conversation_id && <span className="muted mono">#{conv.conversation_id}</span>}
          </div>
          <div className="chat">
            <div className="chat-msgs">
              {!conv && <div className="empty-state" style={{padding:'24px 8px'}}>
                <IconLab size={26} />
                <div style={{marginTop:8}}>Напишите первое сообщение, чтобы начать диалог.</div>
              </div>}
              {conv?.messages?.map(m => (
                <div key={m.id} className={`msg ${m.role}`}>
                  {m.role === 'bot' && <div style={{fontSize:11, color:'var(--ink-3)', marginBottom:2, fontWeight:600}}>· бот</div>}
                  {m.text}
                </div>
              ))}
              {busy && <div className="msg bot" style={{opacity:0.7, fontStyle:'italic'}}><span className="pulse-dot" /> печатает…</div>}
              <div ref={endRef} />
            </div>
            <div className="chat-input">
              <input
                value={text}
                onChange={e => setText(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
                placeholder="Сообщение клиента..."
                disabled={busy}
              />
              <button onClick={send} disabled={busy || !text.trim()}>{busy ? '…' : 'Отправить'}</button>
            </div>
          </div>
        </div>

        <div>
          {/* Live-граф флоу: подсвечивается активный узел и анимируется
              исходящая связь, чтобы видеть, куда движется диалог. */}
          {liveNodes.length > 0 && (
            <div className="card" style={{padding:12}}>
              <div className="header" style={{marginBottom:8}}>
                <h4 className="serif" style={{margin:0, fontStyle:'italic'}}>Где сейчас диалог</h4>
                {activeNodeId && <span className="muted mono" style={{fontSize:11}}>{activeNodeId}</span>}
              </div>
              <div style={{height: 240, border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', background: 'var(--paper-2)'}}>
                <ReactFlow
                  nodes={liveNodes}
                  edges={liveEdges}
                  nodeTypes={miniNodeTypes}
                  fitView
                  proOptions={{ hideAttribution: true }}
                  nodesDraggable={false}
                  nodesConnectable={false}
                  elementsSelectable={false}
                  panOnScroll={false}
                  zoomOnScroll={false}
                >
                  <Background gap={16} color="var(--line)" />
                </ReactFlow>
              </div>
            </div>
          )}

          <div className="card">
            <h4 className="serif" style={{margin:'0 0 10px', fontStyle:'italic'}}>Собранные данные</h4>
            {Object.keys(visibleVars).length === 0 ? (
              <div className="muted">Здесь появятся слоты, которые AI извлечёт из диалога: имя, телефон, адрес и т.д.</div>
            ) : (
              <table>
                <tbody>
                  {Object.entries(visibleVars).map(([k, v]) => (
                    <tr key={k}>
                      <td style={{color:'var(--ink-3)', width:'42%'}} className="mono">{k}</td>
                      <td style={{fontWeight:600, fontFamily:'var(--serif)'}}>{String(v) || <span className="muted">—</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
