import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Ellipse

OUT = r"c:\Users\Admin\Documents\DAVE\IS2\IS project\docs\images\UseCase_Diagram.png"

fig, ax = plt.subplots(figsize=(26, 22))
ax.set_xlim(0, 26); ax.set_ylim(0, 22); ax.axis('off')
fig.patch.set_facecolor('white')

def pkg(x,y,w,h,label,color):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle="round,pad=0.1",
        lw=1.3,edgecolor='#555',facecolor=color,zorder=2))
    ax.text(x+0.15,y+h-0.18,label,fontsize=9,fontweight='bold',
            color='#111',va='top',zorder=3)

def uc(x,y,w,h,label,fs=7.8):
    ax.add_patch(Ellipse((x,y),width=w,height=h,lw=1.0,
        edgecolor='#2980B9',facecolor='#EBF5FB',zorder=4))
    ax.text(x,y,label,ha='center',va='center',fontsize=fs,
            zorder=5,multialignment='center')
    return (x,y)

def actor(x,y,label,color,fs=8.5):
    # Compact actor — total height ~1.1 units
    ax.add_patch(plt.Circle((x,y+0.32),0.16,color=color,zorder=6))
    ax.plot([x,x],[y+0.16,y-0.18],color=color,lw=1.6,zorder=6)
    ax.plot([x-0.22,x+0.22],[y+0.0,y+0.0],color=color,lw=1.6,zorder=6)
    ax.plot([x,x-0.18],[y-0.18,y-0.50],color=color,lw=1.6,zorder=6)
    ax.plot([x,x+0.18],[y-0.18,y-0.50],color=color,lw=1.6,zorder=6)
    ax.text(x,y-0.65,label,ha='center',va='top',fontsize=fs,
            fontweight='bold',color='#111',zorder=6,multialignment='center')

def assoc(x1,y1,x2,y2,color,lw=0.75):
    ax.annotate('',xy=(x2,y2),xytext=(x1,y1),
        arrowprops=dict(arrowstyle='->',color=color,lw=lw),zorder=1)

def inc(x1,y1,x2,y2,label=''):
    ax.annotate('',xy=(x2,y2),xytext=(x1,y1),
        arrowprops=dict(arrowstyle='->',color='#666',lw=0.85,
                        linestyle='dashed'),zorder=1)
    if label:
        mx,my=(x1+x2)/2,(y1+y2)/2
        ax.text(mx+0.05,my,label,fontsize=6.5,color='#444',
                ha='left',va='center',style='italic',zorder=5)

# ─── TITLE ───────────────────────────────────────────────────────────────────
ax.text(13,21.7,'UniTask — Domestic Job & Escrow Platform',
        ha='center',fontsize=14,fontweight='bold')
ax.text(13,21.25,'Use Case Diagram',ha='center',fontsize=10.5,color='#444')

# ─── SYSTEM BOUNDARY — contains everything including Scheduler ───────────────
ax.add_patch(FancyBboxPatch((2.0,1.0),22.0,19.8,
    boxstyle="round,pad=0.1",lw=2,edgecolor='#2C3E50',
    facecolor='#FAFAFA',zorder=0))
ax.text(2.2,20.7,'UniTask System Boundary',fontsize=7.5,color='#2C3E50',style='italic')

# ─── ROW 1: Auth & Profile ───────────────────────────────────────────────────
pkg(5.5,17.8,15.0,2.5,'Authentication & Profile','#EAF4FB')
p_reg  = uc(7.5,  19.6,2.5,0.42,'Register Account')
p_log  = uc(11.0, 19.6,1.8,0.42,'Login')
p_prof = uc(14.5, 19.6,2.6,0.42,'View & Edit Profile')
p_rat  = uc(7.5,  18.6,2.5,0.42,'View My Ratings')
p_pay  = uc(11.0, 18.6,2.8,0.42,'View Payment History')
p_cons = uc(14.9, 18.6,2.6,0.42,'Accept Location\nConsent',7.2)

# ─── ROW 2 LEFT: Household tasks ─────────────────────────────────────────────
pkg(2.3,11.5,10.0,6.0,'Task Management (Household)','#EAFAF1')
h_post = uc(4.0,  16.8,2.5,0.42,'Post New Task')
h_view = uc(8.0,  16.8,2.5,0.42,'View My Tasks')
h_conf = uc(4.0,  15.9,2.7,0.42,'Confirm Match\n& Pay Escrow',7.2)
h_code = uc(8.0,  15.9,2.3,0.42,'View Start Code')
h_done = uc(4.0,  15.0,2.7,0.42,'Confirm Work\nComplete',7.2)
h_disp = uc(8.0,  15.0,2.3,0.42,'Raise Dispute')
h_canc = uc(4.0,  14.1,2.3,0.42,'Cancel Task')
h_blk  = uc(8.0,  14.1,2.5,0.42,'Block / Unblock\nStudent',7.2)
h_rate = uc(5.8,  12.3,2.3,0.42,'Rate Student')

