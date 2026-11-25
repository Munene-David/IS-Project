import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
  Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useAuth } from '@/context/AuthContext';
import { api } from '@/services/api';
import { useGoBack } from '@/hooks/useGoBack';

interface Task {
  id: number;
  title: string;
  category: string;
  posted_price: string;
  status: string;
  household_owner_name: string;
  myBid?: {
    id: number;
    amount: string;
    status: string;
    created_at: string;
  };
}

export default function MyBidsScreen() {
  const router = useRouter();
  const { user } = useAuth();
  const goBack = useGoBack();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchMyBids = async () => {
    try {
      // Fetch all tasks
      const allTasks = await api.tasks.list();
      
      // Filter to only tasks where I have a bid
      const tasksWithMyBids = allTasks
        .map((task: any) => {
          const myBid = task.bids?.find((bid: any) => bid.student_username === user?.username);
          if (myBid) {
            return {
              ...task,
              myBid: {
                id: myBid.id,
                amount: myBid.amount,
                status: myBid.status,
                created_at: myBid.created_at,
              },
            };
          }
          return null;
        })
        .filter((task: any) => task !== null);

      setTasks(tasksWithMyBids);
    } catch (error: any) {
      console.error('Error fetching bids:', error);
      Alert.alert('Error', 'Failed to load your bids');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    if (user?.role !== 'STUDENT') {
      Alert.alert('Access Denied', 'Only students can view bids.');
      goBack();
      return;
    }
    fetchMyBids();
  }, [user]);

  const onRefresh = () => {
    setRefreshing(true);
    fetchMyBids();
  };

  const getBidStatusColor = (status: string) => {
    switch (status) {
      case 'Accepted': return '#28a745';
      case 'Pending': return '#FF9800';
      case 'Rejected': return '#F44336';
      case 'Withdrawn': return '#757575';
      default: return '#666';
    }
  };

  const getTaskStatusColor = (status: string) => {
    switch (status) {
      case 'Posted': return '#2196F3';
      case 'Bidding': return '#FF9800';
      case 'Assigned': return '#9C27B0';
      case 'InProgress': return '#FFC107';
      case 'Completed': return '#4CAF50';
      case 'Cancelled': return '#F44336';
      default: return '#757575';
    }
  };

  const renderBid = ({ item }: { item: Task }) => (
    <TouchableOpacity
      style={styles.bidCard}
      onPress={() => router.push(`/tasks/${item.id}` as any)}
    >
      <View style={styles.bidHeader}>
        <View style={{ flex: 1 }}>
          <Text style={styles.taskTitle}>{item.title}</Text>
          <Text style={styles.taskCategory}>📂 {item.category}</Text>
          <Text style={styles.household}>👤 {item.household_owner_name}</Text>
        </View>
        <View style={[styles.taskStatusBadge, { backgroundColor: getTaskStatusColor(item.status) }]}>
          <Text style={styles.statusText}>{item.status}</Text>
        </View>
      </View>

      <View style={styles.priceRow}>
        <View>
          <Text style={styles.label}>Task Price</Text>
          <Text style={styles.taskPrice}>KES {item.posted_price}</Text>
        </View>
        <View>
          <Text style={styles.label}>Your Bid</Text>
          <Text style={styles.myBidAmount}>KES {item.myBid?.amount}</Text>
        </View>
      </View>

      <View style={styles.bidFooter}>
        <View style={[styles.bidStatusBadge, { backgroundColor: getBidStatusColor(item.myBid?.status || '') }]}>
          <Text style={styles.bidStatusText}>{item.myBid?.status}</Text>
        </View>
        <Text style={styles.bidDate}>
          Bid placed: {new Date(item.myBid?.created_at || '').toLocaleDateString()}
        </Text>
      </View>

      {item.myBid?.status === 'Accepted' && (
        <View style={styles.acceptedBanner}>
          <Text style={styles.acceptedText}>🎉 Your bid was accepted!</Text>
        </View>
      )}
    </TouchableOpacity>
  );

  if (loading && !refreshing) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color="#007bff" />
        <Text style={styles.loadingText}>Loading your bids...</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => goBack()} style={styles.backButton}>
          <Text style={styles.backText}>← Back</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>My Bids</Text>
        <View style={{ width: 60 }} />
      </View>

      <View style={styles.summary}>
        <View style={styles.summaryItem}>
          <Text style={styles.summaryNumber}>{tasks.length}</Text>
          <Text style={styles.summaryLabel}>Total Bids</Text>
        </View>
        <View style={styles.summaryItem}>
          <Text style={[styles.summaryNumber, { color: '#FF9800' }]}>
            {tasks.filter(t => t.myBid?.status === 'Pending').length}
          </Text>
          <Text style={styles.summaryLabel}>Pending</Text>
        </View>
        <View style={styles.summaryItem}>
          <Text style={[styles.summaryNumber, { color: '#28a745' }]}>
            {tasks.filter(t => t.myBid?.status === 'Accepted').length}
          </Text>
          <Text style={styles.summaryLabel}>Accepted</Text>
        </View>
      </View>

      <FlatList
        data={tasks}
        renderItem={renderBid}
        keyExtractor={(item) => item.id.toString()}
        contentContainerStyle={styles.listContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
        }
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyText}>No bids yet</Text>
            <Text style={styles.emptySubtext}>
              Browse available tasks and submit your first bid!
            </Text>
            <TouchableOpacity
              style={styles.browseButton}
              onPress={() => router.push('/tasks' as any)}
            >
              <Text style={styles.browseButtonText}>Browse Tasks</Text>
            </TouchableOpacity>
          </View>
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#f5f5f5',
  },
  loadingText: {
    marginTop: 10,
    color: '#666',
    fontSize: 14,
  },
  header: {
    backgroundColor: '#fff',
    padding: 16,
    paddingTop: 60,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
  },
  backButton: {
    padding: 4,
  },
  backText: {
    fontSize: 16,
    color: '#007bff',
    fontWeight: '600',
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#1a1a1a',
  },
  summary: {
    flexDirection: 'row',
    backgroundColor: '#fff',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
  },
  summaryItem: {
    flex: 1,
    alignItems: 'center',
  },
  summaryNumber: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#007bff',
  },
  summaryLabel: {
    fontSize: 12,
    color: '#666',
    marginTop: 4,
  },
  listContent: {
    padding: 16,
  },
  bidCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
    shadowColor: '#000',
    shadowOpacity: 0.1,
    shadowOffset: { width: 0, height: 2 },
    shadowRadius: 4,
    elevation: 3,
  },
  bidHeader: {
    flexDirection: 'row',
    marginBottom: 12,
  },
  taskTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#1a1a1a',
    marginBottom: 4,
  },
  taskCategory: {
    fontSize: 13,
    color: '#666',
    marginBottom: 2,
  },
  household: {
    fontSize: 13,
    color: '#666',
  },
  taskStatusBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
    height: 24,
  },
  statusText: {
    color: '#fff',
    fontSize: 11,
    fontWeight: '600',
  },
  priceRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    backgroundColor: '#f8f9fa',
    padding: 12,
    borderRadius: 8,
    marginBottom: 12,
  },
  label: {
    fontSize: 11,
    color: '#666',
    marginBottom: 4,
  },
  taskPrice: {
    fontSize: 16,
    fontWeight: '600',
    color: '#666',
  },
  myBidAmount: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#007bff',
  },
  bidFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  bidStatusBadge: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 12,
  },
  bidStatusText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: '600',
  },
  bidDate: {
    fontSize: 12,
    color: '#999',
  },
  acceptedBanner: {
    backgroundColor: '#e8f5e9',
    padding: 10,
    borderRadius: 8,
    marginTop: 12,
    alignItems: 'center',
  },
  acceptedText: {
    color: '#28a745',
    fontSize: 14,
    fontWeight: '600',
  },
  emptyContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 60,
  },
  emptyText: {
    fontSize: 18,
    fontWeight: '600',
    color: '#999',
    marginBottom: 8,
  },
  emptySubtext: {
    fontSize: 14,
    color: '#bbb',
    textAlign: 'center',
    marginBottom: 20,
  },
  browseButton: {
    backgroundColor: '#007bff',
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 8,
  },
  browseButtonText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '600',
  },
});
