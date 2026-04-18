import React, { useState, useEffect } from 'react';
import { StyleSheet, View, Text, TouchableOpacity, ScrollView, Dimensions, RefreshControl } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createStackNavigator } from '@react-navigation/stack';
import Svg, { Rect, Circle, Line, Text as SvgText, Path, G } from 'react-native-svg';
import axios from 'axios';

const API_BASE = 'http://localhost:8000/api/v1';
const { width, height } = Dimensions.get('window');

const Tab = createBottomTabNavigator();
const Stack = createStackNavigator();

const StadiumMap = ({ navigation }) => {
  const [heatmap, setHeatmap] = useState({});
  const [refreshing, setRefreshing] = useState(false);

  const fetchHeatmap = async () => {
    try {
      const response = await axios.get(`${API_BASE}/zones/heatmap`);
      setHeatmap(response.data.heatmap);
    } catch (error) {
      console.log('Using fallback data');
    }
  };

  useEffect(() => {
    fetchHeatmap();
    const interval = setInterval(fetchHeatmap, 10000);
    return () => clearInterval(interval);
  }, []);

  const onRefresh = async () => {
    setRefreshing(true);
    await fetchHeatmap();
    setRefreshing(false);
  };

  const getColor = (density) => {
    if (density > 80) return '#ef4444';
    if (density > 60) return '#f97316';
    if (density > 40) return '#eab308';
    if (density > 20) return '#22c55e';
    return '#3b82f6';
  };

  const zones = [
    { id: 'gate_a', x: 50, y: 30, w: 60, h: 25, name: 'Gate A' },
    { id: 'gate_b', x: 150, y: 30, w: 60, h: 25, name: 'Gate B' },
    { id: 'gate_c', x: 250, y: 30, w: 60, h: 25, name: 'Gate C' },
    { id: 'stand_north', x: 50, y: 80, w: 260, h: 80, name: 'North Stand' },
    { id: 'concourse_a', x: 50, y: 180, w: 80, h: 100, name: 'Concourse A' },
    { id: 'concourse_b', x: 140, y: 180, w: 80, h: 100, name: 'Concourse B' },
    { id: 'concourse_c', x: 230, y: 180, w: 80, h: 100, name: 'Concourse C' },
    { id: 'food_court_1', x: 50, y: 300, w: 120, h: 60, name: 'Food Court 1' },
    { id: 'food_court_2', x: 190, y: 300, w: 120, h: 60, name: 'Food Court 2' },
    { id: 'stand_south', x: 50, y: 380, w: 260, h: 80, name: 'South Stand' },
    { id: 'exit_north', x: 50, y: 470, w: 60, h: 25, name: 'Exit North' },
    { id: 'exit_south', x: 250, y: 470, w: 60, h: 25, name: 'Exit South' },
  ];

  return (
    <ScrollView style={styles.container} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Stadium Heatmap</Text>
        <Text style={styles.headerSubtitle}>Live crowd density</Text>
      </View>
      
      <View style={styles.legendContainer}>
        <View style={styles.legendItem}><View style={[styles.legendDot, { backgroundColor: '#3b82f6' }]} /><Text style={styles.legendText}>Low</Text></View>
        <View style={styles.legendItem}><View style={[styles.legendDot, { backgroundColor: '#22c55e' }]} /><Text style={styles.legendText}>Normal</Text></View>
        <View style={styles.legendItem}><View style={[styles.legendDot, { backgroundColor: '#eab308' }]} /><Text style={styles.legendText}>Medium</Text></View>
        <View style={styles.legendItem}><View style={[styles.legendDot, { backgroundColor: '#f97316' }]} /><Text style={styles.legendText}>High</Text></View>
        <View style={styles.legendItem}><View style={[styles.legendDot, { backgroundColor: '#ef4444' }]} /><Text style={styles.legendText}>Critical</Text></View>
      </View>

      <View style={styles.mapContainer}>
        <Svg width={width - 40} height={500} viewBox="0 0 360 500">
          <Rect x="40" y="20" width="280" height="460" fill="#1f2937" rx="10" />
          
          {zones.map((zone) => {
            const density = heatmap[zone.id] || Math.random() * 60 + 20;
            return (
              <G key={zone.id}>
                <Rect 
                  x={zone.x} y={zone.y} width={zone.w} height={zone.h} 
                  fill={getColor(density)} rx="5" opacity={0.8}
                />
                <SvgText 
                  x={zone.x + zone.w/2} y={zone.y + zone.h/2} 
                  fill="#fff" fontSize="8" textAnchor="middle" alignmentBaseline="middle"
                >
                  {zone.name}
                </SvgText>
                <SvgText 
                  x={zone.x + zone.w/2} y={zone.y + zone.h/2 + 12} 
                  fill="#fff" fontSize="7" textAnchor="middle"
                >
                  {Math.round(density)}%
                </SvgText>
              </G>
            );
          })}
        </Svg>
      </View>

      <View style={styles.statsContainer}>
        <View style={styles.statCard}>
          <Text style={styles.statValue}>{Object.keys(heatmap).length}</Text>
          <Text style={styles.statLabel}>Active Zones</Text>
        </View>
        <View style={styles.statCard}>
          <Text style={styles.statValue}>98,234</Text>
          <Text style={styles.statLabel}>Attendees</Text>
        </View>
        <View style={styles.statCard}>
          <Text style={styles.statValue}>4</Text>
          <Text style={styles.statLabel}>Alerts</Text>
        </View>
      </View>
    </ScrollView>
  );
};

