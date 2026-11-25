import React, { useState, useEffect } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  ActivityIndicator, Alert, Platform, RefreshControl,
} from 'react-native';
import { useAuth } from '@/context/AuthContext';
import { api } from '@/services/api';
import { useGoBack } from '@/hooks/useGoBack';
import { useRouter } from 'expo-router';

const showAlert = (title: string, msg: string) => {
  if (Platform.OS === 'web') window.alert(`${title}\n\n${msg}`);
  else Alert.alert(title, msg);
};

function timeAgo(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 2592000) return `${Math.floor(diff / 86400)}d ago`;
  return new Date(iso).toLocaleDateString();
}

const TYPE_LABELS: Record<string, { label: string; color: string; icon: string }> = {
  DEPOSIT:        { label: 'Deposit',        color: '#16a34a', icon: '↓' },
  HOLD:           { label: 'Escrow Hold',    color: '#7c3aed', icon: '🔒' },
  RELEASE:        { label: 'Released',       color: '#16a34a', icon: '↑' },
  REFUND:         { label: 'Full Refund',    color: '#d97706', icon: '↩' },
  PARTIAL_REFUND: { label: 'Partial Refund', color: '#d97706', icon: '↩' },
  PENALTY:        { label: 'Penalty',        color: '#dc2626', icon: '⚠' },
};

const STATUS_COLOR: Record<string, string> = {
  COMPLETED:  '#16a34a',
  SIMULATED:  '#6b7280',
  PENDING:    '#d97706',
  FAILED:     '#dc2626',
};