# ─── ROW 2 RIGHT: Student tasks ──────────────────────────────────────────────
pkg(14.0,11.5,10.0,6.0,'Task Management (Student)','#FEF9E7')
s_inbox= uc(15.5, 16.8,2.6,0.42,'View Available\nTasks (Inbox)',7.2)
s_acc  = uc(19.5, 16.8,2.2,0.42,'Accept Task')
s_dec  = uc(15.5, 15.9,2.5,0.42,'Decline /\nIgnore Task',7.2)
s_ci   = uc(19.5, 15.9,2.4,0.42,'Check In\n(Code + GPS)',7.2)
s_fin  = uc(15.5, 15.0,2.4,0.42,'Mark Work\nFinished',7.2)
s_resp = uc(19.5, 15.0,2.4,0.42,'Respond\nto Dispute',7.2)
s_canc = uc(15.5, 14.1,2.6,0.42,'Cancel Accepted\nTask',7.2)
s_rate = uc(19.5, 14.1,2.2,0.42,'Rate Household')
s_vmyt = uc(17.5, 12.3,2.2,0.42,'View My Tasks')

# ─── ROW 3 LEFT: Payments ────────────────────────────────────────────────────
pkg(2.3, 6.5,10.0,4.7,'Payments & Escrow','#FDF2E9')
py_stk = uc(4.0,  10.5,2.7,0.42,'Initiate M-Pesa\nSTK Push',7.2)
py_cb  = uc(8.2,  10.5,2.5,0.42,'Process Payment\nCallback',7.2)
py_hld = uc(4.0,   9.6,2.5,0.42,'Hold Funds\nin Escrow',7.2)
py_rel = uc(8.2,   9.6,2.6,0.42,'Release Escrow\nto Student',7.2)
py_ref = uc(5.8,   7.8,2.7,0.42,'Refund Escrow\nto Household',7.2)

# ─── ROW 3 RIGHT: Administration ─────────────────────────────────────────────
pkg(14.0, 6.5,10.0,4.7,'Administration','#FDEDEC')
a_ver  = uc(15.5, 10.5,2.6,0.42,'Verify Student\nAccount',7.2)
a_res  = uc(19.5, 10.5,2.4,0.42,'Resolve Dispute')
a_map  = uc(15.5,  9.6,2.6,0.42,'View Location\nAudit Map',7.2)
a_pol  = uc(19.5,  9.6,2.5,0.42,'Manage Platform\nPolicies',7.2)
a_log  = uc(17.5,  7.8,2.3,0.42,'View Audit Logs')

# ─── ROW 4: Automated Jobs — full width, all UCs, Scheduler on left edge ──────
pkg(2.3, 1.1,22.0,2.8,'Automated Jobs (Scheduler)','#F5EEF8')

# Use cases fill the package — two rows, left-to-right
sc_bc  = uc(5.5,  3.2,2.6,0.42,'Broadcast Task\nto Students',7.2)
sc_ns  = uc(9.0,  3.2,2.5,0.42,'Detect No-Show\n(30 min)',7.2)
sc_ar  = uc(12.5, 3.2,2.6,0.42,'Auto-Release\nEscrow (48h)',7.2)
sc_rem = uc(16.5, 3.2,2.8,0.42,'Send Confirmation\nReminders',7.2)
sc_rb  = uc(5.5,  2.0,2.7,0.42,'Re-broadcast\nStale Tasks',7.2)
sc_an  = uc(9.0,  2.0,2.7,0.42,'Anonymise\nLocation Data',7.2)
sc_post= uc(12.5, 2.0,2.5,0.42,'Detect Stale\nBroadcasts',7.2)

# Scheduler actor sits just inside the LEFT of the Automated Jobs package
actor(3.0, 2.6,'Scheduler\n(Cron)','#6C3483',8.0)

# ─── LEFT ACTORS: Household (mid-left), M-Pesa (lower-left) ─────────────────
actor(0.8, 16.0,'Household\nOwner','#1A8449')
actor(0.8,  9.5,'M-Pesa\n(Safaricom)','#D35400')

# ─── RIGHT ACTORS: Student (mid-right), Administrator (lower-right) ──────────
actor(25.2,16.0,'Student','#1A5276')
actor(25.2, 9.5,'Administrator','#884EA0')

# ─── HOUSEHOLD → use cases ───────────────────────────────────────────────────
hx = 1.4
# → auth (selected key ones)
for p in [p_reg, p_rat, p_pay]:
    assoc(hx,16.5, p[0]-1.3,p[1], '#1A8449', 0.65)
# → HH tasks package left edge
for p in [h_post, h_conf, h_done, h_canc, h_rate]:
    assoc(hx,15.5, p[0]-1.7,p[1], '#1A8449', 0.65)