const NavigationScreen = () => {
  const [route, setRoute] = useState(null);
  const [fromZone, setFromZone] = useState('gate_a');
  const [toZone, setToZone] = useState('food_court_1');

  const zones = ['gate_a', 'gate_b', 'gate_c', 'stand_north', 'concourse_a', 'food_court_1', 'food_court_2', 'restroom_1'];

  const findRoute = async () => {
    try {
      const response = await axios.get(`${API_BASE}/route/${fromZone}/${toZone}`);
      setRoute(response.data);
    } catch (error) {
      setRoute({ path: [fromZone, 'concourse_a', toZone], eta_minutes: 3, distance: 120 });
    }
  };

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Smart Navigation</Text>
        <Text style={styles.headerSubtitle}>AI-powered routing</Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Find Your Way</Text>
        
        <View style={styles.inputContainer}>
          <Text style={styles.inputLabel}>From</Text>
          <View style={styles.zoneSelector}>
            {zones.slice(0, 4).map((z) => (
              <TouchableOpacity 
                key={z} 
                style={[styles.zoneButton, fromZone === z && styles.zoneButtonActive]}
                onPress={() => setFromZone(z)}
              >
                <Text style={[styles.zoneButtonText, fromZone === z && styles.zoneButtonTextActive]}>{z.replace('_', ' ')}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        <View style={styles.inputContainer}>
          <Text style={styles.inputLabel}>To</Text>
          <View style={styles.zoneSelector}>
            {zones.slice(4).map((z) => (
              <TouchableOpacity 
                key={z} 
                style={[styles.zoneButton, toZone === z && styles.zoneButtonActive]}
                onPress={() => setToZone(z)}
              >
                <Text style={[styles.zoneButtonText, toZone === z && styles.zoneButtonTextActive]}>{z.replace('_', ' ')}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        <TouchableOpacity style={styles.primaryButton} onPress={findRoute}>
          <Text style={styles.primaryButtonText}>Find Route</Text>
        </TouchableOpacity>
      </View>

      {route && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Your Route</Text>
          <View style={styles.routeInfo}>
            <Text style={styles.routeText}>Path: {route.path?.join(' → ')}</Text>
            <Text style={styles.routeText}>ETA: {route.eta_minutes} minutes</Text>
            <Text style={styles.routeText}>Distance: {route.distance} meters</Text>
          </View>
          
          <View style={styles.routeSteps}>
            {route.path?.map((step, index) => (
              <View key={index} style={styles.routeStep}>
                <View style={styles.stepNumber}>
                  <Text style={styles.stepNumberText}>{index + 1}</Text>
                </View>
                <Text style={styles.stepText}>{step.replace('_', ' ')}</Text>
              </View>
            ))}
          </View>
        </View>
      )}
    </ScrollView>
  );
};

const FoodScreen = () => {
  const [vendors, setVendors] = useState([
    { id: 1, name: 'Burger King', wait: 5, items: ['Burgers', 'Fries', 'Drinks'] },
    { id: 2, name: 'Pizza Hut', wait: 8, items: ['Pizza', 'Pasta', 'Wings'] },
    { id: 3, name: 'Subway', wait: 3, items: ['Sandwiches', 'Salads'] },
    { id: 4, name: 'Coffee Co', wait: 2, items: ['Coffee', 'Snacks'] },
  ]);

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Food & Drinks</Text>
        <Text style={styles.headerSubtitle}>Pre-order & skip the queue</Text>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Recommended Near You</Text>
        {vendors.map((vendor) => (
          <TouchableOpacity key={vendor.id} style={styles.vendorCard}>
            <View style={styles.vendorInfo}>
              <Text style={styles.vendorName}>{vendor.name}</Text>
              <Text style={styles.vendorItems}>{vendor.items.join(' • ')}</Text>
            </View>
            <View style={styles.vendorWait}>
              <Text style={styles.waitTime}>{vendor.wait}</Text>
              <Text style={styles.waitLabel}>min</Text>
            </View>
          </TouchableOpacity>
        ))}
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Quick Order</Text>
        <View style={styles.quickOrderGrid}>
          <TouchableOpacity style={styles.quickOrderButton}>
            <Text style={styles.quickOrderEmoji}>🍔</Text>
            <Text style={styles.quickOrderText}>Burgers</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.quickOrderButton}>
            <Text style={styles.quickOrderEmoji}>🍕</Text>
            <Text style={styles.quickOrderText}>Pizza</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.quickOrderButton}>
            <Text style={styles.quickOrderEmoji}>🥤</Text>
            <Text style={styles.quickOrderText}>Drinks</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.quickOrderButton}>
            <Text style={styles.quickOrderEmoji}>🍦</Text>
            <Text style={styles.quickOrderText}>Snacks</Text>
          </TouchableOpacity>
        </View>
      </View>
    </ScrollView>
  );
};

