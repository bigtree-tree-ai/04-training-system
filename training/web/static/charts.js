// Chart.js 数据加载函数

async function loadPMC(canvasId) {
    const res = await fetch((window.BASE_PATH || '') + '/api/pmc?days=90');
    const data = await res.json();

    new Chart(document.getElementById(canvasId), {
        type: 'line',
        data: {
            labels: data.dates,
            datasets: [
                {
                    label: 'CTL (体能)',
                    data: data.ctl,
                    borderColor: '#2196F3',
                    backgroundColor: 'rgba(33,150,243,0.1)',
                    fill: false,
                    tension: 0.3,
                    pointRadius: 0,
                    borderWidth: 2,
                },
                {
                    label: 'ATL (疲劳)',
                    data: data.atl,
                    borderColor: '#f44336',
                    fill: false,
                    tension: 0.3,
                    pointRadius: 0,
                    borderWidth: 2,
                },
                {
                    label: 'TSB (状态)',
                    data: data.tsb,
                    borderColor: '#4CAF50',
                    backgroundColor: 'rgba(76,175,80,0.08)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 0,
                    borderWidth: 2,
                },
            ]
        },
        options: {
            responsive: true,
            interaction: { mode: 'index', intersect: false },
            scales: {
                x: {
                    ticks: { maxTicksLimit: 10, font: { size: 11 } },
                    grid: { display: false },
                },
                y: { grid: { color: '#f0f0f0' } },
            },
            plugins: {
                legend: { position: 'top' },
                tooltip: {
                    callbacks: {
                        label: function(ctx) {
                            return ctx.dataset.label + ': ' + ctx.raw.toFixed(1);
                        }
                    }
                }
            }
        }
    });
}

async function loadWeeklyVolume(canvasId) {
    const res = await fetch((window.BASE_PATH || '') + '/api/weekly-volume?weeks=12');
    const data = await res.json();

    new Chart(document.getElementById(canvasId), {
        type: 'bar',
        data: {
            labels: data.labels,
            datasets: [
                {
                    label: '跑量 (km)',
                    data: data.run_km,
                    backgroundColor: 'rgba(33,150,243,0.7)',
                    borderRadius: 4,
                },
                {
                    label: 'hrTSS',
                    data: data.hr_tss,
                    backgroundColor: 'rgba(255,152,0,0.5)',
                    borderRadius: 4,
                    yAxisID: 'y1',
                }
            ]
        },
        options: {
            responsive: true,
            scales: {
                y: { title: { display: true, text: 'km' }, grid: { color: '#f0f0f0' } },
                y1: { position: 'right', title: { display: true, text: 'TSS' }, grid: { display: false } },
            },
            plugins: { legend: { position: 'top' } }
        }
    });
}

async function loadZoneDistribution(canvasId) {
    const res = await fetch((window.BASE_PATH || '') + '/api/zone-distribution?days=14');
    const data = await res.json();

    if (!data.labels.length) return;

    new Chart(document.getElementById(canvasId), {
        type: 'doughnut',
        data: {
            labels: data.labels,
            datasets: [{
                data: data.values,
                backgroundColor: data.colors,
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { position: 'bottom' },
                tooltip: {
                    callbacks: {
                        label: function(ctx) {
                            return ctx.label + ': ' + ctx.raw + '%';
                        }
                    }
                }
            }
        }
    });
}
