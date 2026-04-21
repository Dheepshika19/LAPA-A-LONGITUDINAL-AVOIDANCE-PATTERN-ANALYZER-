/**
 * LAPA Charts & Visualizations
 * Handles all chart rendering and data visualization
 */

let emotionChart = null;
let trendChart = null;
let topicChart = null;

/**
 * Update emotion radar/bar chart
 */
function updateEmotionRadar(emotionData) {
  const ctx = document.getElementById('emotion-chart');
  if (!ctx) return;

  if (emotionChart) {
    emotionChart.destroy();
  }

  const labels = Object.keys(emotionData).map(k => k.charAt(0).toUpperCase() + k.slice(1));
  const data = Object.values(emotionData);

  emotionChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Emotion Distribution',
        data: data,
        backgroundColor: [
          'rgba(255, 107, 107, 0.6)',  // fear - red
          'rgba(100, 150, 200, 0.6)',  // sadness - blue
          'rgba(255, 165, 0, 0.6)',    // anger - orange
          'rgba(76, 205, 196, 0.6)',   // joy - teal
          'rgba(255, 192, 203, 0.6)',  // surprise - pink
          'rgba(200, 200, 200, 0.6)'   // neutral - gray
        ],
        borderColor: [
          'rgba(255, 107, 107, 1)',
          'rgba(100, 150, 200, 1)',
          'rgba(255, 165, 0, 1)',
          'rgba(76, 205, 196, 1)',
          'rgba(255, 192, 203, 1)',
          'rgba(200, 200, 200, 1)'
        ],
        borderWidth: 1,
        borderRadius: 4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      indexAxis: 'x',
      plugins: {
        legend: {
          display: false
        }
      },
      scales: {
        y: {
          beginAtZero: true,
          max: 1,
          ticks: {
            callback: function(value) {
              return (value * 100).toFixed(0) + '%';
            }
          }
        }
      }
    }
  });
}

/**
 * Update trend chart with multiple weeks
 */
function updateTrendChart(analyses) {
  const ctx = document.getElementById('trend-chart');
  if (!ctx) return;

  if (trendChart) {
    trendChart.destroy();
  }

  if (!analyses || analyses.length === 0) {
    return;
  }

  const labels = analyses.map(a => 'W' + a.weekId);
  const avoidanceData = analyses.map(a => a.avoidanceScore);
  const joyData = analyses.map(a => a.emotions.joy);

  trendChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Avoidance Score',
          data: avoidanceData,
          borderColor: 'rgba(201, 42, 42, 1)',
          backgroundColor: 'rgba(201, 42, 42, 0.1)',
          tension: 0.4,
          fill: true,
          pointRadius: 4,
          pointHoverRadius: 6,
          pointBackgroundColor: 'rgba(201, 42, 42, 1)'
        },
        {
          label: 'Joy Level',
          data: joyData,
          borderColor: 'rgba(42, 157, 143, 1)',
          backgroundColor: 'rgba(42, 157, 143, 0.1)',
          tension: 0.4,
          fill: true,
          pointRadius: 4,
          pointHoverRadius: 6,
          pointBackgroundColor: 'rgba(42, 157, 143, 1)'
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: {
        legend: {
          display: true,
          position: 'top'
        }
      },
      scales: {
        y: {
          beginAtZero: true,
          max: 1,
          ticks: {
            callback: function(value) {
              return (value * 100).toFixed(0) + '%';
            }
          }
        }
      }
    }
  });
}

/**
 * Update topic heatmap
 */
function updateTopicHeatmap(analyses) {
  const container = document.getElementById('topic-heatmap');
  if (!container || !analyses || analyses.length === 0) return;

  const allTopics = {};
  analyses.forEach(analysis => {
    Object.keys(analysis.topics).forEach(topic => {
      if (!allTopics[topic]) allTopics[topic] = [];
      allTopics[topic].push(analysis.topics[topic]);
    });
  });

  let html = '<div style="overflow-x: auto;">';
  html += '<table style="width: 100%; border-collapse: collapse; font-size: 12px;">';
  html += '<tr>';
  html += '<th style="text-align: left; padding: 8px; border-bottom: 1px solid #e0e8f0;">Topic</th>';
  
  analyses.forEach(a => {
    html += `<th style="padding: 8px; border-bottom: 1px solid #e0e8f0; text-align: center;">W${a.weekId}</th>`;
  });
  
  html += '</tr>';

  for (const [topic, data] of Object.entries(allTopics)) {
    html += '<tr>';
    html += `<td style="padding: 8px; border-bottom: 1px solid #e0e8f0; font-weight: 500; text-transform: capitalize;">${topic}</td>`;
    
    const maxValue = Math.max(...data);
    data.forEach((value) => {
      const intensity = maxValue > 0 ? value / maxValue : 0;
      const color = `rgba(42, 157, 143, ${intensity * 0.8})`;
      html += `<td style="padding: 8px; border-bottom: 1px solid #e0e8f0; background: ${color}; text-align: center; font-weight: 500;">${value}</td>`;
    });
    
    html += '</tr>';
  }

  html += '</table></div>';
  container.innerHTML = html;
}

