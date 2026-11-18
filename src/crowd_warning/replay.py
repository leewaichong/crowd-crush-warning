"""Render a self-contained viewer for parsed temporal density tables."""

import json
import math


_SOURCE = (
    'Source: Francois Gu, Benjamin Guiselin, and Denis Bartolo, '
    '<a href="https://doi.org/10.5281/zenodo.14050598">Zenodo record 14050598</a>. '
    'Record-level terms: <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>. '
    'Related paper: <a href="https://doi.org/10.1038/s41586-024-08514-6">Nature</a>.'
)
_MAX_POINTS = 2000
_COLORS = ("#175ea8", "#b33d26", "#21824a", "#7651a8")


def _display_points(points):
    """Keep endpoints and bucket extrema while bounding the rendered payload."""
    if len(points) <= _MAX_POINTS:
        return points
    bucket_count = (_MAX_POINTS - 2) // 2
    keep = {0, len(points) - 1}
    for bucket in range(bucket_count):
        start = 1 + bucket * (len(points) - 2) // bucket_count
        end = 1 + (bucket + 1) * (len(points) - 2) // bucket_count
        indices = range(start, end)
        if start < end:
            keep.add(min(indices, key=lambda i: points[i][1]))
            keep.add(max(indices, key=lambda i: points[i][1]))
    return [points[i] for i in sorted(keep)]


