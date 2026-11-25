import React, { useState, useEffect } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  ActivityIndicator, Alert, Platform, RefreshControl,
} from 'react-native';
import { useAuth } from '@/context/AuthContext';
import { api } from '@/services/api';
import { useGoBack } from '@/hooks/useGoBack';

const showAlert = (title: string, msg: string) => {
  if (Platform.OS === 'web') window.alert(`${title}\n\n${msg}`);
  else Alert.alert(title, msg);
};

function StarRow({ score }: { score: number }) {
  return (
    <Text style={{ fontSize: 16 }}>
      {Array.from({ length: 5 }, (_, i) => (i < score ? '⭐' : '☆')).join('')}
    </Text>
  );
}

function timeAgo(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 2592000) return `${Math.floor(diff / 86400)}d ago`;
  return new Date(iso).toLocaleDateString();
}

export default function MyRatingsScreen() {
  const { user } = useAuth();
  const goBack = useGoBack();

  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    if (!user) return;
    try {
      const data = await api.ratings.getUserSummary(user.id);
      setSummary(data);
    } catch (err: any) {
      showAlert('Error', err.message || 'Failed to load ratings');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { load(); }, [user?.id]);

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#007bff" />
        <Text style={styles.loadingText}>Loading ratings…</Text>
      </View>
    );
  }

  const avg: number = summary?.average_rating ?? 0;
  const total: number = summary?.total_reviews ?? 0;
  const recent: any[] = summary?.recent_ratings ?? [];

  return (
    <ScrollView
      style={styles.container}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} />}
    >
      <View style={styles.header}>
        <TouchableOpacity onPress={goBack} style={styles.backBtn}>
          <Text style={styles.backText}>← Back</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>My Ratings</Text>
        <View style={{ width: 60 }} />
      </View>

      {/* Summary card */}
      <View style={styles.summaryCard}>
        <Text style={styles.avgScore}>{avg > 0 ? avg.toFixed(1) : '—'}</Text>
        <View style={styles.starsRow}>
          {avg > 0 && <StarRow score={Math.round(avg)} />}
        </View>
        <Text style={styles.totalText}>
          {total === 0 ? 'No reviews yet' : `${total} review${total === 1 ? '' : 's'}`}
        </Text>
      </View>

      {/* Recent reviews */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Recent Reviews</Text>
        {recent.length === 0 && (
          <Text style={styles.emptyText}>
            Complete tasks to start collecting reviews.
          </Text>
        )}
        {recent.map((r: any) => (
          <View key={r.id} style={styles.reviewRow}>
            <View style={styles.reviewHeader}>
              <StarRow score={r.score} />
              <Text style={styles.reviewMeta}>
                {r.rater_username} · {timeAgo(r.created_at)}
              </Text>
            </View>
            {!!r.comment && (
              <Text style={styles.reviewComment}>{r.comment}</Text>
            )}
            {!!r.task_title && (
              <Text style={styles.reviewTask}>📋 {r.task_title}</Text>
            )}
          </View>
        ))}
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
    justifyContent: 'space-between',
  },
  backBtn: { padding: 4 },
  backText: { color: '#007bff', fontSize: 16, fontWeight: '600' },
  headerTitle: { fontSize: 18, fontWeight: '700', color: '#1a1a2e' },
  summaryCard: {
    backgroundColor: '#fff',
    margin: 16,
    marginBottom: 8,
    borderRadius: 16,
    padding: 28,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOpacity: 0.07,
    shadowOffset: { width: 0, height: 2 },
    shadowRadius: 6,
    elevation: 3,
  },
  avgScore: { fontSize: 56, fontWeight: '800', color: '#1a1a2e' },
  starsRow: { marginVertical: 6 },
  totalText: { fontSize: 14, color: '#6b7280', marginTop: 4 },
  card: {
    backgroundColor: '#fff',
    margin: 16,
    marginBottom: 8,
    borderRadius: 14,
    padding: 16,
    shadowColor: '#000',
    shadowOpacity: 0.05,
    shadowOffset: { width: 0, height: 2 },
    shadowRadius: 4,
    elevation: 2,
  },
  cardTitle: { fontSize: 16, fontWeight: '700', color: '#1a1a2e', marginBottom: 14 },
  emptyText: { fontSize: 14, color: '#9ca3af', lineHeight: 22 },
  reviewRow: {
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: '#f3f4f6',
  },
  reviewHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 },
  reviewMeta: { fontSize: 12, color: '#9ca3af' },
  reviewComment: { fontSize: 14, color: '#374151', lineHeight: 20, marginBottom: 4 },
  reviewTask: { fontSize: 12, color: '#6b7280' },
});
