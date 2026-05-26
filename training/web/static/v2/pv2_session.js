/* Professional v2 单次全息解剖 — GPS+海拔+三轴+步态+分圈 */
(function () {
  const ROOT = location.pathname.startsWith('/training') ? '/training' : '';
  const SID = window.PV2_SESSION_ID;

  function setText(id, value) { const el = document.getElementById(id); if (el) el.textContent = value; }

  function fmtPace(sec) {
    if (!sec || sec <= 0) return '-';
    const m = Math.floor(sec / 60);
    const s = Math.round(sec % 60);
    return m + ':' + String(s).padStart(2, '0') + '/km';
  }

  async function load() {
    let d = null;
    try {
      const r = await fetch(ROOT + '/api/v2/session/' + SID + '/full');
      if (!r.ok) throw new Error('HTTP ' + r.status);
      d = await r.json();
    } catch (e) {
      setText('pv2-session-title', '加载失败：' + e.message);
      return;
    }
    renderMeta(d.meta);
    renderMap(d.track);
    renderElev(d.track);
    renderTriaxis(d.track, d.meta);
    renderZones(d.hr_zones);
    renderGait(d.gait);
    renderLaps(d.laps);
  }

  function renderMeta(meta) {
    if (!meta) return;
    const date = (meta.start_time || '').slice(0, 10);
    setText('pv2-session-title', `${date} · ${meta.training_type || meta.sport || '训练'} · ${(meta.distance_km || 0).toFixed(2)} km`);
    const box = document.getElementById('pv2-session-meta');
    while (box.firstChild) box.removeChild(box.firstChild);
    const items = [
      ['距离', (meta.distance_km || 0).toFixed(2) + ' km'],
      ['时长', Math.round((meta.duration_sec || 0) / 60) + ' min'],
      ['平均HR', meta.avg_hr || '-'],
      ['配速', fmtPace(meta.avg_pace_sec)],
      ['步频', meta.avg_cadence ? (meta.avg_cadence * 2) + ' spm' : '-'],
      ['爬升', (meta.total_ascent || 0) + ' m'],
      ['hr_TSS', (meta.hr_tss || 0).toFixed(1)],
      ['HR Drift', meta.hr_drift_pct !== null && meta.hr_drift_pct !== undefined ? meta.hr_drift_pct.toFixed(1) + '%' : '-'],
      ['EF', meta.efficiency_factor !== null && meta.efficiency_factor !== undefined ? meta.efficiency_factor.toFixed(2) : '-'],
      ['VO2max', meta.vo2max ? meta.vo2max.toFixed(1) : '-'],
      ['Recovery', meta.recovery_hours ? meta.recovery_hours + 'h' : '-'],
    ];
    for (const [k, v] of items) {
      const div = document.createElement('div');
      div.className = 'pv2-meta-item';
      const kSpan = document.createTextNode(k + ' ');
      const b = document.createElement('b');
      b.textContent = v;
      div.appendChild(kSpan);
      div.appendChild(b);
      box.appendChild(div);
    }
  }

  function colorForPace(paceSec) {
    if (!paceSec) return '#94a3b8';
    if (paceSec < 240) return '#dc2626';     // <4:00 红
    if (paceSec < 300) return '#f59e0b';     // 4:00-5:00 橙
    if (paceSec < 360) return '#16a34a';     // 5:00-6:00 绿
    if (paceSec < 420) return '#0ea5e9';     // 6:00-7:00 蓝
    return '#6366f1';                         // >7:00 紫
  }

  function renderMap(track) {
    const dom = document.getElementById('pv2-map');
    if (!track || track.length === 0) {
      dom.textContent = '无 GPS 数据';
      dom.style.display = 'flex';
      dom.style.alignItems = 'center';
      dom.style.justifyContent = 'center';
      dom.style.color = '#94a3b8';
      return;
    }
    const pts = track.filter(p => p.lat && p.lon);
    if (pts.length === 0) {
      dom.textContent = '无 GPS 坐标';
      return;
    }
    const map = L.map(dom).setView([pts[0].lat, pts[0].lon], 14);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap',
      maxZoom: 18,
    }).addTo(map);

    // 配速色阶分段：相邻两点一段，速度 mps -> 配速秒
    for (let i = 1; i < pts.length; i++) {
      const a = pts[i - 1], b = pts[i];
      const speed = b.speed_mps || a.speed_mps;
      const paceSec = speed && speed > 0 ? (1000 / speed) : null;
      L.polyline([[a.lat, a.lon], [b.lat, b.lon]], { color: colorForPace(paceSec), weight: 4, opacity: 0.85 }).addTo(map);
    }
    L.circleMarker([pts[0].lat, pts[0].lon], { radius: 6, color: '#16a34a', fillOpacity: 1 }).addTo(map).bindTooltip('起点');
    L.circleMarker([pts[pts.length - 1].lat, pts[pts.length - 1].lon], { radius: 6, color: '#dc2626', fillOpacity: 1 }).addTo(map).bindTooltip('终点');
    map.fitBounds(L.latLngBounds(pts.map(p => [p.lat, p.lon])).pad(0.05));
  }

  function renderElev(track) {
    const dom = document.getElementById('pv2-elev');
    if (!track || track.length === 0) return;
    const data = track.filter(p => p.altitude_m !== null && p.altitude_m !== undefined).map(p => [p.t_offset_s / 60, p.altitude_m]);
    if (data.length === 0) { dom.textContent = '无海拔数据'; return; }
    const chart = echarts.init(dom);
    chart.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 50, right: 30, top: 10, bottom: 30 },
      xAxis: { type: 'value', name: '分钟', axisLabel: { color: '#94a3b8' } },
      yAxis: { type: 'value', name: 'm', axisLabel: { color: '#94a3b8' }, scale: true },
      series: [{ type: 'line', smooth: true, showSymbol: false, data, areaStyle: { color: 'rgba(245,158,11,.18)' }, lineStyle: { color: '#f59e0b' } }],
    });
    window.addEventListener('resize', () => chart.resize());
  }

  function renderTriaxis(track, meta) {
    const dom = document.getElementById('pv2-triaxis');
    if (!track || track.length === 0) { dom.textContent = '无逐秒数据'; return; }
    const tMin = track.map(p => p.t_offset_s / 60);
    const hr = track.map(p => p.hr || null);
    const pace = track.map(p => p.speed_mps && p.speed_mps > 0 ? (1000 / p.speed_mps) : null);
    const cad = track.map(p => p.cadence ? p.cadence * 2 : null);
    const chart = echarts.init(dom);
    chart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['HR', '配速 (s/km)', '步频 (spm)'], top: 0 },
      grid: { left: 60, right: 70, top: 35, bottom: 50 },
      xAxis: { type: 'value', name: '分钟', axisLabel: { color: '#94a3b8' } },
      yAxis: [
        { type: 'value', name: 'HR/spm', axisLabel: { color: '#94a3b8' } },
        { type: 'value', name: 'pace', axisLabel: { color: '#94a3b8' }, inverse: true },
      ],
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 6 }],
      series: [
        { name: 'HR', type: 'line', smooth: true, showSymbol: false, data: tMin.map((t, i) => [t, hr[i]]), itemStyle: { color: '#dc2626' } },
        { name: '配速 (s/km)', type: 'line', smooth: true, showSymbol: false, yAxisIndex: 1, data: tMin.map((t, i) => [t, pace[i]]), itemStyle: { color: '#0f766e' } },
        { name: '步频 (spm)', type: 'line', smooth: true, showSymbol: false, data: tMin.map((t, i) => [t, cad[i]]), itemStyle: { color: '#3b82f6' }, lineStyle: { opacity: 0.6 } },
      ],
    });
    window.addEventListener('resize', () => chart.resize());
  }

  function renderZones(z) {
    const dom = document.getElementById('pv2-zone-pie');
    if (!z) { dom.textContent = '无心率分区数据'; return; }
    const chart = echarts.init(dom);
    const data = [
      { name: 'Z1 恢复', value: z.zone1_sec || 0, itemStyle: { color: '#94a3b8' } },
      { name: 'Z2 有氧', value: z.zone2_sec || 0, itemStyle: { color: '#0f766e' } },
      { name: 'Z3 节奏', value: z.zone3_sec || 0, itemStyle: { color: '#f59e0b' } },
      { name: 'Z4 阈值', value: z.zone4_sec || 0, itemStyle: { color: '#dc2626' } },
      { name: 'Z5 极量', value: z.zone5_sec || 0, itemStyle: { color: '#7c3aed' } },
    ].filter(d => d.value > 0);
    chart.setOption({
      tooltip: { trigger: 'item', formatter: p => `${p.name}: ${Math.round(p.value / 60)} min (${p.percent}%)` },
      series: [{ type: 'pie', radius: ['45%', '70%'], data, label: { formatter: '{b}\n{d}%', fontSize: 11 } }],
    });
    window.addEventListener('resize', () => chart.resize());
  }

  function renderGait(g) {
    const dom = document.getElementById('pv2-gait-radar');
    if (!g || !g.sample_count) { dom.textContent = '此次训练无步态数据'; return; }
    const chart = echarts.init(dom);
    chart.setOption({
      tooltip: {},
      radar: {
        indicator: [
          { name: '垂直振幅 (mm)', max: 120 },
          { name: '触地时间 (ms)', max: 350 },
          { name: '步长 (mm)', max: 1500 },
          { name: '垂直比 (%)', max: 12 },
          { name: '左右平衡', max: 100 },
        ],
        axisName: { color: '#475569', fontSize: 11 },
      },
      series: [{
        type: 'radar',
        data: [{
          value: [
            g.avg_vertical_oscillation || 0,
            g.avg_ground_contact_time || 0,
            g.avg_step_length_mm || 0,
            g.avg_vertical_ratio || 0,
            g.avg_stance_time_balance || 50,
          ],
          name: '步态',
          areaStyle: { color: 'rgba(15,118,110,.2)' },
          lineStyle: { color: '#0f766e' },
        }],
      }],
    });
    window.addEventListener('resize', () => chart.resize());
  }

  function renderLaps(laps) {
    const dom = document.getElementById('pv2-laps');
    while (dom.firstChild) dom.removeChild(dom.firstChild);
    if (!laps || laps.length === 0) { const i = document.createElement('i'); i.style.color = '#94a3b8'; i.textContent = '无分圈'; dom.appendChild(i); return; }
    const tbl = document.createElement('table');
    tbl.className = 'pv2-table';
    const thead = document.createElement('thead');
    const trh = document.createElement('tr');
    ['#', '距离', '时长', '配速', 'HR', '步频', '爬升'].forEach(t => {
      const th = document.createElement('th'); th.textContent = t; trh.appendChild(th);
    });
    thead.appendChild(trh); tbl.appendChild(thead);
    const tbody = document.createElement('tbody');
    for (const l of laps) {
      const tr = document.createElement('tr');
      const cells = [
        l.lap_index + 1,
        (l.distance_km || 0).toFixed(2) + ' km',
        Math.round((l.duration_sec || 0) / 60) + ':' + String(Math.round((l.duration_sec || 0) % 60)).padStart(2, '0'),
        fmtPace(l.avg_pace_sec),
        l.avg_hr || '-',
        l.avg_cadence ? (l.avg_cadence * 2) : '-',
        (l.total_ascent || 0) + ' m',
      ];
      for (const v of cells) {
        const td = document.createElement('td'); td.textContent = v; tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
    tbl.appendChild(tbody);
    dom.appendChild(tbl);
  }

  load();
})();