/**
 * Update detailed charts on analysis page
 */
function updateDetailedCharts(latest, analyses) {
  // Emotion distribution
  const emotionContainer = document.getElementById('emotion-breakdown');
  if (emotionContainer) {
    const emotionHTML = Object.entries(latest.emotions)
      .map(([emotion, value]) => `
        <div class="stat-card" style="background: rgba(255,255,255,0.85); padding: 12px; border-radius: 12px;">
          <div style="font-size: 12px; color: #7a9aaa; text-transform: capitalize; margin-bottom: 6px;">${emotion}</div>
          <div style="font-size: 18px; font-weight: 700; color: #2a9d8f;">${(value * 100).toFixed(0)}%</div>
          <div style="width: 100%; height: 4px; background: #e0e8f0; border-radius: 2px; margin-top: 6px;">
            <div style="height: 100%; background: #2a9d8f; border-radius: 2px; width: ${value * 100}%;"></div>
          </div>
        </div>
      `).join('');
    emotionContainer.innerHTML = emotionHTML;
  }

  // Topic breakdown
  const topicContainer = document.getElementById('topic-breakdown');
  if (topicContainer) {
    const topicHTML = Object.entries(latest.topics)
      .filter(([topic, count]) => count > 0)
      .sort((a, b) => b[1] - a[1])
      .map(([topic, count]) => `
        <div class="stat-card" style="background: rgba(255,255,255,0.85); padding: 12px; border-radius: 12px;">
          <div style="font-size: 12px; color: #7a9aaa; text-transform: capitalize; margin-bottom: 6px;">${topic}</div>
          <div style="font-size: 18px; font-weight: 700; color: #1a6b8a;">${count}</div>
        </div>
      `).join('');
    topicContainer.innerHTML = topicHTML || '<div style="grid-column: 1/3; text-align: center; color: #7a9aaa; font-size: 13px;">No topics detected yet</div>';
  }
}

/**
 * Load topic cards with baseline comparison
 */
function loadTopicCards(currentTopics, baselineTopics) {
  const container = document.getElementById('topic-cards');
  if (!container) return;

  let html = '';
  for (const [topic, currentCount] of Object.entries(currentTopics)) {
    const baselineCount = baselineTopics ? baselineTopics[topic] || 0 : 0;
    const change = currentCount - baselineCount;
    const changePercent = baselineCount > 0 ? ((change / baselineCount) * 100).toFixed(0) : 0;
    const changeColor = change > 0 ? '#2a6a2a' : change < 0 ? '#c92a2a' : '#7a9aaa';
    const arrow = change > 0 ? '↑' : change < 0 ? '↓' : '→';

    html += `
      <div class="stat-card" style="background: rgba(255,255,255,0.85); padding: 12px; border-radius: 12px;">
        <div style="font-size: 12px; color: #7a9aaa; text-transform: capitalize; margin-bottom: 6px;">${topic}</div>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <div style="font-size: 18px; font-weight: 700; color: #1a6b8a;">${currentCount}</div>
          <div style="font-size: 12px; color: ${changeColor}; font-weight: 600;">${arrow} ${Math.abs(changePercent)}%</div>
        </div>
        ${baselineTopics ? `<div style="font-size: 10px; color: #7a9aaa; margin-top: 4px;">Baseline: ${baselineCount}</div>` : ''}
      </div>
    `;
  }

  container.innerHTML = html;
}

/**
 * Build history timeline
 */