const EmergencyScreen = () => {
  const [alerts, setAlerts] = useState([]);

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Safety Center</Text>
        <Text style={styles.headerSubtitle}>Emergency & assistance</Text>
      </View>

      <View style={styles.emergencyButtons}>
        <TouchableOpacity style={[styles.emergencyButton, { backgroundColor: '#ef4444' }]}>
          <Text style={styles.emergencyButtonText}>🚨 Emergency</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[styles.emergencyButton, { backgroundColor: '#3b82f6' }]}>
          <Text style={styles.emergencyButtonText}>🏥 Medical</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[styles.emergencyButton, { backgroundColor: '#22c55e' }]}>
          <Text style={styles.emergencyButtonText}>👮 Security</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Emergency Exits</Text>
        <View style={styles.exitList}>
          <View style={styles.exitItem}>
            <Text style={styles.exitName}>North Exit</Text>
            <Text style={styles.exitDistance}>50m - Turn left</Text>
          </View>
          <View style={styles.exitItem}>
            <Text style={styles.exitName}>South Exit</Text>
            <Text style={styles.exitDistance}>80m - Turn right</Text>
          </View>
          <View style={styles.exitItem}>
            <Text style={styles.exitName}>East Exit</Text>
            <Text style={styles.exitDistance}>100m - Straight ahead</Text>
          </View>
        </View>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Active Alerts</Text>
        <Text style={styles.noDataText}>No active alerts in your area</Text>
      </View>
    </ScrollView>
  );
};

