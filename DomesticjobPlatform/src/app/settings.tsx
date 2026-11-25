import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator,
  TextInput, Alert, Platform, RefreshControl,
} from 'react-native';import { useAuth } from '@/context/AuthContext';
import { api, GeoConsentInfo } from '@/services/api';
import { useGoBack } from '@/hooks/useGoBack';

const showAlert = (title: string, msg: string) => {
  if (Platform.OS === 'web') window.alert(`${title}\n\n${msg}`);
  else Alert.alert(title, msg);
};

export default function SettingsScreen() {
  const { user } = useAuth();
  const goBack = useGoBack();

  const [minRating, setMinRating] = useState('');
  const [searchRadius, setSearchRadius] = useState('');
  const [blockedStudents, setBlockedStudents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  // Location privacy notice + live policy values (retention etc.)
  const [privacyInfo, setPrivacyInfo] = useState<GeoConsentInfo | null>(null);
  const [retentionDays, setRetentionDays] = useState<number | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [consent, policy] = await Promise.all([
          api.geo.getConsent(),
          api.geo.getPolicy(),
        ]);
        setPrivacyInfo(consent);
        setRetentionDays(policy.retention_days);
      } catch {
        // Keep the generic policy text if the API is unreachable.
      }
    })();
  }, []);

  const fetchSettings = useCallback(async () => {
    try {
      const data = await api.household.getSettings();
      setMinRating(String(data.min_rating));
      setSearchRadius(String(data.search_radius_km));
      setBlockedStudents(data.blocked_students || []);
    } catch (err: any) {
      showAlert('Error', err.message || 'Failed to load settings');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { fetchSettings(); }, [fetchSettings]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const data: any = {};
      if (minRating) data.min_rating = parseFloat(minRating);
      if (searchRadius) data.search_radius_km = parseFloat(searchRadius);
      await api.household.updateSettings(data);
      showAlert('Saved', 'Your settings have been updated.');
    } catch (err: any) {
      showAlert('Error', err.message || 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  const handleUnblock = async (studentId: number, name: string) => {
    const ok = await new Promise<boolean>(resolve =>
      Platform.OS === 'web'
        ? resolve(window.confirm(`Unblock ${name}?\n\nThey will be able to receive your tasks again.`))
        : Alert.alert('Unblock Student', `Unblock ${name}?\n\nThey will be able to receive your tasks again.`, [
            { text: 'Cancel', style: 'cancel', onPress: () => resolve(false) },
            { text: 'Unblock', onPress: () => resolve(true) },
          ])
    );
    if (!ok) return;
    try {
      await api.household.unblockStudent(studentId);
      setBlockedStudents(prev => prev.filter(s => s.id !== studentId));
    } catch (err: any) {
      showAlert('Error', err.message || 'Failed to unblock');
    }
  };

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#007bff" />
        <Text style={styles.loadingText}>Loading settings…</Text>
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.container}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); fetchSettings(); }} />}
    >
      <View style={styles.header}>
        <TouchableOpacity onPress={goBack} style={styles.backBtn}>
          <Text style={styles.backText}>← Back</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Settings</Text>
        <View style={{ width: 50 }} />
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Matching Preferences</Text>

        <View style={styles.formGroup}>
          <Text style={styles.label}>Minimum Student Rating (0-5)</Text>
          <TextInput
            style={styles.input}
            placeholder="e.g. 3.5"
            keyboardType="numeric"
            value={minRating}
            onChangeText={setMinRating}
          />
          <Text style={styles.hint}>Only students with this rating or higher will receive your tasks.</Text>
        </View>

        <View style={styles.formGroup}>
          <Text style={styles.label}>Search Radius (km)</Text>
          <TextInput
            style={styles.input}
            placeholder="e.g. 5"
            keyboardType="numeric"
            value={searchRadius}
            onChangeText={setSearchRadius}
          />
          <Text style={styles.hint}>How far from your location to search for students. Round 2 widens this automatically.</Text>
        </View>

        <TouchableOpacity
          style={[styles.saveBtn, saving && styles.disabledBtn]}
          onPress={handleSave}
          disabled={saving}
        >
          {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.saveBtnText}>Save Settings</Text>}
        </TouchableOpacity>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Blocked Students ({blockedStudents.length})</Text>
        {blockedStudents.length === 0 ? (
          <Text style={styles.emptyText}>No blocked students. You can block a student when cancelling a match.</Text>
        ) : (
          blockedStudents.map(s => (
            <View key={s.id} style={styles.blockedRow}>
              <View>
                <Text style={styles.blockedName}>{s.first_name} {s.last_name}</Text>
                <Text style={styles.blockedUsername}>@{s.username}</Text>
              </View>
              <TouchableOpacity style={styles.unblockBtn} onPress={() => handleUnblock(s.id, `${s.first_name} ${s.last_name}`.trim() || s.username)}>
                <Text style={styles.unblockText}>Unblock</Text>
              </TouchableOpacity>
            </View>
          ))
        )}
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Privacy &amp; Location</Text>
        <Text style={styles.policyIntro}>
          How the platform handles location data:
        </Text>
        <View style={styles.bulletRow}>
          <Text style={styles.bulletDot}>•</Text>
          <Text style={styles.policyText}>
            Your location is captured{' '}
            <Text style={styles.policyBold}>only once, when you check in or finish a task</Text>{' '}
            — never continuously in the background.
          </Text>
        </View>
        <View style={styles.bulletRow}>
          <Text style={styles.bulletDot}>•</Text>
          <Text style={styles.policyText}>
            It is used to verify you were within the task's check-in radius at
            the scheduled start time.
          </Text>
        </View>
        <View style={styles.bulletRow}>
          <Text style={styles.bulletDot}>•</Text>
          <Text style={styles.policyText}>
            Households never see your coordinates — only{' '}
            <Text style={styles.policyItalic}>“Arrived at HH:MM, location verified.”</Text>{' '}
            Raw coordinates are visible only to platform administrators, and
            only for reviewing a dispute.
          </Text>
        </View>
        <View style={styles.bulletRow}>
          <Text style={styles.bulletDot}>•</Text>
          <Text style={styles.policyText}>
            Check-in coordinates are automatically anonymised after{' '}
            {retentionDays ?? 90} days (kept longer only while a dispute is open).
          </Text>
        </View>
        <View style={styles.bulletRow}>
          <Text style={styles.bulletDot}>•</Text>
          <Text style={styles.policyText}>
            Location is transmitted over an encrypted connection, and your
            consent is recorded with a timestamp and version before your first
            check-in.
          </Text>
        </View>

        {!!privacyInfo?.text && (
          <View style={styles.noticeBox}>
            <Text style={styles.noticeLabel}>
              Location-collection notice (v{privacyInfo.version})
            </Text>
            <Text style={styles.noticeText}>{privacyInfo.text}</Text>
          </View>
        )}

        {user?.role === 'STUDENT' && privacyInfo && (
          <Text style={privacyInfo.consented ? styles.consentedYes : styles.consentedNo}>
            {privacyInfo.consented
              ? '✓ You have accepted the location-collection notice.'
              : 'You will be asked to accept the location notice before your first check-in.'}
          </Text>
        )}
      </View>

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f7fa' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  loadingText: { marginTop: 10, color: '#666' },
  header: {
    backgroundColor: '#fff',
    paddingTop: 50,
    paddingHorizontal: 16,
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
    flexDirection: 'row',
    alignItems: 'center',
  },
  backBtn: { marginRight: 12 },
  backText: { color: '#007bff', fontSize: 16 },
  headerTitle: { flex: 1, fontSize: 18, fontWeight: '700', color: '#1a1a2e' },
  card: { backgroundColor: '#fff', margin: 16, marginBottom: 8, borderRadius: 14, padding: 16, shadowColor: '#000', shadowOpacity: 0.05, shadowOffset: { width: 0, height: 2 }, shadowRadius: 4, elevation: 2 },
  cardTitle: { fontSize: 18, fontWeight: '700', color: '#1a1a2e', marginBottom: 16 },
  formGroup: { marginBottom: 20 },
  label: { fontSize: 14, fontWeight: '600', color: '#333', marginBottom: 6 },
  input: { borderWidth: 1, borderColor: '#d0d0d0', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 10, fontSize: 15, backgroundColor: '#f9f9f9' },
  hint: { fontSize: 12, color: '#999', marginTop: 6 },
  saveBtn: { backgroundColor: '#007bff', padding: 16, borderRadius: 10, alignItems: 'center' },
  saveBtnText: { color: '#fff', fontSize: 16, fontWeight: '700' },
  disabledBtn: { opacity: 0.5 },
  emptyText: { fontSize: 14, color: '#888', lineHeight: 20 },
  blockedRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#f0f0f0' },
  blockedName: { fontSize: 15, fontWeight: '600', color: '#1a1a2e' },
  blockedUsername: { fontSize: 13, color: '#999' },
  unblockBtn: { backgroundColor: '#fee2e2', paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8 },
  unblockText: { color: '#c00', fontWeight: '600', fontSize: 13 },
  // Privacy & location policy styles
  policyIntro: { fontSize: 14, color: '#374151', marginBottom: 12 },
  bulletRow: { flexDirection: 'row', gap: 8, marginBottom: 10 },
  bulletDot: { fontSize: 14, color: '#007bff', lineHeight: 21 },
  policyText: { flex: 1, fontSize: 14, color: '#374151', lineHeight: 21 },
  policyBold: { fontWeight: '700' },
  policyItalic: { fontStyle: 'italic' },
  noticeBox: { backgroundColor: '#f8fafc', borderWidth: 1, borderColor: '#e2e8f0', borderRadius: 10, padding: 12, marginTop: 4 },
  noticeLabel: { fontSize: 12, fontWeight: '700', color: '#64748b', marginBottom: 6 },
  noticeText: { fontSize: 13, color: '#475569', lineHeight: 19 },
  consentedYes: { fontSize: 13, color: '#16a34a', fontWeight: '600', marginTop: 12 },
  consentedNo: { fontSize: 13, color: '#d97706', marginTop: 12 },
});