function buildHistoryTimeline(analyses) {
  const timelineContainer = document.getElementById('history-timeline');
  if (!timelineContainer || !analyses || analyses.length === 0) {
    return;
  }

  let html = '';
  analyses.forEach((analysis, index) => {
    const flaggedClass = analysis.flagged ? 'flagged' : '';
    const flaggedColor = analysis.flagged ? '#c92a2a' : '#2a9d8f';

    html += `
      <div style="display: flex; gap: 12px; margin-bottom: 16px;">
        <div style="width: 40px; display: flex; flex-direction: column; align-items: center;">
          <div style="width: 10px; height: 10px; background: ${flaggedColor}; border-radius: 50%; margin-top: 8px;"></div>
          ${index < analyses.length - 1 ? '<div style="width: 2px; flex: 1; background: #e0e8f0; margin: 4px 0;"></div>' : ''}
        </div>
        <div style="flex: 1;">
          <div class="stat-card" style="background: rgba(255,255,255,0.85); padding: 12px; border-radius: 12px;">
            <div style="font-size: 13px; font-weight: 600; color: #1a3a4a; margin-bottom: 6px;">${analysis.weekLabel}</div>
            <div style="font-size: 12px; color: #7a9aaa; margin-bottom: 8px;">${analysis.entryCount} entry${analysis.entryCount !== 1 ? 'ies' : ''}</div>
            <div style="display: flex; justify-content: space-between; font-size: 11px;">
              <span style="color: #7a9aaa;">Avoidance: <span style="color: #1a3a4a; font-weight: 600;">${analysis.avoidanceScore.toFixed(2)}</span></span>
              <span style="color: #7a9aaa;">Mood: <span style="color: #1a3a4a; font-weight: 600;">${(analysis.emotions.joy * 100).toFixed(0)}%</span></span>
            </div>
            ${analysis.flagged ? `<div style="font-size: 11px; color: #c92a2a; margin-top: 8px;">⚠️ Flagged</div>` : ''}
          </div>
        </div>
      </div>
    `;
  });

  timelineContainer.innerHTML = html;
}

/**
 * Build history table
 */
function buildHistoryTable(analyses) {
  const tableContainer = document.getElementById('history-table');
  if (!tableContainer || !analyses || analyses.length === 0) {
    return;
  }

  let html = '<table style="width: 100%; border-collapse: collapse; font-size: 12px;">';
  html += '<tr style="background: rgba(42, 157, 143, 0.1);">';
  html += '<th style="text-align: left; padding: 10px 8px; border-bottom: 1px solid #e0e8f0; font-weight: 600;">Week</th>';
  html += '<th style="text-align: center; padding: 10px 8px; border-bottom: 1px solid #e0e8f0; font-weight: 600;">Entries</th>';
  html += '<th style="text-align: center; padding: 10px 8px; border-bottom: 1px solid #e0e8f0; font-weight: 600;">Avoidance</th>';
  html += '<th style="text-align: center; padding: 10px 8px; border-bottom: 1px solid #e0e8f0; font-weight: 600;">Mood</th>';
  html += '<th style="text-align: center; padding: 10px 8px; border-bottom: 1px solid #e0e8f0; font-weight: 600;">Status</th>';
  html += '</tr>';

  analyses.forEach((analysis) => {
    const statusColor = analysis.flagged ? '#c92a2a' : '#2a6a2a';
    const statusText = analysis.flagged ? '⚠️ Alert' : '✓ Good';

    html += `<tr>`;
    html += `<td style="padding: 10px 8px; border-bottom: 1px solid #e0e8f0; font-weight: 500;">${analysis.weekLabel}</td>`;
    html += `<td style="padding: 10px 8px; border-bottom: 1px solid #e0e8f0; text-align: center;">${analysis.entryCount}</td>`;
    html += `<td style="padding: 10px 8px; border-bottom: 1px solid #e0e8f0; text-align: center; color: ${analysis.avoidanceScore > 0.5 ? '#c92a2a' : '#2a6a2a'};">${analysis.avoidanceScore.toFixed(2)}</td>`;
    html += `<td style="padding: 10px 8px; border-bottom: 1px solid #e0e8f0; text-align: center;">${(analysis.emotions.joy * 100).toFixed(0)}%</td>`;
    html += `<td style="padding: 10px 8px; border-bottom: 1px solid #e0e8f0; text-align: center; color: ${statusColor}; font-weight: 600;">${statusText}</td>`;
    html += `</tr>`;
  });

  html += '</table>';
  tableContainer.innerHTML = html;
}

/**
 * Create empty state placeholder
 */
function createEmptyChartPlaceholder(containerId, message = 'No data available') {
  const container = document.getElementById(containerId);
  if (!container) return;

  container.innerHTML = `
    <div style="
      text-align: center;
      padding: 40px 20px;
      color: #7a9aaa;
      font-size: 13px;
    ">
      <div style="font-size: 36px; margin-bottom: 12px;">📊</div>
      ${message}
    </div>
  `;
}

/**
 * Initialize all charts when page loads
 */
document.addEventListener('DOMContentLoaded', () => {
  // Charts will be initialized when pages are loaded via PageLoader
});

/**
 * Destroy all charts (for cleanup)
 */
function destroyAllCharts() {
  if (emotionChart) emotionChart.destroy();
  if (trendChart) trendChart.destroy();
  if (topicChart) topicChart.destroy();
}
