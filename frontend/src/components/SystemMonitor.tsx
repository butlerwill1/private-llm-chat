import { useEffect, useState } from 'react'
import type { ChatApi, Metric, SystemMonitor as Monitor } from '../domain/chat'

function display(metric: Metric): string { return metric.value === null ? 'Unavailable' : `${metric.value}${metric.unit ? ` ${metric.unit}` : ''}` }
function bytes(value: number | string | null): string { return typeof value === 'number' ? `${(value / 1024 ** 3).toFixed(1)} GB` : 'Unavailable' }

export function SystemMonitor({ api }: { readonly api: ChatApi }) {
  const [monitor, setMonitor] = useState<Monitor | null>(null); const [error, setError] = useState<string | null>(null)
  useEffect(() => { let cancelled = false; const load = async () => { try { const next = await api.getSystemMonitor(); if (!cancelled) { setMonitor(next); setError(null) } } catch (caught) { if (!cancelled) setError(caught instanceof Error ? caught.message : 'Telemetry is unavailable.') } }; void load(); const timer = window.setInterval(() => void load(), 5000); return () => { cancelled = true; window.clearInterval(timer) } }, [api])
  if (!monitor) return <main className="monitor-main"><h1>System Monitor</h1><p role="status">{error ?? 'Loading local telemetry…'}</p></main>
  const s = monitor.snapshot
  return <main className="monitor-main"><header><h1>System Monitor</h1><p>Sampled {new Date(s.sampledAt).toLocaleTimeString()} · Local performance data only</p></header>{error ? <p role="alert" className="request-error">{error}</p> : null}
    <section className="metric-grid" aria-label="Hardware metrics"><Card label="GPU" metric={s.gpuName} /><Card label="GPU temperature" metric={s.gpuTemperature} /><Card label="GPU utilisation" metric={s.gpuUtilization} /><Card label="GPU power" metric={s.gpuPower} /><Card label="VRAM used" metric={{ ...s.vramUsed, value: bytes(s.vramUsed.value), unit: null }} /><Card label="VRAM free" metric={{ ...s.vramFree, value: bytes(s.vramFree.value), unit: null }} /><Card label="Model disk free" metric={{ ...s.diskFree, value: bytes(s.diskFree.value), unit: null }} /><Card label="CPU temperature" metric={s.cpuTemperature} /></section>
    <section className="monitor-section"><h2>Ollama and context</h2><p>Ollama: {display(s.ollamaStatus)}</p>{s.loadedModels.length ? s.loadedModels.map((model) => <p key={model.name}><strong>{model.name}</strong> · VRAM {bytes(model.vramBytes)} · context {model.contextLength?.toLocaleString() ?? 'Unavailable'} tokens. Exact live KV-cache occupancy is not provided by Ollama.</p>) : <p>No local model is currently loaded.</p>}</section>
    <section className="monitor-section"><h2>Performance telemetry</h2><p>{monitor.telemetry.sampleCount.toLocaleString()} samples retained · {bytes(monitor.telemetry.databaseBytes)} database</p><button type="button" onClick={() => void api.exportSystemMonitor()}>Export telemetry JSON</button></section>
  </main>
}
function Card({ label, metric }: { readonly label: string; readonly metric: Metric }) { return <article className="metric-card"><h2>{label}</h2><p>{display(metric)}</p>{metric.detail ? <small>{metric.detail}</small> : null}</article> }