const ProfileScreen = () => {
  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>My Profile</Text>
        <Text style={styles.headerSubtitle}>SSOS Fan Pass</Text>
      </View>

      <View style={styles.profileCard}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>SS</Text>
        </View>
        <Text style={styles.userName}>SSOS Fan</Text>
        <Text style={styles.userEmail}>fan@ssos.stadium</Text>
        <View style={styles.ticketInfo}>
          <Text style={styles.ticketLabel}>Ticket: SECTION A, ROW 5, SEAT 12</Text>
        </View>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>My Stats</Text>
        <View style={styles.statsRow}>
          <View style={styles.statItem}>
            <Text style={styles.statValue}>12</Text>
            <Text style={styles.statLabel}>Events</Text>
          </View>
          <View style={styles.statItem}>
            <Text style={styles.statValue}>45</Text>
            <Text style={styles.statLabel}>Orders</Text>
          </View>
          <View style={styles.statItem}>
            <Text style={styles.statValue}>★</Text>
            <Text style={styles.statLabel}>Gold Member</Text>
          </View>
        </View>
      </View>
    </ScrollView>
  );
};

const HomeTabs = () => {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        tabBarIcon: ({ focused, color, size }) => {
          let icon = '🏟️';
          if (route.name === 'Map') icon = '🗺️';
          else if (route.name === 'Navigate') icon = '🧭';
          else if (route.name === 'Food') icon = '🍔';
          else if (route.name === 'Safety') icon = '🚨';
          else if (route.name === 'Profile') icon = '👤';
          return <Text style={{ fontSize: 20 }}>{icon}</Text>;
        },
        tabBarActiveTintColor: '#3b82f6',
        tabBarInactiveTintColor: 'gray',
        tabBarStyle: { paddingBottom: 5, height: 60 },
      })}
    >
      <Tab.Screen name="Map" component={StadiumMap} />
      <Tab.Screen name="Navigate" component={NavigationScreen} />
      <Tab.Screen name="Food" component={FoodScreen} />
      <Tab.Screen name="Safety" component={EmergencyScreen} />
      <Tab.Screen name="Profile" component={ProfileScreen} />
    </Tab.Navigator>
  );
};

