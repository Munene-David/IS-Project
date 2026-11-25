import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, FlatList, TouchableOpacity, ActivityIndicator,
  StyleSheet, RefreshControl, Alert, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useAuth } from '@/context/AuthContext';
import { api } from '@/services/api';
import { useGoBack } from '@/hooks/useGoBack';

interface TaskRequest {
  id: number;
  task_id: number;
  task_title: string;
  task_category: string;
  task_posted_price: string;
  task_scheduled_date: string | null;
  task_scheduled_time: string | null;
  task_location_approximate: string;
  status: string;
  sent_at: string;
}

function categoryEmoji(cat: string): string {
  const map: Record<string, string> = {
    Cleaning: '🧹',
    Cooking: '🍳',
    Laundry: '👕',
    Childcare: '👶',
    Gardening: '🌱',
    Errands: '🏃',
  };
  return map[cat] || '📋';
}

export default function AvailableRequestsScreen() {
  const router = useRouter();
  const { user } = useAuth();
  const goBack = useGoBack();

  const [requests, setRequests] = useState<TaskRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [acceptingId, setAcceptingId] = useState<number | null>(null);
  const [decliningId, setDecliningId] = useState<number | null>(null);
  const [ignoringId, setIgnoringId] = useState<number | null>(null);

  const showAlert = (title: string, msg: string) => {
    if (Platform.OS === 'web') window.alert(`${title}\n\n${msg}`);
    else Alert.alert(title, msg);
  };

  const confirm = (title: string, msg: string): Promise<boolean> => {
    if (Platform.OS === 'web') return Promise.resolve(window.confirm(`${title}\n\n${msg}`));
    return new Promise(resolve =>
      Alert.alert(title, msg, [
        { text: 'Cancel', style: 'cancel', onPress: () => resolve(false) },
        { text: 'OK', onPress: () => resolve(true) },
      ])
    );
  };

  const fetchRequests = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const data = await api.tasks.myRequests();
      setRequests(data);
    } catch (err: any) {
      if (!silent) showAlert('Error', err.message || 'Failed to load requests');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchRequests();
    // Poll every 10 seconds for new requests
    const interval = setInterval(() => fetchRequests(true), 10000);
    return () => clearInterval(interval);
  }, [fetchRequests]);

  const handleAccept = async (req: TaskRequest) => {
    const ok = await confirm(
      'Accept Task',
      `Accept "${req.task_title}" for KES ${req.task_posted_price}? The household will be notified and has 10 minutes to confirm payment.`
    );
    if (!ok) return;
    setAcceptingId(req.id);
    try {
      await api.tasks.acceptRequest(req.id);
      showAlert('🎉 Accepted!', 'You got the job! The household will confirm payment shortly.');
      fetchRequests();
    } catch (err: any) {
      showAlert('Could not accept', err.message || 'This task may have already been taken.');
    } finally {
      setAcceptingId(null);
    }
  };

  const handleDecline = async (req: TaskRequest) => {
    const ok = await confirm('Decline', `Decline "${req.task_title}"?`);
    if (!ok) return;
    setDecliningId(req.id);
    try {
      await api.tasks.declineRequest(req.id);
      setRequests(prev => prev.filter(r => r.id !== req.id));
    } catch (err: any) {
      showAlert('Error', err.message || 'Failed to decline');
    } finally {
      setDecliningId(null);
    }
  };

  const handleIgnore = async (req: TaskRequest) => {
    setIgnoringId(req.id);
    try {
      await api.tasks.ignoreRequest(req.id);
      setRequests(prev => prev.filter(r => r.id !== req.id));
    } catch (err: any) {
      showAlert('Error', err.message || 'Failed to ignore');
    } finally {
      setIgnoringId(null);
    }
  };

  const renderItem = ({ item }: { item: TaskRequest }) => (
    <View style={styles.card}>
      <View style={styles.cardHeader}>
        <Text style={styles.emoji}>{categoryEmoji(item.task_category)}</Text>
        <View style={styles.cardHeaderText}>
          <Text style={styles.title} numberOfLines={2}>{item.task_title}</Text>
          <Text style={styles.category}>{item.task_category}</Text>
        </View>
        {item.status === 'VIEWED' && <View style={styles.viewedDot} />}
      </View>

      <View style={styles.row}>
        <Text style={styles.label}>💰 Price</Text>
        <Text style={styles.value}>KES {item.task_posted_price}</Text>
      </View>

      {item.task_scheduled_date && (
        <View style={styles.row}>
          <Text style={styles.label}>📅 When</Text>
          <Text style={styles.value}>
            {item.task_scheduled_date}
            {item.task_scheduled_time ? `  ${item.task_scheduled_time.slice(0, 5)}` : ''}
          </Text>
        </View>
      )}

      <View style={styles.row}>
        <Text style={styles.label}>📍 Area</Text>
        <Text style={styles.value}>{item.task_location_approximate || 'Location shared after payment'}</Text>
      </View>

      <View style={styles.actions}>
        <TouchableOpacity
          style={[styles.btn, styles.declineBtn, decliningId === item.id && styles.disabledBtn]}
          onPress={() => handleDecline(item)}
          disabled={decliningId === item.id || acceptingId === item.id || ignoringId === item.id}
        >
          {decliningId === item.id
            ? <ActivityIndicator color="#c00" size="small" />
            : <Text style={styles.declineBtnText}>Decline</Text>}
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.btn, styles.ignoreBtn, ignoringId === item.id && styles.disabledBtn]}
          onPress={() => handleIgnore(item)}
          disabled={ignoringId === item.id || acceptingId === item.id || decliningId === item.id}
        >
          {ignoringId === item.id
            ? <ActivityIndicator color="#666" size="small" />
            : <Text style={styles.ignoreBtnText}>Ignore</Text>}
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.btn, styles.acceptBtn, acceptingId === item.id && styles.disabledBtn]}
          onPress={() => handleAccept(item)}
          disabled={acceptingId === item.id || decliningId === item.id || ignoringId === item.id}
        >
          {acceptingId === item.id
            ? <ActivityIndicator color="#fff" size="small" />
            : <Text style={styles.acceptBtnText}>Accept</Text>}
        </TouchableOpacity>
      </View>
    </View>
  );

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#007bff" />
        <Text style={styles.loadingText}>Loading available tasks…</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={goBack} style={styles.backBtn}>
          <Text style={styles.backText}>← Back</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Available Tasks</Text>
        <Text style={styles.headerCount}>{requests.length} waiting</Text>
      </View>

      <FlatList
        data={requests}
        keyExtractor={item => item.id.toString()}
        renderItem={renderItem}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); fetchRequests(); }} />
        }
        ListEmptyComponent={
          <View style={styles.emptyBox}>
            <Text style={styles.emptyEmoji}>📭</Text>
            <Text style={styles.emptyTitle}>No tasks waiting for you right now</Text>
            <Text style={styles.emptyText}>
              Make sure your profile has categories and a location set so we can match you.
            </Text>
          </View>
        }
        contentContainerStyle={requests.length === 0 ? styles.emptyContainer : styles.list}
      />
    </View>
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
  headerCount: { fontSize: 13, color: '#888', backgroundColor: '#eef2ff', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 12 },
  list: { padding: 12 },
  emptyContainer: { flex: 1, justifyContent: 'center' },
  card: {
    backgroundColor: '#fff',
    borderRadius: 14,
    padding: 16,
    marginBottom: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.07,
    shadowRadius: 6,
    elevation: 2,
  },
  cardHeader: { flexDirection: 'row', alignItems: 'flex-start', marginBottom: 10 },
  emoji: { fontSize: 32, marginRight: 10 },
  cardHeaderText: { flex: 1 },
  title: { fontSize: 16, fontWeight: '700', color: '#1a1a2e' },
  category: { fontSize: 13, color: '#666', marginTop: 2 },
  viewedDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#3b82f6', marginTop: 4 },
  row: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 },
  label: { fontSize: 13, color: '#888' },
  value: { fontSize: 13, color: '#1a1a2e', fontWeight: '500', textAlign: 'right', flex: 1, marginLeft: 8 },
  actions: { flexDirection: 'row', gap: 10, marginTop: 12 },
  btn: { flex: 1, paddingVertical: 12, borderRadius: 10, alignItems: 'center' },
  declineBtn: { backgroundColor: '#fff0f0', borderWidth: 1, borderColor: '#fca5a5' },
  declineBtnText: { color: '#c00', fontWeight: '600' },
  ignoreBtn: { backgroundColor: '#f0f0f0', borderWidth: 1, borderColor: '#d9d9d9' },
  ignoreBtnText: { color: '#666', fontWeight: '600' },
  acceptBtn: { backgroundColor: '#16a34a' },
  acceptBtnText: { color: '#fff', fontWeight: '700', fontSize: 15 },
  disabledBtn: { opacity: 0.5 },
  emptyBox: { alignItems: 'center', padding: 40 },
  emptyEmoji: { fontSize: 50, marginBottom: 12 },
  emptyTitle: { fontSize: 17, fontWeight: '700', color: '#1a1a2e', textAlign: 'center', marginBottom: 8 },
  emptyText: { fontSize: 14, color: '#666', textAlign: 'center', lineHeight: 20 },
});
