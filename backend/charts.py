"""Build chart specifications exclusively from calculated comparison evidence."""
from math import isfinite
from backend.contracts import ChartPoint, GraphicVisual


def visual_types(comparison):
    values=comparison.historical_values
    ids=comparison.source_match_ids
    comparable=(not comparison.contribution and len(values)>=3 and len(values)==len(ids)
                and len(set(ids))==len(ids) and all(isfinite(v) and v>=0 for v in values)
                and isfinite(comparison.current_value) and comparison.current_value>=0)
    return ['numbers','historical_bars','historical_dots'] if comparable else ['numbers']


def model_visual_types(comparison):
    available=visual_types(comparison)
    # Multiple historical observations warrant a chart; two-value stories stay numeric.
    return available[1:] if len(available)>1 else ['numbers']


def build_visual(comparison,kind):
    if kind not in visual_types(comparison):
        raise ValueError('This chart is not supported by the available evidence.')
    if kind=='numbers':
        return GraphicVisual(kind=kind,title='Numbers only',caption='',unit=comparison.unit)
    history=list(zip(comparison.source_match_ids,comparison.historical_values))[-5:]
    points=[ChartPoint(label=f'P{i}',value=value,match_id=match_id)
            for i,(match_id,value) in enumerate(history,1)]
    points.append(ChartPoint(label='Now',value=comparison.current_value,is_current=True))
    return GraphicVisual(kind=kind,title='Recent comparable matches',unit=comparison.unit,points=points,
        caption=f'{len(history)} of {len(comparison.historical_values)} prior matches, oldest to newest; same period. Now = current.')
