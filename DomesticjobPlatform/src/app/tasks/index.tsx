import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
  TextInput,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useAuth } from '@/context/AuthContext';
import { api } from '@/services/api';
import { useGoBack } from '@/hooks/useGoBack';

interface Task {
  id: number;
  title: string;
  description: string;
  category: string;
  posted_price: string;
  recommended_price: string;
  location_address: string;
  status: string;
  household_owner: number;
  household_owner_name: string;
  assigned_student: number | null;
  bids_count: number;
  created_at: string;
}

export default function TasksListScreen() {
  const router = useRouter();
  const { user } = useAuth();
  const params = useLocalSearchParams();
  const goBack = useGoBack();

  const isHousehold = user?.role === 'HOUSEHOLD';

  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterStatus, setFilterStatus] = useState<string>(
    (params.status as string) || ''
  );

  const fetchTasks = async () => {
    try {
      const fetchParams: any = {};
      if (searchQuery) fetchParams.search = searchQuery;
      if (filterStatus) fetchParams.status = filterStatus;

      // Household owners always see only their own tasks
      // Students see all available tasks (not just their own)
      if (isHousehold) {
        fetchParams.my_tasks = true;
      }

      const data = await api.tasks.list(fetchParams);
      setTasks(data);
    } catch (error: any) {
      console.error('Error fetching tasks:', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchTasks();
  }, [filterStatus]);

  const onRefresh = () => {
    setRefreshing(true);
    fetchTasks();
  };

  const handleSearch = () => {
    setLoading(true);
    fetchTasks();
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'Posted': return '#2196F3';
      case 'Bidding': return '#FF9800';
      case 'Assigned': return '#9C27B0';
      case 'InProgress': return '#FFC107';
      case 'Completed': return '#4CAF50';
      case 'Cancelled': return '#F44336';
      case 'Disputed': return '#E91E63';
      default: return '#757575';
    }
  };

  // Student filter tabs
  const studentFilters = ['', 'Posted', 'Bidding'];
  // Household filter tabs
  const householdFilters = ['', 'Posted', 'Bidding', 'Assigned', 'InProgress', 'Completed'];

  const filterOptions = isHousehold ? householdFilters : studentFilters;
  const filterLabels: Record<string, string> = {
    '': 'All',
    Posted: 'Posted',
    Bidding: 'Bidding',
    Assigned: 'Assigned',
    InProgress: 'In Progress',
    Completed: 'Completed',
  };

  const renderTask = ({ item }: { item: Task }) => {
    const isMyTask = Number(user?.id) === Number(item.household_owner);
    const myBidExists = false; // can extend later

    return (
      <TouchableOpacity
        style={styles.taskCard}
        onPress={() => router.push(`/tasks/${item.id}` as any)}
      >
        <View style={styles.taskHeader}>
          <View style={{ flex: 1 }}>
            <Text style={styles.taskTitle}>{item.title}</Text>
            <Text style={styles.taskCategory}>📂 {item.category}</Text>
          </View>
          <View style={[styles.statusBadge, { backgroundColor: getStatusColor(item.status) }]}>
            <Text style={styles.statusText}>{item.status}</Text>
          </View>
        </View>

        <Text style={styles.taskDescription} numberOfLines={2}>
          {item.description}
        </Text>

        <View style={styles.taskMeta}>
          <Text style={styles.metaText}>📍 {item.location_address || 'Location not set'}</Text>
          {/* Students see who posted; household owners see their own tasks */}
          {!isHousehold && (
            <Text style={styles.metaText}>👤 {item.household_owner_name}</Text>
          )}
          {isHousehold && item.assigned_student && (
            <Text style={styles.metaText}>🎓 Student assigned</Text>
          )}
        </View>

        <View style={styles.taskFooter}>
          <View>
            <Text style={styles.priceLabel}>
              {isHousehold ? 'Your Price' : 'Offered Price'}
            </Text>
            <Text style={styles.price}>KES {item.posted_price}</Text>
          </View>
          <View style={styles.bidsContainer}>
            {isHousehold ? (
              <Text style={styles.bidsCount}>
                💼 {item.bids_count} bid{item.bids_count !== 1 ? 's' : ''}
              </Text>
            ) : (
              <Text style={styles.bidsCount}>
                💼 {item.bids_count} bid{item.bids_count !== 1 ? 's' : ''}
              </Text>
            )}
          </View>
        </View>

        {/* Household: show action hint based on status */}
        {isHousehold && item.status === 'Bidding' && item.bids_count > 0 && (
          <View style={styles.actionHint}>
            <Text style={styles.actionHintText}>👆 Tap to review and accept a bid</Text>
          </View>
        )}
        {isHousehold && item.status === 'Assigned' && (
          <View style={[styles.actionHint, styles.actionHintPurple]}>
            <Text style={styles.actionHintText}>💰 Tap to deposit escrow</Text>
          </View>
        )}
        {isHousehold && item.status === 'InProgress' && (
          <View style={[styles.actionHint, styles.actionHintGreen]}>
            <Text style={styles.actionHintText}>✅ Tap to mark complete</Text>
          </View>
        )}
      </TouchableOpacity>
    );
  };

  if (loading && !refreshing) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color="#007bff" />
        <Text style={styles.loadingText}>Loading tasks...</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={goBack} style={styles.backButton}>
          <Text style={styles.backText}>← Back</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>
          {isHousehold ? 'My Posted Tasks' : 'Available Tasks'}
        </Text>
        {isHousehold && (
          <TouchableOpacity
            style={styles.createButton}
            onPress={() => router.push('/tasks/create' as any)}
          >
            <Text style={styles.createButtonText}>+ Post</Text>
          </TouchableOpacity>
        )}
        {!isHousehold && <View style={{ width: 60 }} />}
      </View>

      {/* Search */}
      <View style={styles.searchContainer}>
        <TextInput
          style={styles.searchInput}
          placeholder={isHousehold ? 'Search your tasks...' : 'Search available tasks...'}
          value={searchQuery}
          onChangeText={setSearchQuery}
          onSubmitEditing={handleSearch}
        />
        <TouchableOpacity style={styles.searchButton} onPress={handleSearch}>
          <Text style={styles.searchButtonText}>🔍</Text>
        </TouchableOpacity>
      </View>

      {/* Filter chips */}
      <View style={styles.filterContainer}>
        {filterOptions.map((f) => (
          <TouchableOpacity
            key={f}
            style={[styles.filterChip, filterStatus === f && styles.filterChipActive]}
            onPress={() => setFilterStatus(f)}
          >
            <Text style={[styles.filterChipText, filterStatus === f && styles.filterChipTextActive]}>
              {filterLabels[f]}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <FlatList
        data={tasks}
        renderItem={renderTask}
        keyExtractor={(item) => item.id.toString()}
        contentContainerStyle={styles.listContent}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyText}>
              {isHousehold ? 'No tasks posted yet' : 'No tasks available'}
            </Text>
            <Text style={styles.emptySubtext}>
              {isHousehold
                ? 'Post your first task to get started!'
                : 'Check back soon for new opportunities'}
            </Text>
            {isHousehold && (
              <TouchableOpacity
                style={styles.postButton}
                onPress={() => router.push('/tasks/create' as any)}
              >
                <Text style={styles.postButtonText}>Post a Task</Text>
              </TouchableOpacity>
            )}
          </View>
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f5f5' },
  centerContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#f5f5f5' },
  loadingText: { marginTop: 10, color: '#666', fontSize: 14 },
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
  backButton: { padding: 4 },
  backText: { fontSize: 16, color: '#007bff', fontWeight: '600' },
  headerTitle: { fontSize: 20, fontWeight: 'bold', color: '#1a1a1a' },
  createButton: {
    backgroundColor: '#007bff',
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 8,
  },
  createButtonText: { color: '#fff', fontWeight: '600', fontSize: 14 },
  searchContainer: {
    flexDirection: 'row',
    padding: 12,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
  },
  searchInput: {
    flex: 1,
    borderWidth: 1,
    borderColor: '#d0d0d0',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
    fontSize: 14,
    backgroundColor: '#f9f9f9',
  },
  searchButton: {
    marginLeft: 8,
    backgroundColor: '#007bff',
    paddingHorizontal: 14,
    borderRadius: 8,
    justifyContent: 'center',
  },
  searchButtonText: { fontSize: 18 },
  filterContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    padding: 10,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
    gap: 6,
  },
  filterChip: {
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: 14,
    backgroundColor: '#f0f0f0',
  },
  filterChipActive: { backgroundColor: '#007bff' },
  filterChipText: { fontSize: 12, color: '#666', fontWeight: '500' },
  filterChipTextActive: { color: '#fff', fontWeight: '600' },
  listContent: { padding: 14 },
  taskCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 14,
    marginBottom: 14,
    shadowColor: '#000',
    shadowOpacity: 0.08,
    shadowOffset: { width: 0, height: 2 },
    shadowRadius: 4,
    elevation: 3,
  },
  taskHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 6,
  },
  taskTitle: { fontSize: 17, fontWeight: 'bold', color: '#1a1a1a', marginBottom: 3 },
  taskCategory: { fontSize: 12, color: '#666' },
  statusBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 10 },
  statusText: { color: '#fff', fontSize: 11, fontWeight: '600' },
  taskDescription: { fontSize: 13, color: '#555', lineHeight: 19, marginBottom: 10 },
  taskMeta: { marginBottom: 10 },
  metaText: { fontSize: 12, color: '#666', marginBottom: 3 },
  taskFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderTopWidth: 1,
    borderTopColor: '#f0f0f0',
    paddingTop: 10,
  },
  priceLabel: { fontSize: 11, color: '#999', marginBottom: 2 },
  price: { fontSize: 17, fontWeight: 'bold', color: '#28a745' },
  bidsContainer: { backgroundColor: '#f8f9fa', paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8 },
  bidsCount: { fontSize: 12, color: '#666', fontWeight: '600' },
  actionHint: {
    marginTop: 10,
    backgroundColor: '#fff3e0',
    padding: 8,
    borderRadius: 6,
    alignItems: 'center',
  },
  actionHintPurple: { backgroundColor: '#f3e5f5' },
  actionHintGreen: { backgroundColor: '#e8f5e9' },
  actionHintText: { fontSize: 12, color: '#555', fontWeight: '500' },
  emptyContainer: { alignItems: 'center', paddingVertical: 60 },
  emptyText: { fontSize: 18, fontWeight: '600', color: '#999', marginBottom: 8 },
  emptySubtext: { fontSize: 14, color: '#bbb', textAlign: 'center', marginBottom: 20 },
  postButton: { backgroundColor: '#007bff', paddingHorizontal: 24, paddingVertical: 12, borderRadius: 8 },
  postButtonText: { color: '#fff', fontSize: 15, fontWeight: '600' },
});
