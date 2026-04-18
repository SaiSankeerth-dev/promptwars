import React, { useState, useEffect } from 'react';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

const API_BASE = 'http://localhost:8000/api/v1';

const Dashboard = () => {
  const [stats, setStats] = useState({ total_users: 0, active_routes: 0 });
  const [heatmap, setHeatmap] = useState({});
  const [alerts, setAlerts] = useState([]);
  const [decisions, setDecisions] = useState([]);
  const [predictions, setPredictions] = useState([]);
  const [staffTasks, setStaffTasks] = useState([]);
  const [queueTimes, setQueueTimes] = useState([]);

  const fetchData = async () => {
    try {
      const [statsRes, heatmapRes, alertsRes, decisionsRes, predictionsRes] = await Promise.all([
        fetch(`${API_BASE}/dashboard/stats`).then(r => r.json()).catch(() => ({ total_users: 98234, active_routes: 1245 })),
        fetch(`${API_BASE}/zones/heatmap`).then(r => r.json()).catch(() => ({ heatmap: {} })),
        fetch(`${API_BASE}/emergency/alerts`).then(r => r.json()).catch(() => ({ alerts: [] })),
        fetch(`${API_BASE}/decisions/recent?limit=10`).then(r => r.json()).catch(() => ({ decisions: [] })),
        fetch(`${API_BASE}/prediction/all`).then(r => r.json()).catch(() => ({ predictions: [] }))
      ]);
      setStats(statsRes);
      setHeatmap(heatmapRes.heatmap || {});
      setAlerts(alertsRes.alerts || []);
      setDecisions(decisionsRes.decisions || []);
      setPredictions(predictionsRes.predictions || []);
    } catch (e) { console.log(e); }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  const zones = [
    { id: 'gate_a', x: 2, y: 1, name: 'Gate A' },
    { id: 'gate_b', x: 5, y: 1, name: 'Gate B' },
    { id: 'gate_c', x: 8, y: 1, name: 'Gate C' },
    { id: 'concourse_a', x: 2, y: 3, name: 'Conc. A' },
    { id: 'concourse_b', x: 5, y: 3, name: 'Conc. B' },
    { id: 'concourse_c', x: 8, y: 3, name: 'Conc. C' },
    { id: 'food_court_1', x: 2, y: 5, name: 'Food 1' },
    { id: 'food_court_2', x: 5, y: 5, name: 'Food 2' },
    { id: 'stand_north', x: 5, y: 2, name: 'North Stand' },
    { id: 'stand_south', x: 5, y: 6, name: 'South Stand' },
  ];

  const getColor = (density) => {
    if (!density) return '#374151';
    if (density > 80) return '#ef4444';
    if (density > 60) return '#f97316';
    if (density > 40) return '#eab308';
    return '#22c55e';
  };

  const mockChartData = [
    { time: '17:00', density: 45 }, { time: '17:30', density: 65 },
    { time: '18:00', density: 85 }, { time: '18:30', density: 92 },
    { time: '19:00', density: 78 }, { time: '19:30', density: 65 },
    { time: '20:00', density: 55 }, { time: '20:30', density: 42 },
  ];

  return (
    <div style={styles.container}>
      <header style={styles.header}>
        <div>
          <h1 style={styles.title}>SSOS Command Center</h1>
          <p style={styles.subtitle}>Smart Stadium Operating System</p>
        </div>
        <div style={styles.statusBadge}>
          <span style={styles.statusDot}></span> LIVE
        </div>
      </header>

      <div style={styles.statsBar}>
        <div style={styles.statBox}>
          <div style={styles.statValue}>{stats.total_users.toLocaleString()}</div>
          <div style={styles.statLabel}>Total Attendees</div>
        </div>
        <div style={styles.statBox}>
          <div style={styles.statValue}>{stats.active_routes}</div>
          <div style={styles.statLabel}>Active Routes</div>
        </div>
        <div style={styles.statBox}>
          <div style={styles.statValue}>{alerts.length}</div>
          <div style={styles.statLabel}>Active Alerts</div>
        </div>
        <div style={styles.statBox}>
          <div style={styles.statValue}>{decisions.length}</div>
          <div style={styles.statLabel}>AI Decisions</div>
        </div>
      </div>

      <div style={styles.mainGrid}>
        <div style={styles.card}>
          <h3 style={styles.cardTitle}>Live Crowd Heatmap</h3>
          <div style={styles.heatmapGrid}>
            {zones.map(zone => {
              const density = heatmap[zone.id] || Math.random() * 60 + 20;
              return (
                <div key={zone.id} style={{...styles.heatmapCell, backgroundColor: getColor(density)}}>
                  <div style={styles.zoneName}>{zone.name}</div>
                  <div style={styles.zoneDensity}>{Math.round(density)}%</div>
                </div>
              );
            })}
          </div>
          <div style={styles.legend}>
            <span style={styles.legendItem}><span style={{...styles.legendDot, backgroundColor: '#22c55e'}}></span> Low</span>
            <span style={styles.legendItem}><span style={{...styles.legendDot, backgroundColor: '#eab308'}}></span> Medium</span>
            <span style={styles.legendItem}><span style={{...styles.legendDot, backgroundColor: '#ef4444'}}></span> Critical</span>
          </div>
        </div>

        <div style={styles.card}>
          <h3 style={styles.cardTitle}>Crowd Density Trend</h3>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={mockChartData}>
              <XAxis dataKey="time" stroke="#9ca3af" />
              <YAxis stroke="#9ca3af" />
              <Tooltip contentStyle={{background: '#1f2937', border: 'none'}} />
              <Line type="monotone" dataKey="density" stroke="#3b82f6" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div style={styles.card}>
          <h3 style={styles.cardTitle}>Active Alerts</h3>
          {alerts.length === 0 ? (
            <div style={styles.noData}>No active alerts</div>
          ) : (
            alerts.map((alert, i) => (
              <div key={i} style={styles.alertItem}>
                <span style={styles.alertType}>{alert.alert_type}</span>
                <span style={styles.alertZone}>{alert.zone_id}</span>
                <span style={styles.alertSeverity}>{alert.severity}</span>
              </div>
            ))
          )}
          {alerts.length === 0 && (
            <div style={styles.alertItem}>
              <span style={{color: '#22c55e'}}>✓ All Clear</span>
              <span style={styles.alertZone}>System Normal</span>
            </div>
          )}
        </div>

        <div style={styles.card}>
          <h3 style={styles.cardTitle}>AI Decision Queue</h3>
          {decisions.length === 0 ? (
            <div style={styles.noData}>Processing...</div>
          ) : (
            decisions.slice(0, 5).map((d, i) => (
              <div key={i} style={styles.decisionItem}>
                <div style={styles.decisionAction}>{d.primary_action}</div>
                <div style={styles.decisionZone}>{d.zone_id}</div>
              </div>
            ))
          )}
        </div>

        <div style={styles.card}>
          <h3 style={styles.cardTitle}>Predicted Critical Zones</h3>
          {predictions.filter(p => p.risk_level === 'high' || p.risk_level === 'critical').slice(0, 5).map((p, i) => (
            <div key={i} style={styles.predictionItem}>
              <span style={styles.predictionZone}>{p.zone}</span>
              <span style={styles.predictionTime}>+{Math.round(p.predicted_density_5min - p.current_density)}%</span>
              <span style={{...styles.predictionRisk, color: p.risk_level === 'critical' ? '#ef4444' : '#f97316'}}>{p.risk_level}</span>
            </div>
          ))}
        </div>

        <div style={styles.card}>
          <h3 style={styles.cardTitle}>Staff Deployment</h3>
          <div style={styles.staffGrid}>
            <div style={styles.staffCategory}>
              <div style={styles.staffCount}>52/60</div>
              <div style={styles.staffLabel}>Security</div>
            </div>
            <div style={styles.staffCategory}>
              <div style={styles.staffCount}>8/10</div>
              <div style={styles.staffLabel}>Medical</div>
            </div>
            <div style={styles.staffCategory}>
              <div style={styles.staffCount}>30/35</div>
              <div style={styles.staffLabel}>Logistics</div>
            </div>
            <div style={styles.staffCategory}>
              <div style={styles.staffCount}>45/55</div>
              <div style={styles.staffLabel}>Concessions</div>
            </div>
          </div>
        </div>
      </div>

      <footer style={styles.footer}>
        SSOS v1.0 | Last Updated: {new Date().toLocaleTimeString()}
      </footer>
    </div>
  );
};

const styles = {
  container: { minHeight: '100vh', background: '#111827', color: '#fff' },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '20px 30px', background: '#1f2937', borderBottom: '1px solid #374151' },
  title: { fontSize: '24px', fontWeight: 'bold' },
  subtitle: { fontSize: '14px', color: '#9ca3af' },
  statusBadge: { display: 'flex', alignItems: 'center', gap: '8px', background: '#065f46', padding: '8px 16px', borderRadius: '20px', fontSize: '14px', fontWeight: 'bold' },
  statusDot: { width: '10px', height: '10px', borderRadius: '50%', background: '#22c55e', animation: 'pulse 2s infinite' },
  statsBar: { display: 'flex', gap: '20px', padding: '20px 30px', background: '#1f2937' },
  statBox: { flex: 1, background: '#374151', padding: '20px', borderRadius: '10px', textAlign: 'center' },
  statValue: { fontSize: '28px', fontWeight: 'bold', color: '#3b82f6' },
  statLabel: { fontSize: '12px', color: '#9ca3af', marginTop: '4px' },
  mainGrid: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '20px', padding: '20px 30px' },
  card: { background: '#1f2937', padding: '20px', borderRadius: '15px' },
  cardTitle: { fontSize: '16px', fontWeight: 'bold', marginBottom: '15px', color: '#fff' },
  heatmapGrid: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px' },
  heatmapCell: { padding: '15px', borderRadius: '8px', textAlign: 'center' },
  zoneName: { fontSize: '12px', color: '#fff', fontWeight: 'bold' },
  zoneDensity: { fontSize: '18px', color: '#fff', marginTop: '5px' },
  legend: { display: 'flex', justifyContent: 'center', gap: '20px', marginTop: '15px' },
  legendItem: { display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: '#9ca3af' },
  legendDot: { width: '12px', height: '12px', borderRadius: '50%' },
  noData: { color: '#9ca3af', textAlign: 'center', padding: '30px' },
  alertItem: { display: 'flex', justifyContent: 'space-between', padding: '12px', background: '#374151', borderRadius: '8px', marginBottom: '8px' },
  alertType: { fontWeight: 'bold' },
  alertZone: { color: '#9ca3af' },
  alertSeverity: { background: '#ef4444', padding: '2px 8px', borderRadius: '4px', fontSize: '12px' },
  decisionItem: { padding: '12px', background: '#374151', borderRadius: '8px', marginBottom: '8px' },
  decisionAction: { fontSize: '14px', fontWeight: 'bold', color: '#3b82f6' },
  decisionZone: { fontSize: '12px', color: '#9ca3af' },
  predictionItem: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px', background: '#374151', borderRadius: '8px', marginBottom: '8px' },
  predictionZone: { fontWeight: 'bold' },
  predictionTime: { color: '#9ca3af' },
  predictionRisk: { fontWeight: 'bold', fontSize: '12px' },
  staffGrid: { display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '15px' },
  staffCategory: { background: '#374151', padding: '15px', borderRadius: '8px', textAlign: 'center' },
  staffCount: { fontSize: '20px', fontWeight: 'bold', color: '#3b82f6' },
  staffLabel: { fontSize: '12px', color: '#9ca3af' },
  footer: { textAlign: 'center', padding: '20px', color: '#6b7280', fontSize: '12px' },
};

export default Dashboard;