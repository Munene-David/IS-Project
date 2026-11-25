import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  FlatList,
  Modal,
  StyleSheet,
  ActivityIndicator,
  Alert,
  ScrollView,
  SafeAreaView,
  Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useAuth } from '@/context/AuthContext';
import { api } from '@/services/api';

export default function MarketplaceScreen() {
  const router = useRouter();
  const { user, logout } = useAuth();

  // Tasks state
  const [tasks, setTasks] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('All');
  const [priceGuides, setPriceGuides] = useState<Record<string, any>>({});

  // Modals state
  const [postModalVisible, setPostModalVisible] = useState(false);
  const [bidModalVisible, setBidModalVisible] = useState(false);
  const [bidsReviewModalVisible, setBidsReviewModalVisible] = useState(false);
  const [escrowModalVisible, setEscrowModalVisible] = useState(false);
  const [chatModalVisible, setChatModalVisible] = useState(false);
  const [rateModalVisible, setRateModalVisible] = useState(false);

  // Active task context for modals
  const [activeTask, setActiveTask] = useState<any | null>(null);

  // Form states
  // Post Task Form
  const [taskCategory, setTaskCategory] = useState('Cleaning');
  const [taskTitle, setTaskTitle] = useState('');
  const [taskDesc, setTaskDesc] = useState('');
  const [taskPrice, setTaskPrice] = useState('500');
  const [taskLocation, setTaskLocation] = useState('Kilimani, Nairobi');

  // Submit Bid Form
  const [bidAmount, setBidAmount] = useState('');
  const [bidMessage, setBidMessage] = useState('');

  // Escrow Form
  const [escrowPhone, setEscrowPhone] = useState(user?.phone_number || '254712345678');
  const [escrowLoading, setEscrowLoading] = useState(false);

  // Chat Form
  const [chatMessages, setChatMessages] = useState<any[]>([]);
  const [newMsg, setNewMsg] = useState('');

  // Rating Form
  const [rateScore, setRateScore] = useState(5);
  const [rateComment, setRateComment] = useState('');

  useEffect(() => {
    loadPriceGuides();
    loadTasks();
  }, [selectedCategory]);

  const loadPriceGuides = async () => {
    try {
      const guides = await api.priceGuide.getAll();
      const map: Record<string, any> = {};
      guides.forEach((g) => {
        map[g.category] = g;
      });
      setPriceGuides(map);
    } catch (err) {
      console.warn('Failed to load price guides', err);
    }
  };

  const loadTasks = async () => {
    setLoading(true);
    try {
      const params: any = {};
      if (selectedCategory !== 'All') params.category = selectedCategory;
      if (search.trim()) params.search = search.trim();
      const list = await api.tasks.list(params);
      setTasks(list);
    } catch (err) {
      console.warn('Failed to load tasks', err);
    } finally {
      setLoading(false);
    }
  };

  // Open Post Task
  const handleOpenPostTask = () => {
    if (!user) {
      router.push('/auth/login' as any);
      return;
    }
    const guide = priceGuides[taskCategory];
    if (guide) {
      setTaskPrice(String(guide.recommended_price));
    }
    setPostModalVisible(true);
  };

  // Submit Post Task
  const handleCreateTask = async () => {
    if (!taskTitle.trim() || !taskPrice) {
      Alert.alert('Required Fields', 'Please enter a title and price.');
      return;
    }
    try {
      await api.tasks.create({
        title: taskTitle.trim(),
        description: taskDesc.trim(),
        category: taskCategory,
        posted_price: parseFloat(taskPrice),
        recommended_price: priceGuides[taskCategory]?.recommended_price,
        location_address: taskLocation,
        location_lat: -1.2921,
        location_lng: 36.7856,
      });
      setPostModalVisible(false);
      setTaskTitle('');
      setTaskDesc('');
      loadTasks();
      Alert.alert('Success', 'Task posted successfully to marketplace!');
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Failed to post task.');
    }
  };

  // Submit Bid
  const handleOpenBid = (task: any) => {
    if (!user) {
      router.push('/auth/login' as any);
      return;
    }
    setActiveTask(task);
    setBidAmount(String(task.posted_price));
    setBidMessage('');
    setBidModalVisible(true);
  };

  const handleSubmitBid = async () => {
    if (!activeTask || !bidAmount) return;
    try {
      await api.tasks.submitBid(activeTask.id, parseFloat(bidAmount), bidMessage);
      setBidModalVisible(false);
      loadTasks();
      Alert.alert('Bid Submitted', 'Your proposal was sent to the household owner!');
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Failed to submit bid.');
    }
  };

  // Household reviews bids
  const handleOpenBidsReview = async (task: any) => {
    try {
      const fullTask = await api.tasks.get(task.id);
      setActiveTask(fullTask);
      setBidsReviewModalVisible(true);
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Failed to load bids.');
    }
  };

  // Accept Bid
  const handleAcceptBid = async (bidId: number) => {
    if (!activeTask) return;
    try {
      const res = await api.tasks.acceptBid(activeTask.id, bidId);
      setActiveTask(res.task);
      setBidsReviewModalVisible(false);
      // Immediately open Escrow modal
      setEscrowPhone(user?.phone_number || '254712345678');
      setEscrowModalVisible(true);
      loadTasks();
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Failed to accept bid.');
    }
  };

  // Pay Escrow via M-Pesa
  const handlePayEscrow = async () => {
    if (!activeTask || !escrowPhone) return;
    setEscrowLoading(true);
    try {
      await api.payments.initiateEscrow(activeTask.id, escrowPhone);
      setEscrowModalVisible(false);
      loadTasks();
      Alert.alert('Payment Successful', 'M-Pesa payment verified. Funds held safely in escrow!');
    } catch (err: any) {
      Alert.alert('Payment Error', err.message || 'Escrow deposit failed.');
    } finally {
      setEscrowLoading(false);
    }
  };

  // Mark Complete & Release Escrow
  const handleMarkComplete = async (task: any) => {
    try {
      await api.tasks.markComplete(task.id);
      loadTasks();
      Alert.alert(
        'Task Complete',
        user?.role === 'HOUSEHOLD'
          ? 'Task marked as completed! Escrow funds released to student.'
          : 'You marked task as completed. Waiting for household confirmation.'
      );
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Failed to update task.');
    }
  };

  // Open Chat
  const handleOpenChat = async (task: any) => {
    if (!user) {
      router.push('/auth/login' as any);
      return;
    }
    setActiveTask(task);
    try {
      const msgs = await api.tasks.getMessages(task.id);
      setChatMessages(msgs);
      setChatModalVisible(true);
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Failed to load messages.');
    }
  };

  const handleSendMessage = async () => {
    if (!activeTask || !newMsg.trim()) return;
    try {
      const msg = await api.tasks.sendMessage(activeTask.id, newMsg.trim());
      setChatMessages((prev) => [...prev, msg]);
      setNewMsg('');
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Failed to send message.');
    }
  };

  // Open Rating
  const handleOpenRating = (task: any) => {
    setActiveTask(task);
    setRateScore(5);
    setRateComment('');
    setRateModalVisible(true);
  };

  const handleSubmitRating = async () => {
    if (!activeTask) return;
    const targetUserId =
      user?.id === activeTask.household_owner
        ? activeTask.assigned_student
        : activeTask.household_owner;

    try {
      await api.ratings.create(activeTask.id, targetUserId, rateScore, rateComment);
      setRateModalVisible(false);
      Alert.alert('Rating Submitted', 'Thank you for rating your experience!');
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Failed to submit rating.');
    }
  };

  const categories = ['All', 'Cleaning', 'Laundry', 'Childcare', 'Gardening', 'Cooking'];

  return (
    <SafeAreaView style={styles.safeArea}>
      {/* Top App Bar */}
      <View style={styles.header}>
        <View>
          <Text style={styles.appTitle}>Task Marketplace</Text>
          <Text style={styles.appSub}>Domestic Tasks & Student Opportunities</Text>
        </View>

        {user ? (
          <View style={styles.userSection}>
            <View style={styles.userBadge}>
              <Text style={styles.userName}>{user.username}</Text>
              <Text style={styles.userRole}>
                {user.role === 'STUDENT' ? '🎓 Student' : '🏡 Household'}
              </Text>
            </View>
            <TouchableOpacity onPress={logout} style={styles.logoutBtn}>
              <Text style={styles.logoutText}>Logout</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <TouchableOpacity
            style={styles.loginBtn}
            onPress={() => router.push('/auth/login' as any)}>
            <Text style={styles.loginBtnText}>Sign In</Text>
          </TouchableOpacity>
        )}
      </View>

      {/* Main Content */}
      <View style={styles.container}>
        {/* Action Button for Household */}
        {user?.role === 'HOUSEHOLD' && (
          <TouchableOpacity style={styles.postTaskBanner} onPress={handleOpenPostTask}>
            <Text style={styles.postTaskBannerText}>＋ Post a New Task</Text>
            <Text style={styles.postTaskBannerSub}>Get instant quotes with fair price guides</Text>
          </TouchableOpacity>
        )}

        {/* Search & Filter Header (Wireframe: Task.png) */}
        <View style={styles.searchContainer}>
          <TextInput
            style={styles.searchInput}
            placeholder='Search: "cleaning near me"'
            value={search}
            onChangeText={setSearch}
            onSubmitEditing={loadTasks}
          />
          <TouchableOpacity style={styles.searchBtn} onPress={loadTasks}>
            <Text style={styles.searchBtnText}>Search</Text>
          </TouchableOpacity>
        </View>

        {/* Category Pills */}
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={styles.categoryScroll}
          contentContainerStyle={styles.categoryContent}>
          {categories.map((cat) => (
            <TouchableOpacity
              key={cat}
              style={[
                styles.categoryPill,
                selectedCategory === cat && styles.categoryPillActive,
              ]}
              onPress={() => setSelectedCategory(cat)}>
              <Text
                style={[
                  styles.categoryPillText,
                  selectedCategory === cat && styles.categoryPillTextActive,
                ]}>
                {cat}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        {/* Task List / Table */}
        {loading ? (
          <ActivityIndicator size="large" color="#0969DA" style={{ marginTop: 40 }} />
        ) : (
          <FlatList
            data={tasks}
            keyExtractor={(item) => String(item.id)}
            contentContainerStyle={styles.taskList}
            ListEmptyComponent={
              <View style={styles.emptyContainer}>
                <Text style={styles.emptyText}>No tasks found in this category.</Text>
                {user?.role === 'HOUSEHOLD' && (
                  <TouchableOpacity onPress={handleOpenPostTask}>
                    <Text style={styles.emptyAction}>Be the first to post a task!</Text>
                  </TouchableOpacity>
                )}
              </View>
            }
            renderItem={({ item }) => {
              const isOwner = user?.id === item.household_owner;
              const isAssigned = user?.id === item.assigned_student;

              return (
                <View style={styles.taskCard}>
                  <View style={styles.taskCardHeader}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.taskTitle}>{item.title}</Text>
                      <Text style={styles.taskMeta}>
                        Category: <Text style={styles.bold}>{item.category}</Text> • By{' '}
                        {item.household_owner_name}
                      </Text>
                    </View>
                    <View style={styles.priceContainer}>
                      <Text style={styles.priceAmount}>KES {item.posted_price}</Text>
                      <View
                        style={[
                          styles.statusBadge,
                          item.status === 'Completed'
                            ? styles.statusCompleted
                            : item.status === 'InProgress'
                            ? styles.statusInProgress
                            : styles.statusOpen,
                        ]}>
                        <Text style={styles.statusText}>{item.status}</Text>
                      </View>
                    </View>
                  </View>

                  <Text style={styles.taskDesc} numberOfLines={2}>
                    {item.description}
                  </Text>
                  <Text style={styles.taskLoc}>📍 {item.location_address || 'Nairobi'}</Text>

                  {/* Actions according to role */}
                  <View style={styles.actionRow}>
                    {isOwner ? (
                      <>
                        <TouchableOpacity
                          style={styles.actionButtonSecondary}
                          onPress={() => handleOpenBidsReview(item)}>
                          <Text style={styles.actionButtonSecondaryText}>
                            Bids Received ({item.bids_count})
                          </Text>
                        </TouchableOpacity>

                        {item.status === 'InProgress' && (
                          <TouchableOpacity
                            style={styles.actionButtonSuccess}
                            onPress={() => handleMarkComplete(item)}>
                            <Text style={styles.actionButtonSuccessText}>
                              Confirm & Release Escrow
                            </Text>
                          </TouchableOpacity>
                        )}

                        {item.status === 'Completed' && (
                          <TouchableOpacity
                            style={styles.actionButtonPrimary}
                            onPress={() => handleOpenRating(item)}>
                            <Text style={styles.actionButtonPrimaryText}>Rate Student</Text>
                          </TouchableOpacity>
                        )}
                      </>
                    ) : (
                      <>
                        {user?.role === 'STUDENT' && item.status in ['Posted', 'Bidding'] && (
                          <TouchableOpacity
                            style={styles.actionButtonPrimary}
                            onPress={() => handleOpenBid(item)}>
                            <Text style={styles.actionButtonPrimaryText}>Submit Bid</Text>
                          </TouchableOpacity>
                        )}

                        {isAssigned && item.status === 'InProgress' && (
                          <TouchableOpacity
                            style={styles.actionButtonSuccess}
                            onPress={() => handleMarkComplete(item)}>
                            <Text style={styles.actionButtonSuccessText}>
                              Mark Task as Complete
                            </Text>
                          </TouchableOpacity>
                        )}

                        {isAssigned && item.status === 'Completed' && (
                          <TouchableOpacity
                            style={styles.actionButtonPrimary}
                            onPress={() => handleOpenRating(item)}>
                            <Text style={styles.actionButtonPrimaryText}>Rate Household</Text>
                          </TouchableOpacity>
                        )}
                      </>
                    )}

                    {(isOwner || isAssigned) && (
                      <TouchableOpacity
                        style={styles.actionButtonChat}
                        onPress={() => handleOpenChat(item)}>
                        <Text style={styles.actionButtonChatText}>💬 Message</Text>
                      </TouchableOpacity>
                    )}
                  </View>
                </View>
              );
            }}
          />
        )}
      </View>

      {/* MODAL 1: Post Task (Wireframe: PostTask.png) */}
      <Modal visible={postModalVisible} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>Post a New Task</Text>

            <Text style={styles.modalLabel}>Category</Text>
            <View style={styles.pickerRow}>
              {['Cleaning', 'Laundry', 'Childcare', 'Gardening', 'Cooking'].map((cat) => (
                <TouchableOpacity
                  key={cat}
                  style={[
                    styles.pickerOption,
                    taskCategory === cat && styles.pickerOptionActive,
                  ]}
                  onPress={() => {
                    setTaskCategory(cat);
                    const guide = priceGuides[cat];
                    if (guide) setTaskPrice(String(guide.recommended_price));
                  }}>
                  <Text
                    style={[
                      styles.pickerOptionText,
                      taskCategory === cat && styles.pickerOptionTextActive,
                    ]}>
                    {cat}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            {/* Price Guide Recommendation Banner */}
            <View style={styles.guideBanner}>
              <Text style={styles.guideBannerText}>
                💡 Recommended price for "{taskCategory}": KES{' '}
                {priceGuides[taskCategory]?.recommended_price || 500} (range{' '}
                {priceGuides[taskCategory]?.min_price || 300}-
                {priceGuides[taskCategory]?.max_price || 800})
              </Text>
            </View>

            <Text style={styles.modalLabel}>Your Price (KES)</Text>
            <TextInput
              style={styles.modalInput}
              keyboardType="numeric"
              value={taskPrice}
              onChangeText={setTaskPrice}
            />

            <Text style={styles.modalLabel}>Title</Text>
            <TextInput
              style={styles.modalInput}
              placeholder="e.g. Living Room Cleaning"
              value={taskTitle}
              onChangeText={setTaskTitle}
            />

            <Text style={styles.modalLabel}>Description</Text>
            <TextInput
              style={[styles.modalInput, { height: 70 }]}
              multiline
              placeholder="Details about task requirements..."
              value={taskDesc}
              onChangeText={setTaskDesc}
            />

            <Text style={styles.modalLabel}>Location</Text>
            <TextInput
              style={styles.modalInput}
              value={taskLocation}
              onChangeText={setTaskLocation}
            />

            <View style={styles.modalBtnRow}>
              <TouchableOpacity
                style={styles.modalCancelBtn}
                onPress={() => setPostModalVisible(false)}>
                <Text style={styles.modalCancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.modalSubmitBtn}
                onPress={handleCreateTask}>
                <Text style={styles.modalSubmitText}>Post Task</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* MODAL 2: Submit Bid */}
      <Modal visible={bidModalVisible} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>Submit Proposal / Bid</Text>
            <Text style={styles.modalSubTitle}>Task: {activeTask?.title}</Text>

            <Text style={styles.modalLabel}>Bid Amount (KES)</Text>
            <TextInput
              style={styles.modalInput}
              keyboardType="numeric"
              value={bidAmount}
              onChangeText={setBidAmount}
            />

            <Text style={styles.modalLabel}>Message / Proposal Note</Text>
            <TextInput
              style={[styles.modalInput, { height: 70 }]}
              multiline
              placeholder="e.g. Available this pm, have experience with similar tasks"
              value={bidMessage}
              onChangeText={setBidMessage}
            />

            <View style={styles.modalBtnRow}>
              <TouchableOpacity
                style={styles.modalCancelBtn}
                onPress={() => setBidModalVisible(false)}>
                <Text style={styles.modalCancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.modalSubmitBtn}
                onPress={handleSubmitBid}>
                <Text style={styles.modalSubmitText}>Submit Bid</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* MODAL 3: Bids Review (Wireframe: Bids.png) */}
      <Modal visible={bidsReviewModalVisible} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={[styles.modalCard, { maxWidth: 560 }]}>
            <Text style={styles.modalTitle}>{activeTask?.title} — KES {activeTask?.posted_price}</Text>
            <Text style={styles.modalSubTitle}>
              Status: <Text style={styles.bold}>{activeTask?.status}</Text> • Bids Received:
            </Text>

            <ScrollView style={{ maxHeight: 300 }}>
              {activeTask?.bids?.length === 0 ? (
                <Text style={styles.emptyText}>No bids submitted yet.</Text>
              ) : (
                activeTask?.bids?.map((bid: any) => (
                  <View key={bid.id} style={styles.bidRow}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.bidStudent}>
                        {bid.student_username} ({bid.student_verification})
                      </Text>
                      <Text style={styles.bidRating}>★ {bid.student_rating || 'New'}</Text>
                      <Text style={styles.bidMsg}>"{bid.message || 'No note'}"</Text>
                    </View>
                    <View style={{ alignItems: 'flex-end', gap: 6 }}>
                      <Text style={styles.bidAmount}>KES {bid.amount}</Text>
                      {activeTask.status in ['Posted', 'Bidding'] && (
                        <TouchableOpacity
                          style={styles.acceptBtn}
                          onPress={() => handleAcceptBid(bid.id)}>
                          <Text style={styles.acceptBtnText}>Accept</Text>
                        </TouchableOpacity>
                      )}
                      {bid.status === 'Accepted' && (
                        <Text style={styles.acceptedTag}>✓ Accepted</Text>
                      )}
                    </View>
                  </View>
                ))
              )}
            </ScrollView>

            <TouchableOpacity
              style={[styles.modalCancelBtn, { marginTop: 14 }]}
              onPress={() => setBidsReviewModalVisible(false)}>
              <Text style={styles.modalCancelText}>Close</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

      {/* MODAL 4: Escrow Confirmation (Wireframe: Escrow.png) */}
      <Modal visible={escrowModalVisible} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>Confirm Payment</Text>
            <Text style={styles.modalSubTitle}>Task: {activeTask?.title}</Text>
            <Text style={styles.escrowAmountText}>Amount: KES {activeTask?.posted_price}</Text>

            <View style={styles.escrowNotice}>
              <Text style={styles.escrowNoticeText}>
                🛡️ Funds will be held safely in escrow until task is marked complete.
              </Text>
            </View>

            <Text style={styles.modalLabel}>Payment Method: [X] M-Pesa</Text>
            <Text style={styles.modalLabel}>M-Pesa Phone Number</Text>
            <TextInput
              style={styles.modalInput}
              keyboardType="phone-pad"
              value={escrowPhone}
              onChangeText={setEscrowPhone}
            />

            <View style={styles.modalBtnRow}>
              <TouchableOpacity
                style={styles.modalCancelBtn}
                onPress={() => setEscrowModalVisible(false)}
                disabled={escrowLoading}>
                <Text style={styles.modalCancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.modalPayBtn}
                onPress={handlePayEscrow}
                disabled={escrowLoading}>
                {escrowLoading ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <Text style={styles.modalSubmitText}>Pay via M-Pesa</Text>
                )}
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* MODAL 5: Chat (Wireframe: Messages.png) */}
      <Modal visible={chatModalVisible} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={[styles.modalCard, { height: 500 }]}>
            <Text style={styles.modalTitle}>Chat: {activeTask?.title}</Text>

            <ScrollView style={styles.chatScroll}>
              {chatMessages.length === 0 ? (
                <Text style={styles.emptyText}>No messages yet. Say hello!</Text>
              ) : (
                chatMessages.map((m) => {
                  const isMine = m.sender === user?.id;
                  return (
                    <View
                      key={m.id}
                      style={[
                        styles.chatBubble,
                        isMine ? styles.chatBubbleMine : styles.chatBubbleTheirs,
                      ]}>
                      <Text style={styles.chatSender}>{m.sender_username}</Text>
                      <Text style={styles.chatText}>{m.content}</Text>
                    </View>
                  );
                })
              )}
            </ScrollView>

            <View style={styles.chatInputRow}>
              <TextInput
                style={styles.chatInput}
                placeholder="Type a message..."
                value={newMsg}
                onChangeText={setNewMsg}
              />
              <TouchableOpacity style={styles.chatSendBtn} onPress={handleSendMessage}>
                <Text style={styles.chatSendBtnText}>Send</Text>
              </TouchableOpacity>
            </View>

            <TouchableOpacity
              style={[styles.modalCancelBtn, { marginTop: 10 }]}
              onPress={() => setChatModalVisible(false)}>
              <Text style={styles.modalCancelText}>Close</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

      {/* MODAL 6: Rating (Wireframe: Ratings.png) */}
      <Modal visible={rateModalVisible} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>Rate Your Experience</Text>
            <Text style={styles.modalSubTitle}>Task: {activeTask?.title}</Text>

            <Text style={styles.modalLabel}>Rating:</Text>
            <View style={styles.starsRow}>
              {[1, 2, 3, 4, 5].map((star) => (
                <TouchableOpacity
                  key={star}
                  onPress={() => setRateScore(star)}
                  style={styles.starBtn}>
                  <Text style={[styles.starIcon, rateScore >= star && styles.starActive]}>
                    ★
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            <Text style={styles.modalLabel}>Comment / Feedback</Text>
            <TextInput
              style={[styles.modalInput, { height: 70 }]}
              multiline
              placeholder="How was the punctuality, communication, and work quality?"
              value={rateComment}
              onChangeText={setRateComment}
            />

            <View style={styles.modalBtnRow}>
              <TouchableOpacity
                style={styles.modalCancelBtn}
                onPress={() => setRateModalVisible(false)}>
                <Text style={styles.modalCancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.modalSubmitBtn}
                onPress={handleSubmitRating}>
                <Text style={styles.modalSubmitText}>Submit Rating</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#F5F6F8',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: '#FFFFFF',
    borderBottomWidth: 1,
    borderBottomColor: '#E1E4E8',
  },
  appTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: '#1F2328',
  },
  appSub: {
    fontSize: 11,
    color: '#656D76',
  },
  userSection: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  userBadge: {
    backgroundColor: '#F6F8FA',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#D0D7DE',
  },
  userName: {
    fontSize: 12,
    fontWeight: '600',
    color: '#1F2328',
  },
  userRole: {
    fontSize: 10,
    color: '#0969DA',
  },
  logoutBtn: {
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  logoutText: {
    color: '#CF222E',
    fontSize: 12,
    fontWeight: '500',
  },
  loginBtn: {
    backgroundColor: '#0969DA',
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 8,
  },
  loginBtnText: {
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '600',
  },
  container: {
    flex: 1,
    padding: 16,
  },
  postTaskBanner: {
    backgroundColor: '#2DA44E',
    borderRadius: 12,
    padding: 14,
    alignItems: 'center',
    marginBottom: 14,
  },
  postTaskBannerText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '700',
  },
  postTaskBannerSub: {
    color: '#E6FFEC',
    fontSize: 11,
    marginTop: 2,
  },
  searchContainer: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 12,
  },
  searchInput: {
    flex: 1,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#D0D7DE',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
    fontSize: 14,
  },
  searchBtn: {
    backgroundColor: '#24292F',
    borderRadius: 8,
    paddingHorizontal: 16,
    justifyContent: 'center',
  },
  searchBtnText: {
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '600',
  },
  categoryScroll: {
    maxHeight: 40,
    marginBottom: 14,
  },
  categoryContent: {
    gap: 8,
  },
  categoryPill: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 20,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#D0D7DE',
  },
  categoryPillActive: {
    backgroundColor: '#0969DA',
    borderColor: '#0969DA',
  },
  categoryPillText: {
    fontSize: 13,
    color: '#57606A',
  },
  categoryPillTextActive: {
    color: '#FFFFFF',
    fontWeight: '600',
  },
  taskList: {
    gap: 12,
    paddingBottom: 24,
  },
  taskCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    padding: 14,
    borderWidth: 1,
    borderColor: '#D0D7DE',
    shadowColor: '#000',
    shadowOpacity: 0.04,
    shadowOffset: { width: 0, height: 2 },
    shadowRadius: 6,
    elevation: 2,
  },
  taskCardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 6,
  },
  taskTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: '#1F2328',
  },
  taskMeta: {
    fontSize: 12,
    color: '#656D76',
    marginTop: 2,
  },
  bold: {
    fontWeight: '600',
    color: '#24292F',
  },
  priceContainer: {
    alignItems: 'flex-end',
  },
  priceAmount: {
    fontSize: 16,
    fontWeight: '700',
    color: '#1A7F37',
  },
  statusBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 12,
    marginTop: 4,
  },
  statusOpen: {
    backgroundColor: '#DDF4FF',
  },
  statusInProgress: {
    backgroundColor: '#FFF8C5',
  },
  statusCompleted: {
    backgroundColor: '#DCFFE4',
  },
  statusText: {
    fontSize: 10,
    fontWeight: '600',
    color: '#1F2328',
  },
  taskDesc: {
    fontSize: 13,
    color: '#57606A',
    marginBottom: 6,
  },
  taskLoc: {
    fontSize: 11,
    color: '#8C959F',
    marginBottom: 10,
  },
  actionRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 4,
  },
  actionButtonPrimary: {
    backgroundColor: '#0969DA',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
  },
  actionButtonPrimaryText: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '600',
  },
  actionButtonSecondary: {
    backgroundColor: '#F6F8FA',
    borderWidth: 1,
    borderColor: '#D0D7DE',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
  },
  actionButtonSecondaryText: {
    color: '#24292F',
    fontSize: 12,
    fontWeight: '600',
  },
  actionButtonSuccess: {
    backgroundColor: '#1F883D',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
  },
  actionButtonSuccessText: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '600',
  },
  actionButtonChat: {
    backgroundColor: '#F3F4F6',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 6,
  },
  actionButtonChatText: {
    color: '#4B5563',
    fontSize: 12,
    fontWeight: '500',
  },
  emptyContainer: {
    alignItems: 'center',
    paddingVertical: 40,
  },
  emptyText: {
    fontSize: 14,
    color: '#656D76',
  },
  emptyAction: {
    color: '#0969DA',
    fontSize: 14,
    fontWeight: '600',
    marginTop: 8,
  },

  // Modal styles
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 16,
  },
  modalCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    padding: 20,
    width: '100%',
    maxWidth: 500,
    shadowColor: '#000',
    shadowOpacity: 0.15,
    shadowOffset: { width: 0, height: 6 },
    shadowRadius: 16,
    elevation: 6,
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#1F2328',
    marginBottom: 4,
  },
  modalSubTitle: {
    fontSize: 13,
    color: '#656D76',
    marginBottom: 12,
  },
  modalLabel: {
    fontSize: 12,
    fontWeight: '600',
    color: '#24292F',
    marginBottom: 4,
    marginTop: 8,
  },
  modalInput: {
    borderWidth: 1,
    borderColor: '#D0D7DE',
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 8,
    fontSize: 14,
    backgroundColor: '#FAFAFA',
  },
  pickerRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginBottom: 8,
  },
  pickerOption: {
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 6,
    backgroundColor: '#F6F8FA',
    borderWidth: 1,
    borderColor: '#D0D7DE',
  },
  pickerOptionActive: {
    backgroundColor: '#DDF4FF',
    borderColor: '#0969DA',
  },
  pickerOptionText: {
    fontSize: 12,
    color: '#57606A',
  },
  pickerOptionTextActive: {
    color: '#0969DA',
    fontWeight: '600',
  },
  guideBanner: {
    backgroundColor: '#FFF8C5',
    borderWidth: 1,
    borderColor: '#D4A72C',
    borderRadius: 8,
    padding: 10,
    marginVertical: 8,
  },
  guideBannerText: {
    fontSize: 12,
    color: '#634700',
    lineHeight: 16,
  },
  modalBtnRow: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 10,
    marginTop: 16,
  },
  modalCancelBtn: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 6,
  },
  modalCancelText: {
    color: '#656D76',
    fontSize: 13,
    fontWeight: '500',
  },
  modalSubmitBtn: {
    backgroundColor: '#0969DA',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 6,
  },
  modalPayBtn: {
    backgroundColor: '#1F883D',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 6,
  },
  modalSubmitText: {
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '600',
  },
  bidRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#E1E4E8',
  },
  bidStudent: {
    fontSize: 13,
    fontWeight: '600',
    color: '#1F2328',
  },
  bidRating: {
    fontSize: 12,
    color: '#D4A72C',
  },
  bidMsg: {
    fontSize: 12,
    color: '#656D76',
    fontStyle: 'italic',
  },
  bidAmount: {
    fontSize: 14,
    fontWeight: '700',
    color: '#1A7F37',
  },
  acceptBtn: {
    backgroundColor: '#1F883D',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 4,
  },
  acceptBtnText: {
    color: '#FFFFFF',
    fontSize: 11,
    fontWeight: '600',
  },
  acceptedTag: {
    color: '#1F883D',
    fontSize: 11,
    fontWeight: '600',
  },
  escrowAmountText: {
    fontSize: 15,
    fontWeight: '700',
    color: '#1A7F37',
    marginBottom: 8,
  },
  escrowNotice: {
    backgroundColor: '#DDF4FF',
    padding: 10,
    borderRadius: 8,
    marginBottom: 10,
  },
  escrowNoticeText: {
    fontSize: 12,
    color: '#0969DA',
  },
  chatScroll: {
    flex: 1,
    marginVertical: 10,
    paddingHorizontal: 4,
  },
  chatBubble: {
    maxWidth: '80%',
    padding: 10,
    borderRadius: 10,
    marginBottom: 8,
  },
  chatBubbleMine: {
    alignSelf: 'flex-end',
    backgroundColor: '#DDF4FF',
  },
  chatBubbleTheirs: {
    alignSelf: 'flex-start',
    backgroundColor: '#F6F8FA',
    borderWidth: 1,
    borderColor: '#E1E4E8',
  },
  chatSender: {
    fontSize: 10,
    fontWeight: '600',
    color: '#656D76',
    marginBottom: 2,
  },
  chatText: {
    fontSize: 13,
    color: '#1F2328',
  },
  chatInputRow: {
    flexDirection: 'row',
    gap: 8,
  },
  chatInput: {
    flex: 1,
    borderWidth: 1,
    borderColor: '#D0D7DE',
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 8,
    fontSize: 13,
  },
  chatSendBtn: {
    backgroundColor: '#0969DA',
    borderRadius: 8,
    paddingHorizontal: 14,
    justifyContent: 'center',
  },
  chatSendBtnText: {
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '600',
  },
  starsRow: {
    flexDirection: 'row',
    gap: 8,
    marginVertical: 8,
  },
  starBtn: {
    padding: 4,
  },
  starIcon: {
    fontSize: 28,
    color: '#D0D7DE',
  },
  starActive: {
    color: '#D4A72C',
  },
});
