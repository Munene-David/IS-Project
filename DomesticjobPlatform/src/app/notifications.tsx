import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, StyleSheet, FlatList,
  TouchableOpacity, ActivityIndicator, RefreshControl,
  Alert, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useAuth } from '@/context/AuthContext';
import { api } from '@/services/api';
import { useGoBack } from '@/hooks/useGoBack';

interface Notification {
  id: number;
  type: string;
  title: string;
  message: string;
  is_read: boolean;
  task_id: number | null;
  request_id: number | null;
  request_status: string | null;
  created_at: string;
}

const TYPE_ICON: Record<string, string> = {
  bid_accepted: '🎉',
  bid_submitted: '💼',
  payment_received: '💰',
  task_completed: '✅',
  escrow_deposited: '🔒',
  // Broadcast-flow
  task_request: '📢',
  task_matched: '🤝',
  request_taken: '⏱️',
  grace_window: '⏳',
  payment_failed: '❌',
  student_flagged: '🚩',
  start_code: '🔐',
  awaiting_confirmation: '👀',
  confirmation_reminder: '🔔',
  auto_released: '💸',
  cancellation: '🚫',
  refund: '↩️',
  no_show: '🚷',
  dispute_raised: '⚖️',
  dispute_response: '📝',
  dispute_resolved: '✅',
  task_deleted: '🗑️',
  general: '📢',
};