# ─── STUDENT → use cases ─────────────────────────────────────────────────────
sx = 24.6
for p in [p_log, p_prof, p_cons]:
    assoc(sx,16.5, p[0]+1.3,p[1], '#1A5276', 0.65)
for p in [s_inbox, s_ci, s_fin, s_rate, s_vmyt]:
    assoc(sx,15.5, p[0]+1.3,p[1], '#1A5276', 0.65)

# ─── M-PESA (from outside left) ──────────────────────────────────────────────
assoc(1.4,10.0, py_stk[0]-1.35,py_stk[1], '#D35400', 1.0)
ax.text(0.5,10.3,'STK\nPush',fontsize=6.5,color='#D35400',style='italic',ha='center')
assoc(py_cb[0]-1.3,py_cb[1], 1.4,9.8, '#D35400', 1.0)
ax.text(0.5,9.5,'Callback',fontsize=6.5,color='#D35400',style='italic',ha='center')

# ─── ADMIN → administration ──────────────────────────────────────────────────
for p in [a_ver, a_res, a_map, a_pol, a_log]:
    assoc(24.6,9.5, p[0]+1.3,p[1], '#884EA0', 0.65)

# ─── SCHEDULER → automated jobs ──────────────────────────────────────────────
sc_x, sc_y = 3.6, 2.9
for p in [sc_bc,sc_ns,sc_ar,sc_rem,sc_rb,sc_an,sc_post]:
    assoc(sc_x,sc_y, p[0]-1.3,p[1], '#6C3483', 0.65)

# ─── INCLUDE / EXTEND (keep only within-package or short cross-package arrows)
# Confirm match → initiate STK Push
inc(h_conf[0]+0.1,h_conf[1]-0.22, py_stk[0]+0.1,py_stk[1]+0.22,'')
# STK Push → Hold in Escrow
inc(py_stk[0]+0.4,py_stk[1]-0.22, py_hld[0]+0.3,py_hld[1]+0.22,'<<include>>')
# Callback → Hold in Escrow
inc(py_cb[0]-0.1,py_cb[1]-0.22,   py_hld[0]+0.9,py_hld[1]+0.22,'')
# Confirm work → Release escrow
inc(h_done[0]+0.3,h_done[1]-0.22, py_rel[0]-0.2,py_rel[1]+0.22,'')
# Check In → Accept Location Consent
inc(s_ci[0]-0.3,s_ci[1]-0.22,     p_cons[0]+0.3,p_cons[1]-0.22,'<<include>>')
# Resolve Dispute → View Location Audit Map
inc(a_res[0]-0.5,a_res[1]-0.22,   a_map[0]+0.5, a_map[1]+0.22,'<<include>>')
# Auto-Release → Release Escrow
inc(sc_ar[0],sc_ar[1]+0.22,       py_rel[0]+0.5,py_rel[1]-0.22,'')
# Detect No-Show → Refund Escrow
inc(sc_ns[0]+0.1,sc_ns[1]+0.22,   py_ref[0]-0.2,py_ref[1]-0.22,'<<extend>>')

# ─── LEGEND ──────────────────────────────────────────────────────────────────
lx,ly = 20.0,6.2
ax.add_patch(FancyBboxPatch((lx-0.3,ly-2.1),4.0,2.4,
    boxstyle="round,pad=0.1",lw=1,edgecolor='#aaa',facecolor='#fff',zorder=7))
ax.text(lx,ly,'Legend',fontsize=9,fontweight='bold',color='#111',zorder=8)
ax.annotate('',xy=(lx+1.6,ly-0.5),xytext=(lx+0.6,ly-0.5),
    arrowprops=dict(arrowstyle='->',color='#2C3E50',lw=1.1),zorder=8)
ax.text(lx+1.8,ly-0.5,'= Association',fontsize=7.5,va='center',zorder=8)
ax.annotate('',xy=(lx+1.6,ly-1.0),xytext=(lx+0.6,ly-1.0),
    arrowprops=dict(arrowstyle='->',color='#666',lw=1.0,linestyle='dashed'),zorder=8)
ax.text(lx+1.8,ly-1.0,'= <<include>> / <<extend>>',fontsize=7.5,va='center',zorder=8)
ax.add_patch(Ellipse((lx+1.1,ly-1.6),1.1,0.38,lw=1.0,
    edgecolor='#2980B9',facecolor='#EBF5FB',zorder=8))
ax.text(lx+1.1,ly-1.6,'Use Case',fontsize=7,ha='center',va='center',zorder=9)
ax.text(lx+1.8,ly-1.6,'= Use Case Ellipse',fontsize=7.5,va='center',zorder=8)

plt.tight_layout(pad=0.3)
plt.savefig(OUT,dpi=180,bbox_inches='tight',facecolor='white',edgecolor='none')
plt.close()
print('Saved:', OUT)