def render_density_replay(table):
    """Return light-only HTML for inspecting a parsed density table."""
    if table.get("source_format") != "zenodo-density-time-v1":
        raise ValueError("unsupported density table format")
    if table.get("time_reference") != "seconds_relative_to_festival_opening":
        raise ValueError("unsupported time reference")
    units = table.get("units", {})
    if units.get("time") != "s" or units.get("density") != "m^-2":
        raise ValueError("unexpected density table units")
    series = table.get("series")
    if not isinstance(series, list) or not series:
        raise ValueError("density table has no series")

    clean = []
    for index, item in enumerate(series):
        year = item["year"]
        source_points = item["points"]
        if not isinstance(source_points, list):
            raise ValueError("series points must be a list")
        points = []
        padding_started = False
        previous_time = None
        for point in source_points:
            if not isinstance(point, (list, tuple)) or len(point) != 2:
                raise ValueError("points must contain time and density")
            t, density = point
            if t is None and density is None:
                padding_started = True
                continue
            if t is None or density is None:
                raise ValueError("partial missing density pair")
            if padding_started:
                raise ValueError("missing pairs must be trailing padding")
            if (isinstance(t, bool) or isinstance(density, bool)
                    or not isinstance(t, (int, float)) or not isinstance(density, (int, float))
                    or not math.isfinite(t) or not math.isfinite(density) or density < 0):
                raise ValueError("invalid density point")
            if previous_time is not None and t <= previous_time:
                raise ValueError("point times must be strictly increasing")
            points.append([t, density])
            previous_time = t
        missing_count = item["missing_count"]
        if isinstance(missing_count, bool) or not isinstance(missing_count, int) or missing_count < 0:
            raise ValueError("missing_count must be a nonnegative integer")
        clean.append({
            "year": year,
            "points": _display_points(points),
            "observation_count": len(points),
            "missing_count": missing_count,
            "start": points[0][0] if points else None,
            "end": points[-1][0] if points else None,
            "color": _COLORS[index % len(_COLORS)],
        })

    payload = json.dumps(clean, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    encoded_source = json.dumps(_SOURCE).replace("</", "<\\/")
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Temporal density source viewer</title>
<style>
:root{{color-scheme:light;font:16px system-ui,sans-serif;color:#18212b;background:#fff}}body{{max-width:1100px;margin:2rem auto;padding:0 1rem}}h1{{font-size:1.6rem}}.controls{{display:flex;gap:1rem;align-items:center;flex-wrap:wrap}}select,input{{font:inherit}}input[type=range]{{flex:1;min-width:220px}}.chart-scroll{{max-width:100%;overflow-x:auto;border:1px solid #cbd3da}}svg{{display:block;width:100%;min-width:720px;height:auto;aspect-ratio:900 / 470;background:#fff}}.axis{{stroke:#59636e;stroke-width:1}}.line{{fill:none;stroke-width:2}}.grid{{stroke:#e5e9ed}}.cursor-line{{stroke:#a43b28;stroke-width:2;stroke-dasharray:5 4}}#readout{{font-variant-numeric:tabular-nums;min-height:1.5em}}footer{{border-top:1px solid #ccd3da;margin-top:1.5rem;padding-top:1rem;font-size:.92rem}}.legend{{display:flex;flex-wrap:wrap;gap:.5rem 1.25rem;margin:.75rem 0}}.legend-item{{display:inline-flex;align-items:center;gap:.4rem}}.swatch{{width:1rem;height:.2rem;display:inline-block}}.mobile-hint{{display:none}}@media(max-width:760px){{.mobile-hint{{display:block;font-size:.9rem;color:#4b5560}}}}
</style></head><body><h1>Temporal density source viewer</h1>
<p>Spatially averaged density from the source table. This is a technical source viewer, not an empirical warning result.</p>
<div class="controls"><label for="year">Year</label><select id="year"><option value="all">All years</option>{''.join(f'<option value="{_escape(item["year"])}">{_escape(item["year"])}</option>' for item in clean)}</select>
<label for="time">Time cursor</label><input id="time" type="range" min="0" max="0" step="1" value="0"></div>
<div id="readout" aria-live="polite" role="status"></div>
<div class="legend" aria-label="Year and missing row counts">{''.join(f'<span class="legend-item"><span class="swatch" style="background:{item["color"]}" aria-hidden="true"></span>{_escape(item["year"])} · missing padding rows: {item["missing_count"]}</span>' for item in clean)}</div>
<p class="mobile-hint">Scroll the chart horizontally to see the full time axis.</p>
<div class="chart-scroll" tabindex="0" role="region" aria-label="Scrollable density chart"><svg id="chart" viewBox="0 0 900 470" role="img" aria-label="Density by time relative to festival opening"><g id="plot"></g><text x="470" y="455" text-anchor="middle">Time relative to festival opening (s)</text><text x="18" y="205" text-anchor="middle" transform="rotate(-90 18 205)">Spatially averaged density (m^-2)</text></svg></div>
<p id="decimation"></p><p>Missing count is the number of omitted trailing source padding rows. Lines connect retained display samples. No values are interpolated.</p>
<footer><p>Limits: the source provides spatially averaged density and time relative to festival opening. The chart defines no hazard threshold or safety state and makes no forecast. Unknown camera scale and source gaps remain unknown.</p><p id="source"></p></footer>
<script>
'use strict';
const data={payload};
const source={encoded_source};
document.getElementById('source').innerHTML=source;
const plot=document.getElementById('plot'), year=document.getElementById('year'), cursor=document.getElementById('time'), readout=document.getElementById('readout');
const ns='http://www.w3.org/2000/svg', L=82, R=865, T=30, B=385;
function node(tag,attrs,text){{const e=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);if(text!==undefined)e.textContent=text;return e;}}
function formatSeconds(value){{return Number(value.toFixed(3)).toString();}}
function selected(){{return year.value==='all'?data:data.filter(s=>String(s.year)===year.value);}}
function draw(){{plot.replaceChildren();const sets=selected(), all=sets.flatMap(s=>s.points);if(!all.length){{readout.textContent='No numeric observations for this year.';cursor.disabled=true;return;}}cursor.disabled=false;
const xmin=Math.min(...all.map(p=>p[0])),xmax=Math.max(...all.map(p=>p[0])), rawMax=Math.max(...all.map(p=>p[1])),ymax=rawMax||1;
const x=t=>L+(t-xmin)/(xmax-xmin||1)*(R-L), y=v=>B-v/ymax*(B-T);
for(let i=0;i<=4;i++){{const value=ymax*(4-i)/4, py=y(value);plot.append(node('line',{{x1:L,y1:py,x2:R,y2:py,class:'grid'}}),node('text',{{x:L-9,y:py+4,'text-anchor':'end',class:'tick'}},Number(value.toPrecision(3)).toString()));}}
for(let i=0;i<=4;i++){{const value=xmin+(xmax-xmin)*i/4, px=x(value);plot.append(node('line',{{x1:px,y1:B,x2:px,y2:B+5,class:'axis'}}),node('text',{{x:px,y:B+22,'text-anchor':'middle',class:'tick'}},Number(value.toPrecision(3)).toString()));}}
plot.append(node('line',{{x1:L,y1:B,x2:R,y2:B,class:'axis'}}),node('line',{{x1:L,y1:T,x2:L,y2:B,class:'axis'}}));
for(let i=0;i<sets.length;i++){{const s=sets[i];let d='';for(let j=0;j<s.points.length;j++){{const p=s.points[j];d+=(j?' L':'M')+x(p[0])+' '+y(p[1]);}}plot.append(node('path',{{d,class:'line',stroke:s.color}}));}}
const allTimes=sets.flatMap(s=>s.points.map(p=>p[0])).sort((a,b)=>a-b);cursor.min='0';cursor.max=String(allTimes.length-1);cursor.dataset.times=JSON.stringify(allTimes);cursor.value=String(Math.floor(allTimes.length/2));
document.getElementById('decimation').textContent=data.some(s=>s.observation_count>s.points.length)?'Display decimation is active. Each series keeps endpoints and bucket extrema; slider timestamps are retained display samples.':'All numeric source observations are displayed.';
update();}}
function update(){{const times=JSON.parse(cursor.dataset.times||'[]');if(!times.length)return;const t=times[Number(cursor.value)], sets=selected();const xmin=Math.min(...sets.flatMap(s=>s.points.map(p=>p[0]))),xmax=Math.max(...sets.flatMap(s=>s.points.map(p=>p[0])));plot.querySelector('.cursor-line')?.remove();plot.append(node('line',{{x1:L+(t-xmin)/(xmax-xmin||1)*(R-L),y1:T,x2:L+(t-xmin)/(xmax-xmin||1)*(R-L),y2:B,class:'cursor-line'}}));
const vals=sets.map(s=>{{if(t<s.start||t>s.end)return s.year+': outside actual coverage';let best=null;for(const p of s.points)if(p[0]<=t)best=p;if(!best)return s.year+': outside actual coverage';return s.year+': retained display sample at or before cursor, '+best[1].toLocaleString()+' m^-2 at '+formatSeconds(best[0])+' s, age '+formatSeconds(t-best[0])+' s';}});readout.textContent='Cursor: '+formatSeconds(t)+' s relative to festival opening. '+vals.join(' | ');}}
year.addEventListener('change',draw);cursor.addEventListener('input',update);draw();
</script></body></html>'''


def _escape(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#x27;")
