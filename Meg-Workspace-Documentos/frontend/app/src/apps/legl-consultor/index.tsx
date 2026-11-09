/**
 * Copyright © 2026 Cristian Rodriguez
 * All rights reserved.
 *
 * App: LEGL Consultor Legal v2.0
 * Layout tipo Siri + Herramientas (Comparador, Calculadora, Checklist)
 * Chatbot sin IA basado en corpus legal estructurado
 */
import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Scale, Send, MessageSquare, Sparkles,
  Loader2, PanelLeft, PanelRight,
  GitCompare, Calculator, ListChecks
} from 'lucide-react';
import { megalodonClient } from '@/lib/api-client';

// Componentes de herramientas
import ComparadorArticulos from './components/ComparadorArticulos';
import CalculadoraPlazos from './components/CalculadoraPlazos';
import ChecklistGenerator from './components/ChecklistGenerator';
import CoberturaCorpusPanel from './components/CoberturaCorpusPanel';

interface Mensaje {
  id: string;
  tipo: 'usuario' | 'bot';
  texto: string;
  metadata?: any;
  timestamp: Date;
}

type ToolView = 'chat' | 'comparador' | 'calculadora' | 'checklist';

const SUGERENCIAS = [
  "¿Qué procedimiento aplica para una obra de 5 millones?",
  "¿Cuáles son los requisitos de una licitación pública?",
  "Artículo 40 de la LOPSRM",
  "¿Qué es la adjudicación directa?",
  "Plazos para publicar convocatoria",
  "Garantías de seriedad de proposición",
  "Ajuste de costos por INPC",
  "Responsabilidades administrativas LGRA",
  "Compara el artículo 40 entre LOPSRM y LAASSP",
  "Genera checklist para licitación pública",
];

const HERRAMIENTAS = [
  { id: 'chat' as ToolView, label: 'Chat', icon: MessageSquare, color: 'text-amber-400', bg: 'bg-amber-500/10' },
  { id: 'comparador' as ToolView, label: 'Comparador', icon: GitCompare, color: 'text-violet-400', bg: 'bg-violet-500/10' },
  { id: 'calculadora' as ToolView, label: 'Plazos', icon: Calculator, color: 'text-cyan-400', bg: 'bg-cyan-500/10' },
  { id: 'checklist' as ToolView, label: 'Checklist', icon: ListChecks, color: 'text-emerald-400', bg: 'bg-emerald-500/10' },
];

