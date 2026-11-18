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


def _display_points(points):
    """Keep endpoints and extrema while bounding the rendered payload."""
    if len(points) <= _MAX_POINTS:
        return points
    # Each bucket contributes its min and max, preserving broad extrema while
    # fixing the output bound even for a rapidly alternating signal.
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
    for item in series:
        year = item["year"]
        pts = []
        for point in item["points"]:
            if len(point) != 2:
                raise ValueError("points must contain time and density")
            t, d = point
            if t is None and d is None:
                continue
            if t is None or d is None or not math.isfinite(t) or not math.isfinite(d) or d < 0:
                raise ValueError("invalid density point")
            pts.append([t, d])
        clean.append({"year": year, "points": _display_points(pts),
                      "observation_count": len(pts), "missing_count": item["missing_count"],
                      "start": pts[0][0] if pts else None, "end": pts[-1][0] if pts else None})
    payload = json.dumps(clean, ensure_ascii=True, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    encoded_source = json.dumps(_SOURCE).replace("</", "<\\/")
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Temporal density source viewer</title>
<style>
:root{{color-scheme:light;font:16px system-ui,sans-serif;color:#18212b;background:#fff}}body{{max-width:1100px;margin:2rem auto;padding:0 1rem}}h1{{font-size:1.6rem}}.controls{{display:flex;gap:1rem;align-items:center;flex-wrap:wrap}}select,input{{font:inherit}}input[type=range]{{flex:1;min-width:220px}}svg{{width:100%;height:430px;border:1px solid #cbd3da;background:#fff}}.axis{{stroke:#59636e;stroke-width:1}}.line{{fill:none;stroke-width:2}}.line[data-year=\"2022\"]{{stroke:#175ea8}}.line[data-year=\"2023\"]{{stroke:#b33d26}}.line[data-year=\"2024\"]{{stroke:#21824a}}.cursor{{stroke:#a43b28;stroke-dasharray:4 4}}.grid{{stroke:#e5e9ed}}#readout{{font-variant-numeric:tabular-nums;min-height:1.5em}}footer{{border-top:1px solid #ccd3da;margin-top:1.5rem;padding-top:1rem;font-size:.92rem}}.limit{{font-weight:600}}
</style></head><body><h1>Temporal density source viewer</h1>
<p>Spatially averaged density from the source table. This is a technical source viewer, not an empirical warning result.</p>
<div class="controls"><label for="year">Year</label><select id="year"><option value="all">All years</option>{''.join(f'<option value="{_escape(item["year"])}">{_escape(item["year"])}</option>' for item in clean)}</select>
<label for="time">Time cursor</label><input id="time" type="range" min="0" max="0" step="1" value="0"></div>
<div id="readout" aria-live="polite" role="status"></div>
<svg id="chart" viewBox="0 0 900 430" role="img" aria-label="Density by time relative to festival opening"><g id="plot"></g><text x="450" y="420" text-anchor="middle">Time relative to festival opening (s)</text><text x="18" y="210" text-anchor="middle" transform="rotate(-90 18 210)">Spatially averaged density (m^-2)</text></svg>
<p id="decimation"></p><p>Missing pairs are omitted. Lines break at missing source rows; no values are interpolated across gaps.</p>
<footer><p>Limits: the source provides spatially averaged density and time relative to festival opening. The chart defines no hazard threshold or safety state and makes no forecast. Unknown camera scale and source gaps remain unknown.</p><p id="source"></p></footer>
<script>
'use strict';
const data={payload};
const source={encoded_source};
document.getElementById('source').innerHTML=source;
const svg=document.getElementById('chart'), plot=document.getElementById('plot'), year=document.getElementById('year'), cursor=document.getElementById('time'), readout=document.getElementById('readout');
const ns='http://www.w3.org/2000/svg';
function node(tag,attrs,text){{const e=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,v);if(text!==undefined)e.textContent=text;return e;}}
function selected(){{return year.value==='all'?data:data.filter(s=>String(s.year)===year.value);}}
function draw(){{plot.replaceChildren();const sets=selected(), all=sets.flatMap(s=>s.points);if(!all.length){{readout.textContent='No numeric observations for this selection.';cursor.disabled=true;return;}}cursor.disabled=false;
const xmin=Math.min(...all.map(p=>p[0])),xmax=Math.max(...all.map(p=>p[0])),ymax=Math.max(...all.map(p=>p[1]),1),L=70,R=875,T=25,B=370;
for(let i=0;i<=4;i++){{const y=T+(B-T)*i/4;plot.append(node('line',{{x1:L,y1:y,x2:R,y2:y,class:'grid'}}));}}
plot.append(node('line',{{x1:L,y1:B,x2:R,y2:B,class:'axis'}}),node('line',{{x1:L,y1:T,x2:L,y2:B,class:'axis'}}));
for(const s of sets){{let d='',prev=null;for(const p of s.points){{const x=L+(p[0]-xmin)/(xmax-xmin||1)*(R-L),y=B-p[1]/ymax*(B-T);d+=(prev!==null&&p[0]>prev?' L':' M')+x+' '+y;prev=p[0];}}plot.append(node('path',{{d,class:'line','data-year':s.year}}));}}
const samples=sets.flatMap(s=>s.points.map(p=>p[0]));cursor.min='0';cursor.max=String(samples.length-1);cursor.value=String(Math.floor(samples.length/2));cursor.dataset.times=JSON.stringify(samples.sort((a,b)=>a-b));
document.getElementById('decimation').textContent=data.some(s=>s.observation_count>s.points.length)?'Display decimation is active. Endpoints and bucket extrema are retained; displayed points are a sample.':'All numeric source observations are displayed.';
update();}}
function update(){{const times=JSON.parse(cursor.dataset.times||'[]');if(!times.length)return;const t=times[Number(cursor.value)];const vals=selected().map(s=>{{let best=null;for(const p of s.points)if(p[0]===t)best=p;return s.year+': '+(best?best[1].toLocaleString()+' m^-2':'no observation at this time');}});readout.textContent='Time: '+t+' s relative to festival opening. '+vals.join(' | ')+' Missing source rows: '+selected().reduce((n,s)=>n+s.missing_count,0)+'.';}}
year.addEventListener('change',draw);cursor.addEventListener('input',update);draw();
</script></body></html>'''


def _escape(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#x27;")
