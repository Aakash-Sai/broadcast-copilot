import type { GraphicVisual } from './contracts';

/** All points arrive from the server's verified evidence, never from model output. */
export function HistoryChart({visual}: {visual?: GraphicVisual | null}) {
  const points=visual?.points ?? [];
  if (!visual || visual.kind==='numbers' || points.length<3) return null;
  const max=Math.max(1,...points.map(point=>point.value));
  const step=216/points.length;
  const description=points.map(point=>`${point.label}: ${point.value} ${visual.unit}`).join('; ');
  return <div className="history-chart">
    <div className="chart-heading">{visual.unit}</div>
    <svg viewBox="0 0 240 102" role="img" aria-label={`${visual.title}. ${description}`}>
      <title>{visual.title}</title><desc>{visual.caption}</desc>
      <line x1="18" y1="76" x2="234" y2="76" className="chart-axis"/>
      <text x="11" y="79" textAnchor="end" className="chart-zero">0</text>
      {points.map((point,i)=>{
        const x=18+step*(i+.5);
        const height=point.value/max*54;
        const y=76-height;
        return <g key={point.match_id ?? 'current'} className={point.is_current ? 'chart-current' : 'chart-history'}>
          <title>{`${point.is_current ? 'Current match' : point.match_id}: ${point.value} ${visual.unit}`}</title>
          {visual.kind==='historical_bars'
            ? <rect x={x-10} y={y} width="20" height={height} rx="2" className="chart-mark"/>
            : <><line x1={x} x2={x} y1="76" y2={y} className="chart-stem"/><circle cx={x} cy={y} r="4" className="chart-mark"/></>}
          <text x={x} y={Math.max(12,y-6)} textAnchor="middle" className="chart-value">{point.value}</text>
          <text x={x} y="94" textAnchor="middle" className="chart-label">{point.label}</text>
        </g>;
      })}
    </svg>
    <div className="chart-caption">{visual.caption}</div>
  </div>;
}
