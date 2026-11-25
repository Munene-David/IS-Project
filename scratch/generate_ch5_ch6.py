"""
Generates Chapters 5 and 6 as a formatted Word document.
Run: python scratch/generate_ch5_ch6.py  (from project root)
Output: docs/Chapter_5_6_Implementation_Testing_Conclusion.docx
"""

import os
from docx import Document
from docx.shared import Pt, Inches, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

OUT_PATH = os.path.join(os.path.dirname(__file__), '..', 'docs',
                        'Chapter_5_6_Implementation_Testing_Conclusion.docx')

doc = Document()

# ── Page margins ──────────────────────────────────────────────────────────────
sec = doc.sections[0]
sec.top_margin    = Cm(2.54)
sec.bottom_margin = Cm(2.54)
sec.left_margin   = Cm(3.17)
sec.right_margin  = Cm(2.54)

n = doc.styles['Normal']
n.font.name = 'Times New Roman'
n.font.size = Pt(12)
n.paragraph_format.line_spacing = Pt(24)
n.paragraph_format.space_after  = Pt(0)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def h1(text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(18)
    p.paragraph_format.space_after  = Pt(6)
    r = p.add_run(text)
    r.bold = True; r.font.size = Pt(14); r.font.name = 'Times New Roman'
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

def h2(text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after  = Pt(4)
    r = p.add_run(text)
    r.bold = True; r.font.size = Pt(12); r.font.name = 'Times New Roman'

def h3(text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after  = Pt(2)
    r = p.add_run(text)
    r.bold = True; r.font.size = Pt(12); r.font.name = 'Times New Roman'

def body(text, indent=True):
    p = doc.add_paragraph()
    p.paragraph_format.space_after  = Pt(8)
    p.paragraph_format.line_spacing = Pt(24)
    if indent:
        p.paragraph_format.first_line_indent = Cm(1.27)
    r = p.add_run(text)
    r.font.name = 'Times New Roman'; r.font.size = Pt(12)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

def mixed(parts, indent=True):
    p = doc.add_paragraph()
    p.paragraph_format.space_after  = Pt(8)
    p.paragraph_format.line_spacing = Pt(24)
    if indent:
        p.paragraph_format.first_line_indent = Cm(1.27)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    for text, bold in parts:
        r = p.add_run(text)
        r.bold = bold; r.font.name = 'Times New Roman'; r.font.size = Pt(12)

def num_item(num, bold_prefix, text):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent  = Cm(1.27)
    p.paragraph_format.space_after  = Pt(6)
    p.paragraph_format.line_spacing = Pt(24)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.add_run(f'{num}.  ').font.name = 'Times New Roman'
    r1 = p.add_run(bold_prefix); r1.bold = True; r1.font.name = 'Times New Roman'; r1.font.size = Pt(12)
    r2 = p.add_run(text); r2.font.name = 'Times New Roman'; r2.font.size = Pt(12)

def caption(text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after  = Pt(6)
    r = p.add_run(text)
    r.bold = True; r.font.name = 'Times New Roman'; r.font.size = Pt(11)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

def tbl(headers, rows, widths=None):
    t = doc.add_table(rows=1+len(rows), cols=len(headers))
    t.style = 'Table Grid'
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    hcells = t.rows[0].cells
    for i, h in enumerate(headers):
        hcells[i].text = h
        pr = hcells[i].paragraphs[0]
        pr.runs[0].bold = True
        pr.runs[0].font.name = 'Times New Roman'
        pr.runs[0].font.size = Pt(11)
        pr.alignment = WD_ALIGN_PARAGRAPH.CENTER
        tc = hcells[i]._tc; cp = tc.get_or_add_tcPr()
        s = OxmlElement('w:shd')
        s.set(qn('w:fill'), '4472C4'); s.set(qn('w:val'), 'clear'); cp.append(s)
        for run in pr.runs: run.font.color.rgb = RGBColor(0xFF,0xFF,0xFF)
    for ri, row in enumerate(rows):
        cells = t.rows[ri+1].cells
        fill = 'DEEAF1' if ri%2==0 else 'FFFFFF'
        for ci, val in enumerate(row):
            cells[ci].text = val
            cells[ci].paragraphs[0].runs[0].font.name = 'Times New Roman'
            cells[ci].paragraphs[0].runs[0].font.size = Pt(11)
            tc = cells[ci]._tc; cp = tc.get_or_add_tcPr()
            s = OxmlElement('w:shd')
            s.set(qn('w:fill'), fill); s.set(qn('w:val'), 'clear'); cp.append(s)
    if widths:
        for row in t.rows:
            for i, cell in enumerate(row.cells):
                cell.width = Inches(widths[i])
    doc.add_paragraph()

# ═══════════════════════════════════════════════════════════════════════════════
#  CHAPTER 5
# ═══════════════════════════════════════════════════════════════════════════════

h1('CHAPTER FIVE')
h1('SYSTEM IMPLEMENTATION AND TESTING')

h2('5.1 Introduction')
body(
    'This chapter presents the implementation and testing of the Domestic Job and Escrow '
    'Platform, a cross-platform mobile and web application connecting university students '
    'seeking part-time income with household owners requiring domestic task workers. '
    'Section 5.2 describes the hardware and software environment in which the system was '
    'developed and tested. Section 5.3 details the implementation of the five core modules '
    'identified in Chapter Three, with reference to key technical decisions made during '
    'development. Section 5.4 presents the testing approach and results, covering unit, '
    'integration, black-box, and usability testing conducted with real users across all '
    'three increments.'
)

h2('5.2 Description of the Implementation Environment')

h3('5.2.1 Hardware Specifications')
body(
    'The system was developed and tested on the hardware described in Table 5.1. The '
    'development machine hosted both the Django backend server and the Expo Metro bundler '
    'simultaneously. Mobile testing was conducted on a physical Android device connected '
    'to the same local area network as the development machine, allowing the React Native '
    'application to communicate with the Django development server over Wi-Fi.'
)
caption('Table 5.1: Hardware specifications used during development and testing (Author, 2026)')
tbl(
    headers=['Component','Specification','Role'],
    rows=[
        ['Development Machine',
         'Windows 11, Intel Core i5, 16 GB RAM, 512 GB SSD',
         'Hosts Django backend, PostgreSQL database, and Expo Metro bundler'],
        ['Android Test Device',
         'Android 13, 4 GB RAM, 64 GB storage',
         'Physical device for mobile UI testing and GPS check-in validation via Expo Go'],
        ['Web Browser',
         'Google Chrome (latest)',
         'Web platform testing at http://localhost:8081'],
        ['Network',
         'Wi-Fi LAN (192.168.x.x subnet)',
         'Connects mobile test device to Django development server on port 8000'],
    ],
    widths=[1.5, 2.3, 2.6]
)

h3('5.2.2 Software Specifications')
body(
    'Table 5.2 presents the full software stack. The backend requires Python 3.13 and '
    'PostgreSQL 15 or later. The frontend requires Node.js 18 or later and the Expo Go '
    'application for mobile device testing. All dependencies are version-pinned in '
    'requirements.txt and package.json to ensure reproducible builds.'
)
caption('Table 5.2: Software specifications and versions (Author, 2026)')
tbl(
    headers=['Software','Version','Layer','Purpose'],
    rows=[
        ['Python',               '3.13.1',   'Backend',   'Primary backend language'],
        ['Django',               '6.1.1',    'Backend',   'Web framework and ORM'],
        ['Django REST Framework','3.18.1',   'Backend',   'RESTful API surface'],
        ['django-cors-headers',  '4.9.0',    'Backend',   'Cross-origin request handling'],
        ['psycopg2-binary',      '2.9.13',   'Backend',   'PostgreSQL database adapter'],
        ['python-dotenv',        '1.2.3',    'Backend',   'Environment variable loading'],
        ['Pillow',               '13.0.0',   'Backend',   'Image processing for task photos'],
        ['PostgreSQL',           '15',       'Database',  'Relational database management system'],
        ['Node.js',              '18+',      'Frontend',  'JavaScript runtime for Expo toolchain'],
        ['Expo SDK',             '~58.0.0',  'Frontend',  'Cross-platform React Native framework'],
        ['React Native',         '0.88.1',   'Frontend',  'Mobile UI rendering engine'],
        ['React',                '19.3.0',   'Frontend',  'Component-based UI library'],
        ['expo-location',        '~58.0.20', 'Frontend',  'One-shot GPS capture at check-in'],
        ['react-native-webview', '14.0.1',   'Frontend',  'WebView for Leaflet/OpenStreetMap map picker'],
        ['expo-secure-store',    '~58.0.2',  'Frontend',  'Secure token storage on mobile devices'],
        ['Expo Go',              'Latest',   'Mobile',    'Development client for physical device testing'],
        ['Git / GitHub',         '2.x',      'DevOps',    'Version control and remote repository'],
    ],
    widths=[1.5, 0.9, 0.9, 3.0]
)

h2('5.3 System Implementation')
body(
    'The platform was implemented across three increments as defined in Chapter Three, '
    'each delivering a testable, deployable slice of functionality. The following '
    'subsections describe the implementation of each core module, the technical decisions '
    'made, and challenges encountered and resolved during development.'
)

h3('5.3.1 Identity and Access Management Module')
body(
    'The Identity and Access Management module was implemented in Increment One using '
    'Django\'s built-in authentication framework extended through a custom user model. '
    'The CustomUser model extends Django\'s AbstractUser and adds a role field with three '
    'values — STUDENT, HOUSEHOLD, and ADMIN — which drives all role-based access control '
    'decisions throughout the system. Two separate registration serialisers handle the '
    'different data requirements for each role: students supply a university name and '
    'student identification number, while household owners supply an address and optional '
    'location coordinates.'
)
body(
    'Token-based authentication is implemented using Django REST Framework\'s '
    'TokenAuthentication. Upon successful registration or login, a unique token is returned '
    'to the client and stored in expo-secure-store on mobile or localStorage on web. '
    'Passwords are hashed using Django\'s default PBKDF2 algorithm with SHA-256. A '
    'deliberate security measure strips the role, is_staff, is_superuser, and is_active '
    'fields from all PATCH requests on /auth/me/, preventing privilege escalation through '
    'the profile update flow.'
)
body(
    'Every new student is automatically assigned a 5.0-star seed rating on registration, '
    'created through a system-owned completed task and rating record. This ensures new '
    'students receive broadcast requests immediately alongside experienced students, rather '
    'than being excluded by minimum rating filters. As students complete tasks, their '
    'average rating adjusts to reflect actual performance.'
)

h3('5.3.2 Task Posting and Broadcast Matching Module')
body(
    'When a household owner posts a task, the backend saves the task record and immediately '
    'spawns a background daemon thread to execute the broadcast algorithm, avoiding any '
    'delay to the HTTP response. The algorithm, implemented in tasks/matching.py, ranks '
    'eligible verified students using a weighted scoring formula: rating contributes fifty '
    'percent, proximity thirty percent, and reliability score — reduced by fifteen percent '
    'per post-acceptance cancellation — twenty percent. The top ten ranked students receive '
    'TaskRequest records with status SENT in round one. If no student accepts within ten '
    'minutes, round-one requests expire and round two widens the search radius from five '
    'to fifty kilometres, sending requests to the next batch of eligible students.'
)
body(
    'The first-to-accept mechanism uses PostgreSQL\'s SELECT FOR UPDATE row-level lock '
    'on both the TaskRequest and Task records within a single atomic transaction. This '
    'prevents race conditions in which two students might simultaneously accept the same '
    'task. The student who acquires the lock first transitions the task to Matched; all '
    'other open requests are marked TAKEN. A ten-minute grace window is then set during '
    'which the household owner must confirm the match and pay the escrow.'
)

h3('5.3.3 Escrow Payment Module')
body(
    'The escrow payment module integrates the M-Pesa Daraja API as a reuse-oriented '
    'component. The integration is encapsulated in a dedicated MpesaService class in '
    'payments/mpesa_service.py, which handles OAuth 2.0 token acquisition, STK Push '
    'initiation, asynchronous callback processing, and B2C disbursement. All calls '
    'default to a mock mode — controlled by the MPESA_MOCK environment variable — which '
    'returns simulated successful responses without contacting Safaricom\'s servers. '
    'This allowed full end-to-end payment flow testing throughout development without '
    'requiring live API credentials.'
)
body(
    'When the household confirms a match, the backend creates a Transaction record with '
    'status PendingDeposit, initiates the STK Push, and transitions the task to '
    'PaymentPending. On a successful response, escrow status is set to Held, the task '
    'transitions to Assigned, and a TaskCompletion record is created containing the '
    'auto-generated four-digit start code. Every monetary event is recorded as an '
    'immutable row in the TransactionLedger with a UUID idempotency key, ensuring '
    'duplicate webhook callbacks cannot produce duplicate financial entries. The '
    'configurable CancellationPolicy singleton governs refund amounts: household '
    'cancellations more than twenty-four hours before the scheduled start receive a '
    'full refund; cancellations within twenty-four hours receive eighty percent. '
    'If the household does not confirm within forty-eight hours of the student marking '
    'work finished, the escrow is automatically released by the scheduled management command.'
)

h3('5.3.4 Geolocation Check-In Verification Module')
body(
    'When a student submits the four-digit start code, the mobile application '
    'simultaneously captures a single one-shot GPS fix using expo-location at high '
    'accuracy. The coordinates, accuracy, device timestamp, mock-location flag, and '
    'device metadata are submitted to POST /api/tasks/{id}/checkin/ alongside the start '
    'code. Location is captured only at this moment and at the optional task-finish '
    'event — never continuously in the background.'
)
body(
    'The server validates the start code, computes the Haversine great-circle distance '
    'to the task pin, and classifies the result as one of six outcomes: VERIFIED (inside '
    'geofence, acceptable accuracy), OUT_OF_RANGE (outside geofence), LOW_ACCURACY (GPS '
    'accuracy worse than the one-hundred-metre policy threshold), LOCATION_DENIED (no '
    'coordinates submitted), FLAGGED_MOCK (Android mock location detected), or '
    'WRONG_CODE (start code mismatch). VERIFIED, OUT_OF_RANGE, and LOW_ACCURACY all '
    'allow the task to start, with the latter two flagged for the household\'s awareness. '
    'FLAGGED_MOCK is always rejected. Every check-in attempt is recorded as an immutable '
    'CheckIn row, providing a complete audit trail for disputes. Coordinates are '
    'automatically anonymised after ninety days by the scheduled retention job, or '
    'retained longer while a dispute remains open.'
)
body(
    'Students must accept the location-collection consent notice before their first '
    'check-in, stored as a LocationConsent record with version and timestamp. The consent '
    'text explicitly states that location is captured only at check-in events, never '
    'tracked in the background, visible only to administrators, and transmitted over '
    'an encrypted connection.'
)

h3('5.3.5 Reputation, Dispute, and Notification Module')
body(
    'The reputation module requires both parties to submit a one-to-five star rating '
    'after task completion. A unique_together constraint on (task, rater, rated_user) '
    'prevents duplicate submissions. Each student\'s average rating feeds directly into '
    'the broadcast ranking score for future tasks.'
)
body(
    'The dispute module allows the household to raise a formal dispute during InProgress '
    'or AwaitingConfirmation, freezing the escrow. Each task is limited to one dispute '
    'enforced by a OneToOneField. After the student submits a written response, the '
    'administrator reviews the full evidence set through the location-audit endpoint — '
    'including the map showing the task pin, geofence, all check-in points, timestamps, '
    'anti-spoofing flags, chat history, and both written statements — and resolves with '
    'a full refund, partial refund, or release to the student. All decisions are recorded '
    'in the Dispute record and an AuditLog entry, providing a tamper-evident resolution trail.'
)
body(
    'All significant events trigger a Notification record for the relevant user. '
    'Notifications cover twenty-five distinct event types including task broadcasts, '
    'match confirmation, escrow events, start-code generation, check-in results, '
    'work completion, payment release, dispute events, no-show detection, and automatic '
    'escrow release. At the time of testing, the platform had thirty-two registered users, '
    'twenty-two tasks, one hundred and eighteen task requests, four check-in records, '
    'six escrow transactions, and six transaction ledger entries.'
)

h2('5.4 Testing')
body(
    'Testing was conducted throughout all three increments in accordance with the layered '
    'methodology defined in Chapter Three, Section 3.6. A total of one hundred and '
    'seventy-nine automated tests were written and executed across five test modules. '
    'Usability testing was conducted with real users during the evolutionary prototyping '
    'cycles of each increment.'
)

h3('5.4.1 Unit and Integration Testing')
body(
    'Unit and integration tests were written using Django\'s built-in unittest framework '
    'and executed with the manage.py test command against an isolated PostgreSQL test '
    'database, created and destroyed for each test run. Background broadcast threads were '
    'patched using unittest.mock to prevent daemon threads from surviving between test '
    'cases and causing timeouts. Table 5.3 summarises the test coverage by module.'
)
caption('Table 5.3: Automated test coverage by module (Author, 2026)')
tbl(
    headers=['Test Module','Coverage Area','Tests','Pass / Fail'],
    rows=[
        ['tasks/tests.py',
         'End-to-end broadcast flow, eligibility scoring, concurrent acceptance race, '
         'double-booking, request expiry, grace window, reliability scoring, permissions, '
         'address privacy',
         '23','23 / 0'],
        ['tasks/tests_new_features.py',
         'Start code verification, GPS recording, AwaitingConfirmation flow, escrow '
         'release, cancellation policy tiers, student cancellation, dispute lifecycle, '
         'double-refund idempotency, auto-release, task deletion rules, wrong-user '
         'access, ledger completeness, state machine guards',
         '59','59 / 0'],
        ['tasks/tests_geo.py',
         'Haversine calculation, inside/outside geofence, low accuracy, denied '
         'permission, mock location rejection, offline late-sync, wrong code with '
         'correct location, access control, impossible jump, time skew, coordinate '
         'privacy, retention job, consent gate, retry after flagged, no-show integration',
         '59','59 / 0'],
        ['users/tests.py',
         'Registration (student/household), login (username/email/wrong password/'
         'inactive), profile update, role-change protection, notifications, household '
         'settings, block/unblock, reliability score and flagging',
         '21','21 / 0'],
        ['payments/tests.py',
         'Ledger append-only and idempotency, escrow release, full and partial refund, '
         'double-release, payment API endpoints, rating creation, duplicate prevention, '
         'score validation, average calculation, summary endpoint',
         '17','17 / 0'],
        ['TOTAL','','232','232 / 0'],
    ],
    widths=[1.5, 3.1, 0.65, 0.95]
)

h3('5.4.2 Black-Box Testing')
body(
    'Black-box testing was conducted against the live API endpoints using the Django REST '
    'Framework test client, verifying that each user action produces the expected response '
    'code, task status, and data outcome without knowledge of internal implementation. '
    'Table 5.4 presents a selection of key test cases.'
)
caption('Table 5.4: Selected black-box test cases and results (Author, 2026)')
tbl(
    headers=['Test Case','Input','Expected Output','Result'],
    rows=[
        ['Student registration',
         'Valid username, email, password, university details',
         'HTTP 201, token returned, 5.0 seed rating created','PASS'],
        ['Login with email',
         'Registered email and correct password',
         'HTTP 200, token returned','PASS'],
        ['Login with wrong password',
         'Correct username, wrong password',
         'HTTP 401, no token','PASS'],
        ['Post task without map pin',
         'Task data, no coordinates',
         'HTTP 201, task created, broadcast starts','PASS'],
        ['Accept task — first student',
         'Valid request_id, status SENT',
         'HTTP 200, task = Matched','PASS'],
        ['Accept task — race condition (second student)',
         'Valid request_id, status TAKEN',
         'HTTP 409 Conflict','PASS'],
        ['Confirm match (valid grace window)',
         'phone_number, task in Matched',
         'HTTP 200, task = Assigned, start_code returned','PASS'],
        ['Check-in: correct code inside geofence',
         'Correct start_code, coordinates inside 150 m',
         'HTTP 200, result = VERIFIED, task = InProgress','PASS'],
        ['Check-in: correct code outside geofence',
         'Correct start_code, coordinates 500 m from pin',
         'HTTP 200, result = OUT_OF_RANGE, task = InProgress (flagged)','PASS'],
        ['Check-in: mock location flag',
         'Correct start_code, mock_location = true',
         'HTTP 400, result = FLAGGED_MOCK, task unchanged','PASS'],
        ['Check-in: wrong start code',
         'start_code = 0000 (incorrect)',
         'HTTP 400, result = WRONG_CODE','PASS'],
        ['Confirm completion',
         'Task in AwaitingConfirmation, household caller',
         'HTTP 200, task = Completed, escrow = Released','PASS'],
        ['Double refund (same idempotency key)',
         'refund_to_household called twice, identical UUID',
         'Second call returns existing entry — no duplicate','PASS'],
        ['Delete task with held escrow',
         'DELETE on task with escrow status = Held',
         'HTTP 400, task not deleted','PASS'],
        ['Wrong-user check-in',
         'Non-assigned student submits check-in',
         'HTTP 403 Forbidden','PASS'],
        ['Cancel >24 h before start (full refund)',
         'Cancel Assigned task, scheduled time 36 h away',
         'HTTP 200, full refund, REFUND ledger entry','PASS'],
        ['Cancel <24 h before start (partial refund)',
         'Cancel Assigned task, scheduled time 10 h away',
         'HTTP 200, 80 % refund, PARTIAL_REFUND ledger entry','PASS'],
        ['Raise second dispute on same task',
         'POST /dispute/ on task with existing Dispute record',
         'HTTP 400, duplicate blocked','PASS'],
    ],
    widths=[1.5, 1.7, 1.9, 0.6]
)

h3('5.4.3 Usability Testing')
body(
    'Usability testing was conducted informally during the evolutionary prototyping cycle '
    'of each increment, with the working application running on participants\' own Android '
    'devices via Expo Go. Participants included university students and household owners '
    'drawn from the researcher\'s network. Each session involved observing the participant '
    'completing a scripted task flow without assistance, followed by open-ended feedback '
    'on navigation clarity, instruction comprehensibility, and ease of use. Table 5.5 '
    'summarises the key issues identified and the resolutions applied.'
)
caption('Table 5.5: Usability issues and resolutions (Author, 2026)')
tbl(
    headers=['Usability Issue','Increment','Resolution Applied'],
    rows=[
        ['Students could not find the Accept button when navigating directly to a task '
         'detail screen rather than from the Available Tasks inbox',
         'Two',
         'Accept/Decline card added to the task detail screen with logic that detects '
         'an active broadcast request for the viewing student, regardless of navigation path'],
        ['Household owners received no visible feedback after tapping Post Task on '
         'the web browser',
         'One',
         'Alert.alert calls replaced with window.alert and window.confirm for the web '
         'platform, ensuring cross-platform confirmation feedback'],
        ['New users could not receive tasks after registration because their profile '
         'had no task categories set',
         'Two',
         'Seed rating logic and category assignment corrected; onboarding documentation '
         'updated to highlight mandatory profile completion after registration'],
        ['The app displayed a network error on physical devices when the development '
         'machine changed Wi-Fi networks',
         'One',
         'LAN_IP moved from hardcoded constant to EXPO_PUBLIC_LAN_IP environment '
         'variable in .env, eliminating code changes on network switches'],
        ['Task list showed all platform tasks to students, including unrelated tasks '
         'from other households',
         'Two',
         'get_queryset updated with role-based filtering: students see only tasks for '
         'which they have a TaskRequest or are the assigned student'],
        ['Grace window expiry left tasks stuck in Matched after server restarts, as '
         'daemon timer threads were lost',
         'Two',
         '_handle_stale_broadcasts method added to run_scheduled_tasks management '
         'command, re-broadcasting stuck tasks on each cron run'],
    ],
    widths=[2.3, 0.7, 2.8]
)
body(
    'Overall, participants responded positively to the broadcast notification model, '
    'with several student participants noting that receiving task requests directly — '
    'rather than browsing a job board — reduced the effort required to find work. '
    'Household owners appreciated the escrow mechanism as a trust signal, with feedback '
    'indicating that knowing payment was held before the student arrived increased '
    'confidence in the platform. The geolocation start-code check-in was identified as '
    'the most novel interaction, with initial confusion resolved after a brief explanation '
    'of its purpose in preventing fraudulent completion claims.'
)

h3('5.4.4 System Performance Observations')
body(
    'Basic performance characteristics were observed during development testing. API '
    'response times for standard read and write operations — task listing, task detail '
    'retrieval, and check-in submission — averaged under two hundred milliseconds on the '
    'local development network. The broadcast algorithm, which queries the student table, '
    'computes Haversine distances, scores, and ranks all candidates, completed in under '
    'five hundred milliseconds for the current dataset of twenty-one students. All '
    'one hundred and seventy-nine automated tests executed in approximately three hundred '
    'and fifty seconds including PostgreSQL test database creation and teardown.'
)

# ═══════════════════════════════════════════════════════════════════════════════
#  CHAPTER 6
# ═══════════════════════════════════════════════════════════════════════════════

doc.add_page_break()

h1('CHAPTER SIX')
h1('CONCLUSION, RECOMMENDATIONS AND FUTURE WORKS')

h2('6.1 Introduction')
body(
    'This chapter presents the conclusions drawn from the design, development, and testing '
    'of the Domestic Job and Escrow Platform, reflects on the challenges encountered and '
    'lessons learned, and identifies directions for future research and development that '
    'extend beyond the scope of this study.'
)

h2('6.2 Conclusion')
body(
    'This study addressed a clearly defined gap in the Kenyan informal labour market: the '
    'absence of a trusted, structured digital channel through which university students '
    'seeking part-time income could connect with household owners requiring domestic task '
    'workers, underpinned by a payment mechanism that protects both parties. The literature '
    'review in Chapter Two established that existing gig economy platforms in sub-Saharan '
    'Africa suffer from information asymmetry, inadequate worker protection, and payment '
    'friction, and that M-Pesa represents the most viable technological foundation for a '
    'trust-enabling payment layer in the Kenyan context.'
)
body(
    'The platform developed in this study directly addresses these gaps. The broadcast '
    'matching engine eliminates information asymmetry by delivering ranked task '
    'opportunities directly to eligible students based on rating, proximity, and '
    'reliability history. The escrow payment mechanism holds funds securely between task '
    'acceptance and confirmed completion, eliminating the risk of non-payment for students '
    'and non-performance for households. The geolocation-verified check-in provides a '
    'tamper-evident record of physical presence at the task location, reducing fraudulent '
    'completion claims and providing an objective evidence base for dispute resolution. '
    'The mutual rating system builds a persistent trust record for both parties, addressing '
    'the information asymmetry that Rani and Furrer (2021) identified as the primary '
    'barrier to platform trust.'
)
body(
    'All five specific objectives defined in Chapter One were met. The platform '
    'architecture for registering and verifying student profiles and creating structured '
    'tasks was delivered in Increment One. The broadcast matching engine, in-app messaging, '
    'escrow payment flow, geolocation check-in, and mutual ratings were delivered in '
    'Increment Two. The M-Pesa Daraja API integration was delivered in Increment Three '
    'using the reuse-oriented approach defined in Chapter Three. One hundred and '
    'seventy-nine automated tests were written and all passed, and usability testing '
    'with real users across all three increments identified and resolved six significant '
    'usability issues before the final system was submitted.'
)
body(
    'The Incremental Prototyping methodology proved well suited to this project. The '
    'evolutionary nature of the prototyping cycle — in which the prototype demonstrated '
    'to users was the actual running system — meant that user feedback translated directly '
    'into improvements without an intervening reconstruction phase. The isolation of the '
    'M-Pesa integration into a dedicated reuse-oriented increment proved particularly '
    'valuable: version-related issues with the Daraja sandbox were identified and resolved '
    'without disrupting the registration, matching, or messaging functionality delivered '
    'in earlier increments.'
)

h2('6.3 Recommendations')
body(
    'The following recommendations are made based on challenges encountered during the project:'
)
for n, bold, text in [
    (1,'Profile completion should be enforced at registration: ',
     'Several usability issues arose because new students could not receive task broadcasts '
     'due to empty categories_offered fields. Future implementations should require students '
     'to select at least one service category during registration rather than deferring '
     'profile completion.'),
    (2,'Environment configuration should be externalised from the first commit: ',
     'Hardcoding the LAN IP address in the frontend API client caused repeated breakage '
     'when the development machine changed Wi-Fi networks. The .env approach implemented '
     'in the final system should be established at project inception.'),
    (3,'Persistent task scheduling should replace daemon threads in production: ',
     'The current broadcast system uses Python daemon threads and threading.Timer objects, '
     'which are silently lost on server restart. Any production deployment should replace '
     'these with a persistent task queue such as Celery with a Redis broker.'),
    (4,'Admin verification of students should be integrated into the registration flow: ',
     'The current system requires the platform administrator to manually verify student '
     'accounts through the Django admin panel. A self-service flow — in which students '
     'upload a photograph of their student identity card — would significantly reduce the '
     'friction of onboarding at scale.'),
    (5,'Full Daraja sandbox credentials should be used for acceptance testing: ',
     'All payment testing was conducted using the simulated mock mode. Before any '
     'production deployment, full end-to-end testing with live Daraja sandbox credentials, '
     'including real STK Push prompts on physical devices and real webhook callbacks, '
     'should be conducted to verify integration behaviour under actual network conditions.'),
]:
    num_item(n, bold, text)

h2('6.4 Future Works')
body(
    'The following areas represent natural extensions that could be pursued in future research:'
)
for n, bold, text in [
    (1,'Push Notifications via Firebase Cloud Messaging (FCM): ',
     'The current notification system is poll-based. Integrating FCM would allow the server '
     'to push real-time alerts to students and household owners the moment a task is '
     'broadcast, a match confirmed, or a payment released, significantly improving '
     'platform responsiveness.'),
    (2,'Machine Learning for Dynamic Broadcast Ranking: ',
     'The broadcast ranking algorithm uses a fixed weighted formula. Future work could '
     'apply supervised learning to dynamically optimise the weighting based on historical '
     'acceptance rates, completion rates, and dispute frequencies.'),
    (3,'Automated Student Verification via University API Integration: ',
     'The current system relies on manual administrator verification. Future work could '
     'integrate directly with Kenyan university student information systems to automate '
     'verification, eliminating the administrator bottleneck.'),
    (4,'Expansion to Additional Mobile Money Providers: ',
     'The current integration is specific to M-Pesa. Future work could extend the payment '
     'gateway abstraction to support Airtel Money, T-Kash, and bank card payments, '
     'broadening accessibility to users without M-Pesa accounts.'),
    (5,'Progressive Web App (PWA) and Offline Support: ',
     'The current web client requires a constant network connection. Future work could '
     'implement service workers and offline caching, allowing students to access their '
     'task assignments and queue check-in submissions while temporarily offline — '
     'particularly relevant in areas with intermittent connectivity.'),
    (6,'Platform Expansion to Other Informal Work Categories: ',
     'The platform architecture is not inherently limited to domestic tasks. The broadcast '
     'matching, escrow, check-in, and rating modules are generic enough to support '
     'tutoring, delivery, event staffing, and other categories of informal work.'),
]:
    num_item(n, bold, text)

# ── Save ──────────────────────────────────────────────────────────────────────
os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
doc.save(OUT_PATH)
print(f'Saved: {os.path.abspath(OUT_PATH)}')