export default function App() {
  return (
    <NavigationContainer>
      <HomeTabs />
    </NavigationContainer>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#111827' },
  header: { padding: 20, paddingTop: 50, backgroundColor: '#1f2937' },
  headerTitle: { fontSize: 24, fontWeight: 'bold', color: '#fff' },
  headerSubtitle: { fontSize: 14, color: '#9ca3af', marginTop: 4 },
  legendContainer: { flexDirection: 'row', justifyContent: 'space-around', padding: 15, backgroundColor: '#1f2937' },
  legendItem: { flexDirection: 'row', alignItems: 'center' },
  legendDot: { width: 12, height: 12, borderRadius: 6, marginRight: 6 },
  legendText: { fontSize: 12, color: '#9ca3af' },
  mapContainer: { alignItems: 'center', padding: 20 },
  statsContainer: { flexDirection: 'row', justifyContent: 'space-around', padding: 20 },
  statCard: { backgroundColor: '#1f2937', padding: 15, borderRadius: 10, alignItems: 'center', width: 100 },
  statValue: { fontSize: 20, fontWeight: 'bold', color: '#3b82f6' },
  statLabel: { fontSize: 12, color: '#9ca3af', marginTop: 4 },
  card: { backgroundColor: '#1f2937', margin: 15, padding: 20, borderRadius: 15 },
  cardTitle: { fontSize: 18, fontWeight: 'bold', color: '#fff', marginBottom: 15 },
  inputContainer: { marginBottom: 15 },
  inputLabel: { fontSize: 14, color: '#9ca3af', marginBottom: 8 },
  zoneSelector: { flexDirection: 'row', flexWrap: 'wrap' },
  zoneButton: { paddingHorizontal: 12, paddingVertical: 8, backgroundColor: '#374151', borderRadius: 20, margin: 4 },
  zoneButtonActive: { backgroundColor: '#3b82f6' },
  zoneButtonText: { fontSize: 12, color: '#9ca3af' },
  zoneButtonTextActive: { color: '#fff' },
  primaryButton: { backgroundColor: '#3b82f6', padding: 15, borderRadius: 10, alignItems: 'center', marginTop: 10 },
  primaryButtonText: { fontSize: 16, fontWeight: 'bold', color: '#fff' },
  routeInfo: { marginBottom: 15 },
  routeText: { fontSize: 14, color: '#9ca3af', marginBottom: 5 },
  routeSteps: { marginTop: 10 },
  routeStep: { flexDirection: 'row', alignItems: 'center', marginBottom: 10 },
  stepNumber: { width: 24, height: 24, borderRadius: 12, backgroundColor: '#3b82f6', justifyContent: 'center', alignItems: 'center', marginRight: 10 },
  stepNumberText: { fontSize: 12, color: '#fff', fontWeight: 'bold' },
  stepText: { fontSize: 14, color: '#fff' },
  vendorCard: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 15, backgroundColor: '#374151', borderRadius: 10, marginBottom: 10 },
  vendorInfo: { flex: 1 },
  vendorName: { fontSize: 16, fontWeight: 'bold', color: '#fff' },
  vendorItems: { fontSize: 12, color: '#9ca3af', marginTop: 4 },
  vendorWait: { alignItems: 'center' },
  waitTime: { fontSize: 20, fontWeight: 'bold', color: '#22c55e' },
  waitLabel: { fontSize: 10, color: '#9ca3af' },
  quickOrderGrid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between' },
  quickOrderButton: { width: '48%', backgroundColor: '#374151', padding: 20, borderRadius: 10, alignItems: 'center', marginBottom: 10 },
  quickOrderEmoji: { fontSize: 30, marginBottom: 8 },
  quickOrderText: { fontSize: 14, color: '#fff' },
  emergencyButtons: { padding: 15 },
  emergencyButton: { padding: 20, borderRadius: 10, alignItems: 'center', marginBottom: 10 },
  emergencyButtonText: { fontSize: 18, fontWeight: 'bold', color: '#fff' },
  exitList: { marginTop: 10 },
  exitItem: { flexDirection: 'row', justifyContent: 'space-between', padding: 15, backgroundColor: '#374151', borderRadius: 10, marginBottom: 10 },
  exitName: { fontSize: 16, fontWeight: 'bold', color: '#fff' },
  exitDistance: { fontSize: 14, color: '#9ca3af' },
  noDataText: { fontSize: 14, color: '#9ca3af', textAlign: 'center', padding: 20 },
  profileCard: { backgroundColor: '#1f2937', margin: 15, padding: 30, borderRadius: 15, alignItems: 'center' },
  avatar: { width: 80, height: 80, borderRadius: 40, backgroundColor: '#3b82f6', justifyContent: 'center', alignItems: 'center', marginBottom: 15 },
  avatarText: { fontSize: 30, fontWeight: 'bold', color: '#fff' },
  userName: { fontSize: 24, fontWeight: 'bold', color: '#fff' },
  userEmail: { fontSize: 14, color: '#9ca3af', marginTop: 4 },
  ticketInfo: { backgroundColor: '#374151', padding: 15, borderRadius: 10, marginTop: 15 },
  ticketLabel: { fontSize: 14, color: '#3b82f6' },
  statsRow: { flexDirection: 'row', justifyContent: 'space-around' },
  statItem: { alignItems: 'center' },
});