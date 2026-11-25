/**
 * ADMIN: location audit / dispute map view.
 *
 * Everything needed to adjudicate a location dispute on one screen:
 * the task pin + geofence, every check-in attempt (point, distance,
 * accuracy, timestamps, anti-spoofing flags), the household's complaint
 * and the full chat history.
 */
import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  Platform,
} from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import { api, LocationAuditData } from '@/services/api';
import { useGoBack } from '@/hooks/useGoBack';
import MapPicker from '@/components/map-picker';
import { ExtraMarker } from '@/components/map-picker.shared';

const showAlert = (title: string, message: string) => {
  if (Platform.OS === 'web') {
    window.alert(`${title}\n\n${message}`);
  } else {
    Alert.alert(title, message);
  }
};

function markerColor(result: string): string {
  if (result === 'VERIFIED') return '#16a34a';
  if (result === 'WRONG_CODE') return '#dc2626';
  return '#f59e0b'; // flagged: out of range / low accuracy / denied / mock
}

function fmtClock(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  const ss = String(d.getSeconds()).padStart(2, '0');
  return `${hh}:${mm}:${ss}`;
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString();
}

export default function LocationAuditScreen() {
  const { id } = useLocalSearchParams();
  const goBack = useGoBack();
  const [data, setData] = useState<LocationAuditData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const audit = await api.tasks.locationAudit(Number(id));
        setData(audit);
      } catch (error: any) {
        showAlert('Error', error.message || 'Failed to load the location audit.');
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#0ea5e9" />
        <Text style={styles.loadingText}>Loading location audit…</Text>
      </View>
    );
  }

  if (!data) {
    return (
      <View style={styles.center}>
        <Text style={styles.errorText}>Audit unavailable</Text>
        <TouchableOpacity onPress={goBack} style={styles.backLink}>
          <Text style={styles.backText}>← Back to task</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const { task } = data;
  const pin =
    task.location_lat && task.location_lng
      ? (() => {
          const lat = parseFloat(task.location_lat);
          const lng = parseFloat(task.location_lng);
          return Number.isNaN(lat) || Number.isNaN(lng) ? null : { lat, lng };
        })()
      : null;

  const markers: ExtraMarker[] = data.checkins
    .filter((c) => c.lat && c.lng)
    .map((c) => ({
      lat: parseFloat(c.lat as string),
      lng: parseFloat(c.lng as string),
      label: `${c.type} · ${c.result.replace(/_/g, ' ').toLowerCase()}` +
        (c.distance_m != null ? ` · ${Math.round(c.distance_m)} m from pin` : '') +
        ` · ${fmtClock(c.server_time)}`,
      color: markerColor(c.result),
    }));

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={goBack} style={styles.backLink}>
          <Text style={styles.backText}>← Back to task</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Location Audit</Text>
        <View style={{ width: 90 }} />
      </View>

      {/* Task summary */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>{task.title}</Text>
        <Text style={styles.metaRow}>{`Status: ${task.status}`}</Text>
        <Text style={styles.metaRow}>{`Household: ${task.household_owner}`}</Text>
        <Text style={styles.metaRow}>{`Student: ${task.assigned_student ?? '—'}`}</Text>
        <Text style={styles.metaRow}>{`Address: ${task.location_address}`}</Text>
        {!!task.location_landmark && (
          <Text style={styles.metaRow}>{`Landmark: ${task.location_landmark}`}</Text>
        )}
        {!!task.scheduled_date && (
          <Text style={styles.metaRow}>
            {`Scheduled: ${task.scheduled_date}${task.scheduled_time ? ` ${task.scheduled_time.slice(0, 5)}` : ''}`}
          </Text>
        )}
        <Text style={styles.metaRow}>{`Geofence radius: ${task.geofence_radius_m} m`}</Text>
      </View>

      {/* Map: pin + geofence + every check-in point */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>🗺️ Map</Text>
        {pin ? (
          <View style={styles.mapFrame}>
            <MapPicker
              pin={pin}
              geofenceRadiusM={task.geofence_radius_m}
              markers={markers}
              readOnly
              height={300}
            />
          </View>
        ) : (
          <Text style={styles.emptyText}>Task has no map pin.</Text>
        )}
        <Text style={styles.legend}>
          🟢 verified · 🟠 flagged (out of range / low accuracy / denied) · 🔴 wrong code
        </Text>
      </View>

      {/* Check-in attempts */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>{`📍 Check-Ins (${data.checkins.length})`}</Text>
        {data.checkins.length === 0 && (
          <Text style={styles.emptyText}>No check-in attempts recorded.</Text>
        )}
        {data.checkins.map((c) => (
          <View key={c.id} style={styles.checkinRow}>
            <View style={styles.checkinHeader}>
              <View style={[styles.typeBadge, { backgroundColor: markerColor(c.result) }]}>
                <Text style={styles.typeBadgeText}>{c.type}</Text>
              </View>
              <Text style={[styles.resultText, { color: markerColor(c.result) }]}>
                {c.result.replace(/_/g, ' ')}
              </Text>
              <Text style={styles.whoText}>{c.student_username}</Text>
            </View>
            <Text style={styles.detailText}>
              {c.distance_m != null
                ? `Distance from pin: ${Math.round(c.distance_m)} m`
                : 'No location submitted'}
              {c.accuracy_m != null ? ` · GPS accuracy: ±${Math.round(c.accuracy_m)} m` : ''}
            </Text>
            <Text style={styles.detailText}>
              {`Device time: ${fmtClock(c.device_time)}${c.time_skew_seconds != null ? ` (skew ${c.time_skew_seconds}s)` : ''}`}
            </Text>
            <Text style={styles.detailText}>{`Server time: ${fmtClock(c.server_time)} · ${fmtDate(c.server_time)}`}</Text>
            {(c.mock_location_flag || c.late_sync_flag || c.impossible_jump_flag || c.anonymised_at) && (
              <View style={styles.flagRow}>
                {c.mock_location_flag && <Text style={styles.flagChip}>MOCK LOCATION</Text>}
                {c.late_sync_flag && <Text style={styles.flagChip}>LATE SYNC</Text>}
                {c.impossible_jump_flag && <Text style={styles.flagChip}>IMPOSSIBLE JUMP</Text>}
                {c.anonymised_at && <Text style={[styles.flagChip, { backgroundColor: '#e5e7eb', color: '#6b7280' }]}>ANONYMISED</Text>}
              </View>
            )}
          </View>
        ))}
      </View>

      {/* Dispute */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>⚖️ Household Complaint</Text>
        {!data.dispute && <Text style={styles.emptyText}>No dispute raised for this task.</Text>}
        {!!data.dispute && (
          <>
            <Text style={styles.detailText}>{`Reason: ${String(data.dispute.reason).replace(/_/g, ' ')}`}</Text>
            <Text style={styles.detailText}>{`Raised by: ${data.dispute.raised_by_username} · ${fmtDate(data.dispute.created_at)}`}</Text>
            <Text style={styles.quoteText}>{data.dispute.description}</Text>
            {!!data.dispute.student_response && (
              <>
                <Text style={styles.detailText}>{`Student response (${data.dispute.student_responded_at ? fmtDate(data.dispute.student_responded_at) : '—'}):`}</Text>
                <Text style={styles.quoteText}>{data.dispute.student_response}</Text>
              </>
            )}
            <Text style={styles.detailText}>
              {data.dispute.resolved_at
                ? `Resolved (${data.dispute.outcome}) by ${data.dispute.resolved_by_username}`
                : 'Unresolved — coordinates are retained until this dispute closes.'}
            </Text>
          </>
        )}
      </View>

      {/* Chat history */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>{`💬 Chat History (${data.messages.length})`}</Text>
        {data.messages.length === 0 && <Text style={styles.emptyText}>No messages.</Text>}
        {data.messages.map((m) => (
          <View key={m.id} style={styles.messageRow}>
            <Text style={styles.messageMeta}>
              {`${m.sender_username} → ${m.receiver_username} · ${fmtClock(m.timestamp)}`}
            </Text>
            <Text style={styles.messageText}>{m.content}</Text>
          </View>
        ))}
      </View>

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f5f5' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#f5f5f5' },
  loadingText: { marginTop: 10, color: '#666', fontSize: 14 },
  errorText: { color: '#f44336', fontSize: 16 },
  header: {
    backgroundColor: '#fff', padding: 16, paddingTop: 60,
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    borderBottomWidth: 1, borderBottomColor: '#e0e0e0',
  },
  backLink: { padding: 4 },
  backText: { fontSize: 15, color: '#0ea5e9', fontWeight: '600' },
  headerTitle: { fontSize: 18, fontWeight: 'bold', color: '#1a1a1a' },
  card: {
    backgroundColor: '#fff', margin: 16, marginTop: 8, marginBottom: 8, borderRadius: 12,
    padding: 16, shadowColor: '#000', shadowOpacity: 0.1, shadowOffset: { width: 0, height: 2 },
    shadowRadius: 4, elevation: 3,
  },
  cardTitle: { fontSize: 18, fontWeight: 'bold', color: '#1a1a1a', marginBottom: 12 },
  metaRow: { fontSize: 14, color: '#374151', marginBottom: 4 },
  mapFrame: { borderRadius: 10, overflow: 'hidden', borderWidth: 1, borderColor: '#e0e0e0' },
  legend: { fontSize: 12, color: '#6b7280', marginTop: 8, fontStyle: 'italic' },
  emptyText: { fontSize: 14, color: '#999', fontStyle: 'italic' },
  checkinRow: { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 8, padding: 12, marginBottom: 10 },
  checkinHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 },
  typeBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 },
  typeBadgeText: { color: '#fff', fontSize: 11, fontWeight: '700' },
  resultText: { fontSize: 13, fontWeight: '700', flex: 1 },
  whoText: { fontSize: 12, color: '#6b7280' },
  detailText: { fontSize: 13, color: '#374151', marginBottom: 2 },
  quoteText: { fontSize: 14, color: '#374151', fontStyle: 'italic', backgroundColor: '#f9fafb', borderRadius: 6, padding: 10, marginTop: 4, marginBottom: 6 },
  flagRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 6 },
  flagChip: {
    backgroundColor: '#fee2e2', color: '#b91c1c', fontSize: 10, fontWeight: '700',
    paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, overflow: 'hidden',
  },
  messageRow: { marginBottom: 10, borderBottomWidth: 1, borderBottomColor: '#f3f4f6', paddingBottom: 8 },
  messageMeta: { fontSize: 11, color: '#6b7280', marginBottom: 2 },
  messageText: { fontSize: 14, color: '#374151' },
});