export default function NotificationsScreen() {
  const router = useRouter();
  const goBack = useGoBack();
  const { user } = useAuth();

  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [actingId, setActingId] = useState<number | null>(null);

  const showAlert = (title: string, msg: string) => {
    if (Platform.OS === 'web') window.alert(`${title}\n\n${msg}`);
    else Alert.alert(title, msg);
  };

  const confirmDialog = (title: string, msg: string): Promise<boolean> => {
    if (Platform.OS === 'web') return Promise.resolve(window.confirm(`${title}\n\n${msg}`));
    return new Promise(resolve =>
      Alert.alert(title, msg, [
        { text: 'Cancel', style: 'cancel', onPress: () => resolve(false) },
        { text: 'OK', onPress: () => resolve(true) },
      ])
    );
  };

  const fetchNotifications = useCallback(async () => {
    try {
      const data = await api.notifications.list();
      setNotifications(data.notifications);
      setUnreadCount(data.unread_count);
    } catch (e) {
      console.error('Failed to load notifications', e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { fetchNotifications(); }, [fetchNotifications]);

  const handleMarkAllRead = async () => {
    await api.notifications.markAllRead();
    setUnreadCount(0);
    setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
  };

  const removeNotification = (id: number) => {
    setNotifications(prev => prev.filter(n => n.id !== id));
  };

  const handleTap = (n: Notification) => {
    if (!n.is_read) {
      setNotifications(prev => prev.map(x => x.id === n.id ? { ...x, is_read: true } : x));
      setUnreadCount(prev => Math.max(0, prev - 1));
    }
    if (n.task_id) {
      router.push(`/tasks/${n.task_id}` as any);
    }
  };

  // --- Task invitation actions (accept / ignore / decline) ---

  const isActionable = (n: Notification) =>
    n.type === 'task_request' &&
    !!n.request_id &&
    (n.request_status === 'SENT' || n.request_status === 'VIEWED');

  const handleAccept = async (n: Notification) => {
    const ok = await confirmDialog(
      'Accept Task',
      'Accept this task? The household will be notified and has 10 minutes to confirm payment.'
    );
    if (!ok) return;
    setActingId(n.id);
    try {
      await api.tasks.acceptRequest(n.request_id!);
      removeNotification(n.id);
      showAlert('🎉 Accepted!', 'You got the job! The household will confirm payment shortly.');
    } catch (err: any) {
      showAlert('Could not accept', err.message || 'This task may have already been taken.');
      fetchNotifications();
    } finally {
      setActingId(null);
    }
  };

  const handleIgnore = async (n: Notification) => {
    setActingId(n.id);
    try {
      await api.tasks.ignoreRequest(n.request_id!);
      removeNotification(n.id);
    } catch (err: any) {
      showAlert('Error', err.message || 'Failed to ignore');
      fetchNotifications();
    } finally {
      setActingId(null);
    }
  };

  const handleDecline = async (n: Notification) => {
    const ok = await confirmDialog('Decline Task', 'Decline this task? You will not be asked again.');
    if (!ok) return;
    setActingId(n.id);
    try {
      await api.tasks.declineRequest(n.request_id!);
      removeNotification(n.id);
    } catch (err: any) {
      showAlert('Error', err.message || 'Failed to decline');
      fetchNotifications();
    } finally {
      setActingId(null);
    }
  };

  const renderItem = ({ item }: { item: Notification }) => (
    <TouchableOpacity
      style={[styles.item, !item.is_read && styles.itemUnread]}
      onPress={() => handleTap(item)}
      activeOpacity={0.8}
    >
      <Text style={styles.icon}>{TYPE_ICON[item.type] || '📢'}</Text>
      <View style={styles.itemBody}>
        <View style={styles.itemHeader}>
          <Text style={styles.itemTitle}>{item.title}</Text>
          {!item.is_read && <View style={styles.dot} />}
        </View>
        <Text style={styles.itemMessage}>{item.message}</Text>
        <Text style={styles.itemTime}>
          {new Date(item.created_at).toLocaleString()}
        </Text>

        {/* Accept / Ignore / Decline for open task invitations */}
        {isActionable(item) && (
          <View style={styles.actions}>
            <TouchableOpacity
              style={[styles.actionBtn, styles.declineBtn]}
              onPress={() => handleDecline(item)}
              disabled={actingId === item.id}
            >
              <Text style={styles.declineText}>Decline</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.actionBtn, styles.ignoreBtn]}
              onPress={() => handleIgnore(item)}
              disabled={actingId === item.id}
            >
              <Text style={styles.ignoreText}>Ignore</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.actionBtn, styles.acceptBtn]}
              onPress={() => handleAccept(item)}
              disabled={actingId === item.id}
            >
              {actingId === item.id ? (
                <ActivityIndicator color="#fff" size="small" />
              ) : (
                <Text style={styles.acceptText}>Accept</Text>
              )}
            </TouchableOpacity>
          </View>
        )}
      </View>
    </TouchableOpacity>
  );

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={goBack} style={styles.backBtn}>
          <Text style={styles.backText}>← Back</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>
          {unreadCount > 0 ? `Notifications (${unreadCount})` : 'Notifications'}
        </Text>
        {unreadCount > 0 ? (
          <TouchableOpacity onPress={handleMarkAllRead} style={styles.markBtn}>
            <Text style={styles.markText}>Mark all read</Text>
          </TouchableOpacity>
        ) : (
          <View style={{ width: 80 }} />
        )}
      </View>

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color="#007bff" />
        </View>
      ) : (
        <FlatList
          data={notifications}
          renderItem={renderItem}
          keyExtractor={item => item.id.toString()}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); fetchNotifications(); }} />}
          contentContainerStyle={styles.list}
          ListEmptyComponent={
            <View style={styles.center}>
              <Text style={styles.emptyIcon}>🔔</Text>
              <Text style={styles.emptyText}>No notifications yet</Text>
            </View>
          }
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f5f5' },
  header: {
    backgroundColor: '#fff',
    paddingTop: 60,
    paddingBottom: 14,
    paddingHorizontal: 16,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
  },
  backBtn: { width: 60 },
  backText: { fontSize: 15, color: '#007bff', fontWeight: '600' },
  headerTitle: { fontSize: 18, fontWeight: 'bold', color: '#1a1a1a' },
  markBtn: { width: 80, alignItems: 'flex-end' },
  markText: { fontSize: 12, color: '#007bff' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingTop: 60 },
  emptyIcon: { fontSize: 48, marginBottom: 12 },
  emptyText: { fontSize: 16, color: '#999' },
  list: { padding: 12 },
  item: {
    flexDirection: 'row',
    backgroundColor: '#fff',
    borderRadius: 10,
    padding: 14,
    marginBottom: 10,
    elevation: 1,
    shadowColor: '#000',
    shadowOpacity: 0.05,
    shadowOffset: { width: 0, height: 1 },
    shadowRadius: 3,
  },
  itemUnread: { borderLeftWidth: 4, borderLeftColor: '#007bff', backgroundColor: '#f0f7ff' },
  icon: { fontSize: 28, marginRight: 12, marginTop: 2 },
  itemBody: { flex: 1 },
  itemHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  itemTitle: { fontSize: 15, fontWeight: '700', color: '#1a1a1a', flex: 1 },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#007bff', marginLeft: 8 },
  itemMessage: { fontSize: 13, color: '#555', lineHeight: 19, marginBottom: 6 },
  itemTime: { fontSize: 11, color: '#aaa' },
  actions: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 10,
    borderTopWidth: 1,
    borderTopColor: '#f0f0f0',
    paddingTop: 10,
  },
  actionBtn: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  declineBtn: { backgroundColor: '#fff0f0', borderWidth: 1, borderColor: '#fca5a5' },
  declineText: { color: '#c00', fontWeight: '600', fontSize: 13 },
  ignoreBtn: { backgroundColor: '#f0f0f0', borderWidth: 1, borderColor: '#d9d9d9' },
  ignoreText: { color: '#666', fontWeight: '600', fontSize: 13 },
  acceptBtn: { backgroundColor: '#16a34a' },
  acceptText: { color: '#fff', fontWeight: '700', fontSize: 13 },
});