export default function PaymentHistoryScreen() {
  const { user } = useAuth();
  const goBack = useGoBack();
  const router = useRouter();

  // We load the user's tasks then fetch ledger entries for each
  const [tasks, setTasks] = useState<any[]>([]);
  const [ledgers, setLedgers] = useState<Record<number, any[]>>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);

  const load = async () => {
    try {
      const taskList = await api.tasks.list({ my_tasks: true });
      // Only tasks that have had a payment event (escrow or completed)
      const paymentTasks = taskList.filter((t: any) =>
        ['Assigned', 'InProgress', 'AwaitingConfirmation', 'Completed',
         'Cancelled', 'Disputed', 'NoShow'].includes(t.status)
      );
      setTasks(paymentTasks);
    } catch (err: any) {
      showAlert('Error', err.message || 'Failed to load tasks');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const loadLedger = async (taskId: number) => {
    if (ledgers[taskId]) return; // already loaded
    try {
      const entries = await api.tasks.ledger(taskId);
      setLedgers(prev => ({ ...prev, [taskId]: entries }));
    } catch {
      setLedgers(prev => ({ ...prev, [taskId]: [] }));
    }
  };

  const toggleTask = (taskId: number) => {
    if (expanded === taskId) {
      setExpanded(null);
    } else {
      setExpanded(taskId);
      loadLedger(taskId);
    }
  };

  useEffect(() => { load(); }, [user?.id]);

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#007bff" />
        <Text style={styles.loadingText}>Loading payment history…</Text>
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.container}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} />}
    >
      <View style={styles.header}>
        <TouchableOpacity onPress={goBack} style={styles.backBtn}>
          <Text style={styles.backText}>← Back</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Payment History</Text>
        <View style={{ width: 60 }} />
      </View>

      {tasks.length === 0 && (
        <View style={styles.emptyCard}>
          <Text style={styles.emptyIcon}>💰</Text>
          <Text style={styles.emptyTitle}>No payment history yet</Text>
          <Text style={styles.emptyText}>
            {user?.role === 'HOUSEHOLD'
              ? 'Payments will appear here once you fund a task.'
              : 'Your earnings will appear here once you complete tasks.'}
          </Text>
        </View>
      )}

      {tasks.map((task: any) => {
        const isOpen = expanded === task.id;
        const entries: any[] = ledgers[task.id] ?? [];

        return (
          <View key={task.id} style={styles.taskCard}>
            {/* Task row — tap to expand */}
            <TouchableOpacity
              style={styles.taskRow}
              onPress={() => toggleTask(task.id)}
              activeOpacity={0.7}
            >
              <View style={styles.taskLeft}>
                <Text style={styles.taskTitle} numberOfLines={1}>{task.title}</Text>
                <Text style={styles.taskMeta}>
                  {task.category} · KES {task.posted_price}
                </Text>
              </View>
              <View style={styles.taskRight}>
                <View style={[styles.statusDot, {
                  backgroundColor: task.status === 'Completed' ? '#16a34a'
                    : task.status === 'Cancelled' ? '#dc2626'
                    : '#d97706',
                }]} />
                <Text style={styles.expandArrow}>{isOpen ? '▲' : '▼'}</Text>
              </View>
            </TouchableOpacity>

            {/* Ledger entries */}
            {isOpen && (
              <View style={styles.ledger}>
                {entries.length === 0 && (
                  <ActivityIndicator size="small" color="#007bff" style={{ marginVertical: 10 }} />
                )}
                {entries.map((entry: any) => {
                  const meta = TYPE_LABELS[entry.transaction_type] ?? {
                    label: entry.transaction_type, color: '#6b7280', icon: '•',
                  };
                  return (
                    <View key={entry.id} style={styles.entryRow}>
                      <View style={[styles.entryIcon, { backgroundColor: meta.color + '20' }]}>
                        <Text style={[styles.entryIconText, { color: meta.color }]}>{meta.icon}</Text>
                      </View>
                      <View style={styles.entryBody}>
                        <Text style={styles.entryType}>{meta.label}</Text>
                        {!!entry.notes && (
                          <Text style={styles.entryNotes} numberOfLines={2}>{entry.notes}</Text>
                        )}
                        <Text style={styles.entryTime}>{timeAgo(entry.created_at)}</Text>
                      </View>
                      <View style={styles.entryAmountCol}>
                        <Text style={[styles.entryAmount, { color: meta.color }]}>
                          KES {Number(entry.amount).toLocaleString()}
                        </Text>
                        <Text style={[styles.entryStatus, { color: STATUS_COLOR[entry.status] ?? '#6b7280' }]}>
                          {entry.status}
                        </Text>
                      </View>
                    </View>
                  );
                })}
                <TouchableOpacity
                  style={styles.viewTaskBtn}
                  onPress={() => router.push(`/tasks/${task.id}` as any)}
                >
                  <Text style={styles.viewTaskText}>View Task →</Text>
                </TouchableOpacity>
              </View>
            )}
          </View>
        );
      })}

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
    justifyContent: 'space-between',
  },
  backBtn: { padding: 4 },
  backText: { color: '#007bff', fontSize: 16, fontWeight: '600' },
  headerTitle: { fontSize: 18, fontWeight: '700', color: '#1a1a2e' },
  emptyCard: {
    margin: 24,
    padding: 32,
    backgroundColor: '#fff',
    borderRadius: 16,
    alignItems: 'center',
  },
  emptyIcon: { fontSize: 48, marginBottom: 12 },
  emptyTitle: { fontSize: 18, fontWeight: '700', color: '#1a1a2e', marginBottom: 8 },
  emptyText: { fontSize: 14, color: '#6b7280', textAlign: 'center', lineHeight: 22 },
  taskCard: {
    backgroundColor: '#fff',
    marginHorizontal: 16,
    marginBottom: 10,
    borderRadius: 14,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOpacity: 0.05,
    shadowOffset: { width: 0, height: 2 },
    shadowRadius: 4,
    elevation: 2,
  },
  taskRow: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    justifyContent: 'space-between',
  },
  taskLeft: { flex: 1, marginRight: 12 },
  taskTitle: { fontSize: 15, fontWeight: '600', color: '#1a1a2e', marginBottom: 2 },
  taskMeta: { fontSize: 13, color: '#6b7280' },
  taskRight: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  statusDot: { width: 8, height: 8, borderRadius: 4 },
  expandArrow: { fontSize: 12, color: '#9ca3af' },
  ledger: {
    borderTopWidth: 1,
    borderTopColor: '#f3f4f6',
    padding: 12,
  },
  entryRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#f9fafb',
    gap: 10,
  },
  entryIcon: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  entryIconText: { fontSize: 16, fontWeight: '700' },
  entryBody: { flex: 1 },
  entryType: { fontSize: 14, fontWeight: '600', color: '#1a1a2e' },
  entryNotes: { fontSize: 12, color: '#6b7280', marginTop: 2, lineHeight: 17 },
  entryTime: { fontSize: 11, color: '#9ca3af', marginTop: 3 },
  entryAmountCol: { alignItems: 'flex-end' },
  entryAmount: { fontSize: 14, fontWeight: '700' },
  entryStatus: { fontSize: 11, marginTop: 2, textTransform: 'uppercase' },
  viewTaskBtn: { paddingVertical: 10, alignItems: 'flex-end' },
  viewTaskText: { color: '#007bff', fontSize: 13, fontWeight: '600' },
});
