/* Professional v2 趋势页 */
(function () {
  const ROOT = location.pathname.startsWith('/training') ? '/training' : '';

  async function load() {
    const [load180, zones12] = await Promise.all([
      fetch(ROOT + '/api/v2/trends/load?days=180').then(r => r.ok ? r.json() : null),
      fetch(ROOT + '/api/v2/trends/zones?weeks=12').then(r => r.ok ? r.json() : null),
    ]);
    if (load180) {
      renderLoadLong(load180);
      renderACWR(load180);
    }
    if (zones12) renderZoneStack(zones12);
  }

  function renderLoadLong(data) {
    const dom = document.getElementById('pv2-load-long');
    const chart = echarts.init(dom);
    const dates = data.series.map(r => r.date);
    chart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { data: ['daily TSS', 'CTL', 'ATL', 'TSB'], top: 0 },
      grid: { left: 50, right: 50, top: 35, bottom: 50 },
      xAxis: { type: 'category', data: dates, axisLabel: { color: '#94a3b8', fontSize: 10 } },
      yAxis: { type: 'value', axisLabel: { color: '#94a3b8' } },
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 6 }],
      series: [
        { name: 'daily TSS', type: 'bar', data: data.series.map(r => r.daily_tss), itemStyle: { color: 'rgba(148,163,184,.6)' } },
        { name: 'CTL', type: 'line', smooth: true, data: data.series.map(r => r.ctl), itemStyle: { color: '#0f766e' }, lineStyle: { width: 3 } },
        { name: 'ATL', type: 'line', smooth: true, data: data.series.map(r => r.atl), itemStyle: { color: '#f59e0b' } },
        { name: 'TSB', type: 'line', smooth: true, data: data.series.map(r => r.tsb), itemStyle: { color: '#3b82f6' } },
      ],
    });
    window.addEventListener('resize', () => chart.resize());
  }

  function renderACWR(data) {
    const dom = document.getElementById('pv2-acwr-band');
    const chart = echarts.init(dom);
    const dates = data.series.map(r => r.date);
    chart.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 50, right: 30, top: 30, bottom: 50 },
      xAxis: { type: 'category', data: dates, axisLabel: { color: '#94a3b8', fontSize: 10 } },
      yAxis: { type: 'value', max: 2.5, axisLabel: { color: '#94a3b8' } },
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 6 }],
      series: [
        {
          name: 'ACWR',
          type: 'line',
          smooth: true,
          data: data.series.map(r => r.acwr),
          itemStyle: { color: '#dc2626' },
          markArea: {
            silent: true,
            data: [
              [{ yAxis: 0.8, itemStyle: { color: 'rgba(34,197,94,.10)' } }, { yAxis: 1.3 }],
              [{ yAxis: 1.5, itemStyle: { color: 'rgba(220,38,38,.12)' } }, { yAxis: 2.5 }],
            ],
          },
          markLine: {
            silent: true,
            data: [{ yAxis: 1.0, lineStyle: { type: 'dashed', color: '#94a3b8' }, label: { formatter: '基线 1.0' } }],
          },
        },
      ],
    });
    window.addEventListener('resize', () => chart.resize());
  }

  function renderZoneStack(data) {
    const dom = document.getElementById('pv2-zone-stack');
    const chart = echarts.init(dom);
    const weeks = data.series.map(r => r.week_key);
    const toMin = arr => arr.map(v => Math.round((v || 0) / 60));
    const z = i => data.series.map(r => r['z' + i]);
    chart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      legend: { data: ['Z1 恢复', 'Z2 有氧', 'Z3 节奏', 'Z4 阈值', 'Z5 极量'], top: 0 },
      grid: { left: 50, right: 30, top: 35, bottom: 40 },
      xAxis: { type: 'category', data: weeks, axisLabel: { color: '#94a3b8' } },
      yAxis: { type: 'value', name: 'min', axisLabel: { color: '#94a3b8' } },
      series: [
        { name: 'Z1 恢复', type: 'bar', stack: 'z', data: toMin(z(1)), itemStyle: { color: '#94a3b8' } },
        { name: 'Z2 有氧', type: 'bar', stack: 'z', data: toMin(z(2)), itemStyle: { color: '#0f766e' } },
        { name: 'Z3 节奏', type: 'bar', stack: 'z', data: toMin(z(3)), itemStyle: { color: '#f59e0b' } },
        { name: 'Z4 阈值', type: 'bar', stack: 'z', data: toMin(z(4)), itemStyle: { color: '#dc2626' } },
        { name: 'Z5 极量', type: 'bar', stack: 'z', data: toMin(z(5)), itemStyle: { color: '#7c3aed' } },
      ],
    });
    window.addEventListener('resize', () => chart.resize());
  }

  load();
})();