export default function LeglConsultorApp() {
  const [mensajes, setMensajes] = useState<Mensaje[]>([
    {
      id: 'bienvenida',
      tipo: 'bot',
      texto: '¡Hola! Soy **LEGL**, tu asistente legal.\n\nPuedo ayudarte con:\n💬 **Chat** — Consulta cualquier tema legal\n⚖️ **Comparador** — Compara artículos entre LOPSRM y LAASSP\n📅 **Plazos** — Calcula fechas según procedimiento\n✅ **Checklist** — Genera listas según tu proceso\n\n¿Qué necesitas?',
      timestamp: new Date(),
    }
  ]);
  const [input, setInput] = useState('');
  const [cargando, setCargando] = useState(false);
  const [toolActiva, setToolActiva] = useState<ToolView>('chat');
  const [panelVisible, setPanelVisible] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [mensajes]);

  const enviarMensaje = async (texto: string = input) => {
    if (!texto.trim()) return;

    const msgUsuario: Mensaje = {
      id: Date.now().toString(),
      tipo: 'usuario',
      texto,
      timestamp: new Date(),
    };

    setMensajes(prev => [...prev, msgUsuario]);
    setInput('');
    setCargando(true);

    try {
      const res = await megalodonClient.legal.chat(texto);

      const msgBot: Mensaje = {
        id: (Date.now() + 1).toString(),
        tipo: 'bot',
        texto: res.respuesta,
        metadata: { intencion: res.intencion_detectada, parametros: res.parametros },
        timestamp: new Date(),
      };
      setMensajes(prev => [...prev, msgBot]);
    } catch {
      setMensajes(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        tipo: 'bot',
        texto: 'No pude procesar eso. Intenta con algo como "Artículo 40 LOPSRM", "¿qué procedimiento para 5 millones?", o "genera checklist"',
        timestamp: new Date(),
      }]);
    } finally {
      setCargando(false);
    }
  };

  return (
    <div className="h-full flex bg-[#0a0a0f] text-zinc-100 overflow-hidden">
      {/* ═══════════════════════════════════════════════════════════════
          PANEL IZQUIERDO: Chat tipo Siri
         ═══════════════════════════════════════════════════════════════ */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="border-b border-zinc-800/80 px-5 py-3 shrink-0 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-xl bg-amber-500/15 border border-amber-500/30 flex items-center justify-center">
              <Scale className="w-4 h-4 text-amber-400" />
            </div>
            <div>
              <h1 className="font-bold text-sm text-zinc-100">LEGL</h1>
              <p className="text-[10px] text-zinc-500">Consultor Legal — Sin IA</p>
            </div>
          </div>
          <button
            onClick={() => setPanelVisible(!panelVisible)}
            className="p-1.5 rounded-lg bg-zinc-800/60 border border-zinc-700 hover:bg-zinc-700/60 
                     text-zinc-500 transition-colors"
          >
            {panelVisible ? <PanelRight className="w-3.5 h-3.5" /> : <PanelLeft className="w-3.5 h-3.5" />}
          </button>
        </div>

        <CoberturaCorpusPanel />
        {/* Área de mensajes — estilo conversación */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-5 space-y-4">
          {mensajes.map((msg, idx) => (
            <motion.div
              key={msg.id}
              initial={{ opacity: 0, y: 10, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ duration: 0.25, delay: idx === 0 ? 0 : 0.05 }}
              className={`flex ${msg.tipo === 'usuario' ? 'justify-end' : 'justify-start'}`}
            >
              <div className={`
                max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed
                ${msg.tipo === 'usuario'
                  ? 'bg-amber-500/15 text-amber-100 border border-amber-500/25'
                  : 'bg-zinc-800/60 text-zinc-200 border border-zinc-700/50'
                }
              `}>
                {msg.tipo === 'bot' && (
                  <div className="flex items-center gap-2 mb-2 pb-2 border-b border-zinc-700/30">
                    <div className="w-5 h-5 rounded-full bg-amber-500/20 flex items-center justify-center">
                      <Scale className="w-2.5 h-2.5 text-amber-400" />
                    </div>
                    <span className="text-[10px] font-semibold text-amber-400 tracking-wide uppercase">LEGL</span>
                    <span className="text-[10px] text-zinc-600 ml-auto">
                      {msg.timestamp.toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                )}
                <div className="whitespace-pre-wrap">{msg.texto}</div>
              </div>
            </motion.div>
          ))}

          {cargando && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex justify-start">
              <div className="bg-zinc-800/60 rounded-2xl px-4 py-3 border border-zinc-700/50">
                <div className="flex items-center gap-3">
                  <div className="relative">
                    <div className="w-5 h-5 rounded-full bg-amber-500/20 flex items-center justify-center">
                      <Loader2 className="w-3 h-3 text-amber-400 animate-spin" />
                    </div>
                    <div className="absolute inset-0 rounded-full bg-amber-400/20 animate-ping" />
                  </div>
                  <span className="text-xs text-zinc-500">Consultando corpus legal...</span>
                </div>
              </div>
            </motion.div>
          )}
        </div>

        {/* Sugerencias rápidas */}
        {mensajes.length < 4 && (
          <div className="px-5 pb-2 shrink-0">
            <p className="text-[10px] text-zinc-600 mb-2 uppercase tracking-wider font-medium">Preguntas frecuentes</p>
            <div className="flex flex-wrap gap-1.5">
              {SUGERENCIAS.slice(0, 6).map((s, i) => (
                <button
                  key={i}
                  onClick={() => enviarMensaje(s)}
                  className="text-[11px] px-3 py-1.5 rounded-full bg-zinc-800/40 border border-zinc-700/50 
                           hover:bg-zinc-700/40 hover:border-zinc-600 transition-all text-zinc-500 hover:text-zinc-300"
                >
                  {s.length > 35 ? s.substring(0, 35) + '...' : s}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Input tipo Siri */}
        <div className="border-t border-zinc-800/80 p-4 shrink-0">
          <div className="relative flex items-center gap-3 bg-zinc-800/40 border border-zinc-700/50 rounded-2xl px-4 py-3 
                        focus-within:border-amber-500/30 focus-within:bg-zinc-800/60 transition-all">
            <Sparkles className="w-4 h-4 text-amber-500/50 shrink-0" />
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && enviarMensaje()}
              placeholder="Pregúntame cualquier cosa legal..."
              className="flex-1 bg-transparent text-sm text-zinc-100 placeholder-zinc-600 
                       focus:outline-hidden"
            />
            <button
              onClick={() => enviarMensaje()}
              disabled={cargando || !input.trim()}
              className="w-8 h-8 rounded-full bg-amber-500/15 border border-amber-500/30 
                       flex items-center justify-center text-amber-400 hover:bg-amber-500/25 
                       transition-all disabled:opacity-20 disabled:cursor-not-allowed shrink-0"
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          </div>
          <p className="text-[9px] text-zinc-700 mt-2 text-center">
            LEGL consulta el corpus legal estructurado. Sin IA. Información orientativa.
          </p>
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════════════
          PANEL DERECHO: Herramientas (Comparador, Calculadora, Checklist)
         ═══════════════════════════════════════════════════════════════ */}
      <AnimatePresence>
        {panelVisible && (
          <motion.div
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 340, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: 'easeInOut' }}
            className="border-l border-zinc-800/80 bg-zinc-900/30 flex flex-col overflow-hidden shrink-0"
          >
            {/* Tabs de herramientas */}
            <div className="border-b border-zinc-800/80 p-2">
              <div className="flex gap-1">
                {HERRAMIENTAS.map(tool => {
                  const Icon = tool.icon;
                  const isActive = toolActiva === tool.id;
                  return (
                    <button
                      key={tool.id}
                      onClick={() => setToolActiva(tool.id)}
                      className={`flex-1 flex items-center justify-center gap-1.5 px-2 py-2 rounded-lg 
                                text-[10px] font-medium transition-all
                        ${isActive 
                          ? `${tool.bg} ${tool.color} border border-current` 
                          : 'text-zinc-600 hover:text-zinc-400 hover:bg-zinc-800/40'
                        }`}
                    >
                      <Icon className="w-3.5 h-3.5" />
                      {tool.label}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Contenido de la herramienta activa */}
            <div className="flex-1 overflow-auto p-4">
              <AnimatePresence mode="wait">
                <motion.div
                  key={toolActiva}
                  initial={{ opacity: 0, x: 10 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -10 }}
                  transition={{ duration: 0.15 }}
                  className="h-full"
                >
                  {toolActiva === 'chat' && (
                    <div className="h-full flex flex-col items-center justify-center text-center space-y-4">
                      <div className="w-16 h-16 rounded-2xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
                        <MessageSquare className="w-8 h-8 text-amber-400" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-zinc-300">Modo Chat</p>
                        <p className="text-xs text-zinc-500 mt-1">Usa el panel izquierdo para conversar con LEGL</p>
                      </div>
                      <div className="space-y-2 w-full">
                        <p className="text-[10px] text-zinc-600 uppercase tracking-wider">Ejemplos de consultas</p>
                        {["¿Qué procedimiento para $10M?", "Artículo 52 LOPSRM", "Requisitos de fallo"].map((ej, i) => (
                          <button
                            key={i}
                            onClick={() => enviarMensaje(ej)}
                            className="w-full text-left text-xs px-3 py-2 rounded-lg bg-zinc-800/40 
                                     border border-zinc-700/50 text-zinc-500 hover:text-zinc-300 
                                     hover:border-zinc-600 transition-all"
                          >
                            {ej}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                  {toolActiva === 'comparador' && <ComparadorArticulos />}
                  {toolActiva === 'calculadora' && <CalculadoraPlazos />}
                  {toolActiva === 'checklist' && <ChecklistGenerator />}
                </motion.div>
              </AnimatePresence>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
