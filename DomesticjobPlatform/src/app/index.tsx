import { useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView, ActivityIndicator, RefreshControl } from 'react-native';
import { useRouter } from 'expo-router';
import { useAuth } from '@/context/AuthContext';
import { api } from '@/services/api';

interface DashboardStats {
  activeBids: number;
  completedTasks: number;
  rating: number;
  postedTasks: number;
  activeTasks: number;
}

export default function HomeScreen() {
  const router = useRouter();
  const { user, isLoading, logout } = useAuth();
  const [stats, setStats] = useState<DashboardStats>({
    activeBids: 0, completedTasks: 0, rating: 0, postedTasks: 0, activeTasks: 0,
  });
  const [statsLoading, setStatsLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);

  const fetchStats = async () => {
    if (!user) return;
    setStatsLoading(true);
    try {
      const [tasks, ratingData, notifData] = await Promise.allSettled([
        api.tasks.list(),
        api.ratings.getUserSummary(user.id),
        api.notifications.list(),
      ]);

      const allTasks = tasks.status === 'fulfilled' ? tasks.value : [];
      const rating = ratingData.status === 'fulfilled' ? ratingData.value : null;
      if (notifData.status === 'fulfilled') {
        setUnreadCount(notifData.value.unread_count);
      }

      if (user.role === 'STUDENT') {
        // Count tasks where this student has a bid
        const myBidTasks = allTasks.filter((t: any) =>
          t.bids?.some((b: any) => b.student_username === user.username)
        );
        const activeBids = myBidTasks.filter((t: any) =>
          ['Posted', 'Bidding', 'Assigned', 'InProgress'].includes(t.status)
        ).length;
        const completed = myBidTasks.filter((t: any) => t.status === 'Completed').length;

        setStats({
          activeBids,
          completedTasks: completed,
          rating: rating?.average_rating ?? 0,
          postedTasks: 0,
          activeTasks: 0,
        });
      } else {
        // Household: count their posted tasks
        const myTasks = allTasks.filter((t: any) => t.household_owner === user.id);
        const active = myTasks.filter((t: any) =>
          ['Posted', 'Bidding', 'Assigned', 'InProgress'].includes(t.status)
        ).length;
        const completed = myTasks.filter((t: any) => t.status === 'Completed').length;

        setStats({
          activeBids: 0,
          completedTasks: completed,
          rating: rating?.average_rating ?? 0,
          postedTasks: myTasks.length,
          activeTasks: active,
        });
      }
    } catch (e) {
      // stats stay at defaults — not a crash
    } finally {
      setStatsLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    if (user && !isLoading) fetchStats();
  }, [user, isLoading]);

  const onRefresh = () => {
    setRefreshing(true);
    fetchStats();
  };

  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#007bff" />
        <Text style={styles.loadingText}>Loading...</Text>
      </View>
    );
  }

  // Welcome screen for unauthenticated users
  if (!user) {
    return (
      <View style={styles.container}>
        <View style={styles.heroSection}>
          <Text style={styles.heroEmoji}>🏠</Text>
          <Text style={styles.title}>Domestic Job Platform</Text>
          <Text style={styles.subtitle}>
            Connecting Kenyan university students with households that need help
          </Text>
        </View>

        <TouchableOpacity
          style={styles.primaryButton}
          onPress={() => router.push('/auth/register-student')}
        >
          <Text style={styles.buttonText}>🎓 I am a University Student</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.secondaryButton}
          onPress={() => router.push('/auth/register-household')}
        >
          <Text style={styles.buttonText}>🏠 I am a Household Owner</Text>
        </TouchableOpacity>

        <TouchableOpacity onPress={() => router.push('/auth/login')}>
          <Text style={styles.linkText}>Already have an account? Log in</Text>
        </TouchableOpacity>
      </View>
    );
  }

  // Dashboard for authenticated users
  return (
    <ScrollView
      style={styles.dashboardContainer}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
    >
      {/* Header */}
      <View style={styles.header}>
        <View>
          <Text style={styles.welcomeText}>Welcome back,</Text>
          <Text style={styles.userName}>{user.first_name || user.username}!</Text>
          <Text style={styles.roleTag}>
            {user.role === 'STUDENT' ? '🎓 Student' : '🏠 Household Owner'}
          </Text>
        </View>
        <TouchableOpacity
          style={styles.logoutButton}
          onPress={async () => {
            await logout();
            router.replace('/auth/login');
          }}
        >
          <Text style={styles.logoutText}>Logout</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.bellButton}
          onPress={() => router.push('/notifications' as any)}
        >
          <Text style={styles.bellIcon}>🔔</Text>
          {unreadCount > 0 && (
            <View style={styles.badge}>
              <Text style={styles.badgeText}>{unreadCount > 9 ? '9+' : String(unreadCount)}</Text>
            </View>
          )}
        </TouchableOpacity>
      </View>

      {/* Stats */}
      <View style={styles.statsContainer}>
        {user.role === 'STUDENT' ? (
          <>
            <View style={styles.statCard}>
              {statsLoading ? <ActivityIndicator size="small" color="#007bff" /> : (
                <Text style={styles.statNumber}>{stats.activeBids}</Text>
              )}
              <Text style={styles.statLabel}>Active Bids</Text>
            </View>
            <View style={styles.statCard}>
              {statsLoading ? <ActivityIndicator size="small" color="#007bff" /> : (
                <Text style={styles.statNumber}>{stats.completedTasks}</Text>
              )}
              <Text style={styles.statLabel}>Completed</Text>
            </View>
            <View style={styles.statCard}>
              {statsLoading ? <ActivityIndicator size="small" color="#007bff" /> : (
                <Text style={styles.statNumber}>{stats.rating.toFixed(1)}</Text>
              )}
              <Text style={styles.statLabel}>Rating ⭐</Text>
            </View>
          </>
        ) : (
          <>
            <View style={styles.statCard}>
              {statsLoading ? <ActivityIndicator size="small" color="#007bff" /> : (
                <Text style={styles.statNumber}>{stats.activeTasks}</Text>
              )}
              <Text style={styles.statLabel}>Active Tasks</Text>
            </View>
            <View style={styles.statCard}>
              {statsLoading ? <ActivityIndicator size="small" color="#007bff" /> : (
                <Text style={styles.statNumber}>{stats.completedTasks}</Text>
              )}
              <Text style={styles.statLabel}>Completed</Text>
            </View>
            <View style={styles.statCard}>
              {statsLoading ? <ActivityIndicator size="small" color="#007bff" /> : (
                <Text style={styles.statNumber}>{stats.rating.toFixed(1)}</Text>
              )}
              <Text style={styles.statLabel}>Rating ⭐</Text>
            </View>
          </>
        )}
      </View>

      {/* Student Dashboard */}
      {user.role === 'STUDENT' && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Student Dashboard</Text>

          <View style={styles.infoCard}>
            <Text style={styles.infoTitle}>University Information</Text>
            <Text style={styles.infoText}>
              {user.student_profile?.university_name || 'Not set'}
            </Text>
            <Text style={styles.infoSubtext}>
              ID: {user.student_profile?.university_id || 'Not set'}
            </Text>
            <Text style={[
              styles.statusBadge,
              user.student_profile?.verification_status === 'Verified' ? styles.verified : styles.pending,
            ]}>
              Status: {user.student_profile?.verification_status || 'Pending'}
            </Text>
          </View>

          <TouchableOpacity
            style={styles.actionButton}
            onPress={() => router.push('/tasks' as any)}
          >
            <Text style={styles.actionButtonText}>🔍 Browse Available Tasks</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.actionButtonSecondary}
            onPress={() => router.push('/my-bids' as any)}
          >
            <Text style={styles.actionButtonSecondaryText}>💼 My Bids</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.actionButtonSecondary}
            onPress={() => router.push({ pathname: '/tasks', params: { my_tasks: 'true' } } as any)}
          >
            <Text style={styles.actionButtonSecondaryText}>📋 My Assigned Tasks</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Household Dashboard */}
      {user.role === 'HOUSEHOLD' && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Household Dashboard</Text>

          <View style={styles.infoCard}>
            <Text style={styles.infoTitle}>Location</Text>
            <Text style={styles.infoText}>
              {user.household_profile?.address || 'Address not set'}
            </Text>
            <Text style={[
              styles.statusBadge,
              user.household_profile?.verification_status === 'Verified' ? styles.verified : styles.pending,
            ]}>
              Status: {user.household_profile?.verification_status || 'Pending'}
            </Text>
          </View>

          <TouchableOpacity
            style={styles.actionButton}
            onPress={() => router.push('/tasks/create' as any)}
          >
            <Text style={styles.actionButtonText}>➕ Post New Task</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.actionButtonSecondary}
            onPress={() => router.push('/tasks' as any)}
          >
            <Text style={styles.actionButtonSecondaryText}>📋 My Posted Tasks</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.actionButtonSecondary}
            onPress={() => router.push({ pathname: '/tasks', params: { status: 'InProgress' } } as any)}
          >
            <Text style={styles.actionButtonSecondaryText}>⚡ Active Tasks</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Quick Actions */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Quick Actions</Text>

        <TouchableOpacity
          style={styles.menuItem}
          onPress={() => router.push('/notifications' as any)}
        >
          <View style={styles.menuItemLeft}>
            <Text style={styles.menuItemText}>🔔 Notifications</Text>
          </View>
          {unreadCount > 0 && (
            <View style={styles.menuBadge}>
              <Text style={styles.menuBadgeText}>{unreadCount}</Text>
            </View>
          )}
          {unreadCount === 0 && <Text style={styles.menuItemArrow}>›</Text>}
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.menuItem}
          onPress={() => router.push('/tasks' as any)}
        >
          <Text style={styles.menuItemText}>👤 My Profile</Text>
          <Text style={styles.menuItemArrow}>›</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.menuItem}
          onPress={() => router.push('/tasks' as any)}
        >
          <Text style={styles.menuItemText}>⭐ My Ratings</Text>
          <Text style={styles.menuItemArrow}>›</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.menuItem}
          onPress={() => router.push('/tasks' as any)}
        >
          <Text style={styles.menuItemText}>💰 Payment History</Text>
          <Text style={styles.menuItemArrow}>›</Text>
        </TouchableOpacity>
      </View>

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  loadingContainer: {
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
  // Welcome screen
  container: {
    flex: 1,
    justifyContent: 'center',
    padding: 24,
    backgroundColor: '#f5f5f5',
  },
  heroSection: {
    alignItems: 'center',
    marginBottom: 40,
  },
  heroEmoji: {
    fontSize: 64,
    marginBottom: 16,
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    textAlign: 'center',
    color: '#1a1a1a',
    marginBottom: 10,
  },
  subtitle: {
    fontSize: 15,
    textAlign: 'center',
    color: '#666',
    lineHeight: 22,
  },
  primaryButton: {
    backgroundColor: '#007bff',
    padding: 16,
    borderRadius: 10,
    marginBottom: 14,
  },
  secondaryButton: {
    backgroundColor: '#28a745',
    padding: 16,
    borderRadius: 10,
    marginBottom: 28,
  },
  buttonText: {
    color: '#fff',
    textAlign: 'center',
    fontWeight: 'bold',
    fontSize: 16,
  },
  linkText: {
    color: '#007bff',
    textAlign: 'center',
    fontSize: 15,
  },
  // Dashboard
  dashboardContainer: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  header: {
    backgroundColor: '#007bff',
    padding: 20,
    paddingTop: 60,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  welcomeText: {
    fontSize: 14,
    color: 'rgba(255,255,255,0.8)',
  },
  userName: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#fff',
    marginTop: 2,
  },
  roleTag: {
    fontSize: 13,
    color: 'rgba(255,255,255,0.9)',
    marginTop: 4,
    fontWeight: '600',
  },
  logoutButton: {
    backgroundColor: 'rgba(255,255,255,0.2)',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.4)',
  },
  logoutText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  statsContainer: {
    flexDirection: 'row',
    padding: 16,
    gap: 12,
    backgroundColor: '#f5f5f5',
  },
  statCard: {
    flex: 1,
    backgroundColor: '#fff',
    padding: 16,
    borderRadius: 12,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOpacity: 0.05,
    shadowOffset: { width: 0, height: 2 },
    shadowRadius: 4,
    elevation: 2,
    minHeight: 72,
    justifyContent: 'center',
  },
  statNumber: {
    fontSize: 26,
    fontWeight: 'bold',
    color: '#007bff',
  },
  statLabel: {
    fontSize: 11,
    color: '#666',
    marginTop: 4,
    textAlign: 'center',
  },
  section: {
    padding: 16,
    paddingTop: 8,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#1a1a1a',
    marginBottom: 14,
  },
  infoCard: {
    backgroundColor: '#fff',
    padding: 16,
    borderRadius: 12,
    marginBottom: 14,
    shadowColor: '#000',
    shadowOpacity: 0.05,
    shadowOffset: { width: 0, height: 2 },
    shadowRadius: 4,
    elevation: 2,
  },
  infoTitle: {
    fontSize: 12,
    color: '#666',
    fontWeight: '600',
    textTransform: 'uppercase',
    marginBottom: 8,
  },
  infoText: {
    fontSize: 16,
    color: '#1a1a1a',
    fontWeight: '500',
  },
  infoSubtext: {
    fontSize: 14,
    color: '#666',
    marginTop: 4,
  },
  statusBadge: {
    fontSize: 12,
    fontWeight: '600',
    marginTop: 10,
    paddingVertical: 4,
    paddingHorizontal: 10,
    borderRadius: 6,
    alignSelf: 'flex-start',
    overflow: 'hidden',
  },
  verified: {
    backgroundColor: '#e8f5e9',
    color: '#2e7d32',
  },
  pending: {
    backgroundColor: '#fff3e0',
    color: '#ef6c00',
  },
  actionButton: {
    backgroundColor: '#007bff',
    padding: 16,
    borderRadius: 10,
    marginBottom: 10,
  },
  actionButtonText: {
    color: '#fff',
    textAlign: 'center',
    fontWeight: 'bold',
    fontSize: 16,
  },
  actionButtonSecondary: {
    backgroundColor: '#fff',
    padding: 16,
    borderRadius: 10,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: '#e0e0e0',
  },
  actionButtonSecondaryText: {
    color: '#007bff',
    textAlign: 'center',
    fontWeight: '600',
    fontSize: 16,
  },
  menuItem: {
    backgroundColor: '#fff',
    padding: 16,
    borderRadius: 10,
    marginBottom: 8,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  menuItemText: {
    fontSize: 16,
    color: '#1a1a1a',
  },
  menuItemArrow: {
    fontSize: 20,
    color: '#bbb',
    fontWeight: '300',
  },
  bellButton: {
    position: 'relative',
    padding: 4,
    marginLeft: 8,
  },
  bellIcon: { fontSize: 22 },
  badge: {
    position: 'absolute',
    top: 0,
    right: 0,
    backgroundColor: '#e53935',
    borderRadius: 8,
    minWidth: 16,
    height: 16,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 3,
  },
  badgeText: { color: '#fff', fontSize: 9, fontWeight: 'bold' },
  menuItemLeft: { flex: 1 },
  menuBadge: {
    backgroundColor: '#007bff',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 10,
  },
  menuBadgeText: { color: '#fff', fontSize: 12, fontWeight: 'bold' },
});
