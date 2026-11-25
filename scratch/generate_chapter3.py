"""
Generates Chapter 3 as a formatted Word document.
Run: python generate_chapter3.py
Output: Chapter_3_System_Development_Methodology.docx
"""

from docx import Document
from docx.shared import Pt, Inches, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import os

OUT_PATH = os.path.join(os.path.dirname(__file__),
                        '..', 'docs',
                        'Chapter_3_System_Development_Methodology.docx')

doc = Document()

# ── Page margins (2.5 cm all sides) ──────────────────────────────────────────
section = doc.sections[0]
section.top_margin    = Cm(2.54)
section.bottom_margin = Cm(2.54)
section.left_margin   = Cm(3.17)
section.right_margin  = Cm(2.54)

# ── Default body style ────────────────────────────────────────────────────────
style_normal = doc.styles['Normal']
style_normal.font.name = 'Times New Roman'
style_normal.font.size = Pt(12)
style_normal.paragraph_format.space_after  = Pt(0)
style_normal.paragraph_format.space_before = Pt(0)
style_normal.paragraph_format.line_spacing = Pt(24)   # double-space


def h1(text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(18)
    p.paragraph_format.space_after  = Pt(6)
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(14)
    run.font.name = 'Times New Roman'
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    return p


def h2(text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after  = Pt(4)
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(12)
    run.font.name = 'Times New Roman'
    return p


def h3(text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after  = Pt(2)
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(12)
    run.font.name = 'Times New Roman'
    return p


def body(text, indent=False):
    p = doc.add_paragraph()
    p.paragraph_format.space_after  = Pt(8)
    p.paragraph_format.line_spacing = Pt(24)
    if indent:
        p.paragraph_format.first_line_indent = Cm(1.27)
    run = p.add_run(text)
    run.font.name = 'Times New Roman'
    run.font.size = Pt(12)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    return p


def body_mixed(parts, indent=False):
    """parts = list of (text, bold) tuples"""
    p = doc.add_paragraph()
    p.paragraph_format.space_after  = Pt(8)
    p.paragraph_format.line_spacing = Pt(24)
    if indent:
        p.paragraph_format.first_line_indent = Cm(1.27)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    for text, bold in parts:
        run = p.add_run(text)
        run.bold = bold
        run.font.name = 'Times New Roman'
        run.font.size = Pt(12)
    return p


def bullet(text, level=0):
    p = doc.add_paragraph(style='List Bullet')
    p.paragraph_format.left_indent   = Cm(1.27 * (level + 1))
    p.paragraph_format.space_after   = Pt(4)
    p.paragraph_format.line_spacing  = Pt(24)
    run = p.add_run(text)
    run.font.name = 'Times New Roman'
    run.font.size = Pt(12)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    return p


def numbered(text, num):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent  = Cm(1.27)
    p.paragraph_format.space_after  = Pt(6)
    p.paragraph_format.line_spacing = Pt(24)
    run = p.add_run(f'{num}.\t{text}')
    run.font.name = 'Times New Roman'
    run.font.size = Pt(12)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    return p


def caption(text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after  = Pt(6)
    run = p.add_run(text)
    run.bold = True
    run.font.name = 'Times New Roman'
    run.font.size = Pt(11)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    return p


def add_table(headers, rows, col_widths=None):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Header row
    hdr_cells = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr_cells[i].text = h
        hdr_cells[i].paragraphs[0].runs[0].bold = True
        hdr_cells[i].paragraphs[0].runs[0].font.name = 'Times New Roman'
        hdr_cells[i].paragraphs[0].runs[0].font.size = Pt(11)
        hdr_cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        tc = hdr_cells[i]._tc
        tcPr = tc.get_or_add_tcPr()
        shd = OxmlElement('w:shd')
        shd.set(qn('w:fill'), '4472C4')
        shd.set(qn('w:color'), 'FFFFFF')
        shd.set(qn('w:val'),   'clear')
        tcPr.append(shd)
        for run in hdr_cells[i].paragraphs[0].runs:
            run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    # Data rows
    for r_idx, row in enumerate(rows):
        cells = table.rows[r_idx + 1].cells
        fill = 'DEEAF1' if r_idx % 2 == 0 else 'FFFFFF'
        for c_idx, val in enumerate(row):
            cells[c_idx].text = val
            cells[c_idx].paragraphs[0].runs[0].font.name = 'Times New Roman'
            cells[c_idx].paragraphs[0].runs[0].font.size = Pt(11)
            tc = cells[c_idx]._tc
            tcPr = tc.get_or_add_tcPr()
            shd = OxmlElement('w:shd')
            shd.set(qn('w:fill'), fill)
            shd.set(qn('w:val'),  'clear')
            tcPr.append(shd)

    # Column widths
    if col_widths:
        for row in table.rows:
            for i, cell in enumerate(row.cells):
                cell.width = Inches(col_widths[i])

    doc.add_paragraph()
    return table


def flow_box(text):
    """Simple shaded paragraph for flow diagrams."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after  = Pt(4)
    p.paragraph_format.left_indent  = Cm(1.27)
    run = p.add_run(text)
    run.font.name = 'Courier New'
    run.font.size = Pt(9)
    return p


# ═══════════════════════════════════════════════════════════════════════════════
#  DOCUMENT CONTENT
# ═══════════════════════════════════════════════════════════════════════════════

h1('CHAPTER THREE')
h1('SYSTEM DEVELOPMENT METHODOLOGY')

# ── 3.1 ────────────────────────────────────────────────────────────────────────
h2('3.1 Introduction')
body(
    'This chapter presents the methodology governing the design and development of the '
    'proposed web and mobile platform connecting university students to households requiring '
    'domestic task workers. Section 3.2 discusses the development methodology and justifies '
    'the choice of an Incremental Prototyping approach, combining Incremental Development as '
    'the core process model, Evolutionary Prototyping as the primary validation mechanism, and '
    'Reuse-Oriented Software Engineering to describe the integration of third-party components. '
    'This section describes how these models interact, presents a methodology diagram, and '
    'decomposes the development process into several increments mapped to the respective '
    'objectives defined in Chapter One. Section 3.3 outlines the key deliverables expected '
    'from this study, while Section 3.4 details the tools and techniques used throughout '
    'development, with justification for each choice.', indent=True
)

# ── 3.2 ────────────────────────────────────────────────────────────────────────
h2('3.2 Methodology')

body_mixed([
    ('This study adopts an ', False),
    ('Incremental Prototyping', True),
    (' methodology, combining Incremental Development as the core process model with '
     'Evolutionary Prototyping as the primary validation mechanism, and Reuse-Oriented '
     'Software Engineering for the integration of the M-Pesa Daraja API as a third-party '
     'payment component. According to Sommerville (2016), the three generic types of software '
     'process models are the Waterfall model, Incremental Development, and Reuse-Oriented '
     'Development, and most large systems are developed through a process that integrates '
     'elements of more than one of these generic types. This study deliberately avoids the '
     'Waterfall model for the same reasons identified by Khoza and Marnewick (2020), whose '
     'peer-reviewed study found that iterative approaches significantly outperform Waterfall '
     'across multiple criteria for project success, attributing this, at least in part, to the '
     'Waterfall model\'s inherent inflexibility in accommodating changing requirements and its '
     'tendency to expose risk late in the project lifecycle. In the context of this study, a '
     'late discovery of a critical issue in the integration of the M-Pesa payment API — which '
     'is explicitly identified as a dependency risk in Chapter One, Section 1.8 — would leave '
     'no room for remediation without threatening the entire project timeline.', False)
], indent=True)

body_mixed([
    ('The term ', False),
    ('Incremental Prototyping', True),
    (' as used in this study describes a specific combination of these models in which each '
     'development increment begins with an evolutionary prototype rather than a throwaway one. '
     'The critical distinction here is between throwaway prototyping, in which a prototype is '
     'built solely to elicit requirements and then discarded before real development begins, '
     'and evolutionary prototyping, in which the prototype is iteratively refined in direct '
     'response to user feedback until it becomes the final delivered system (Sommerville, 2016). '
     'This study employs the latter. Because the platform is built as a React Native and Django '
     'application deployed to users\'s own mobile devices during validation sessions, the '
     'prototype reviewed by a student or household owner on their phone is functionally '
     'identical to the delivered system. There is no separate "real" build that follows. Each '
     'cycle of feedback therefore improves the actual system rather than informing a separate '
     'construction phase, which is precisely what evolutionary prototyping describes. Yang, Wei, '
     'and Pu (2020), in a peer-reviewed study published in Frontiers in Psychology, demonstrated '
     'that mobile application design requires an iterative design process with user feedback '
     'collected at every stage to effectively evaluate and improve user experience, a finding '
     'that directly supports this methodological choice given the dual-role, mobile-first nature '
     'of this platform.', False)
], indent=True)

body(
    'According to Sommerville (2016), Incremental Development interleaves specification, '
    'development, and validation activities. Rather than developing the entire system at once, '
    'the system is built as a series of versions or increments, each adding new functionality '
    'to that delivered by the previous version. Because the highest-priority requirements are '
    'addressed in the earliest increments, the system can be evaluated by real users at an '
    'early stage, and if it does not meet user needs, the rework required is confined to the '
    'current increment rather than the whole system. This characteristic aligns directly with '
    'Objective v, which requires testing the platform against defined functional, usability, '
    'and performance criteria. In the incremental model, such testing is an ongoing activity '
    'embedded within the development cycle rather than a once-off exercise after the entire '
    'system is complete. The principal modules of the platform — user registration and '
    'verification, task posting and broadcast matching, in-app messaging, ratings, and payment '
    'processing — correspond naturally to individual increments that can be developed, '
    'prototyped, and tested in isolation before being integrated into the whole.', indent=True
)

body(
    'The Reuse-Oriented Software Engineering approach is employed specifically for the '
    'integration of the M-Pesa Daraja API. Reuse-oriented development focuses on assembling a '
    'system by integrating available components or Commercial-Off-The-Shelf (COTS) systems '
    'rather than implementing all required functionality from scratch (Sommerville, 2016). The '
    'process stages are component analysis, modification of requirements, design with reuse, '
    'and development and integration. The M-Pesa Daraja API is treated in this study as a COTS '
    'payment component: the platform does not implement payment infrastructure but integrates '
    'with Safaricom\'s documented API endpoints for STK Push initiation, callback handling, and '
    'transaction verification. By isolating this integration into a dedicated third increment, '
    'any issues arising from API versioning, sandbox limitations, or authentication changes — '
    'risks explicitly acknowledged in Chapter One, Section 1.8 — are contained within that '
    'increment and cannot propagate backwards to disrupt the core registration, matching, or '
    'messaging functionality delivered in Increments One and Two.', indent=True
)

body(
    'Evolutionary Prototyping runs continuously across all three increments, serving the dual '
    'purpose of UI/UX validation and functional verification with the two primary actors: '
    'university students and household owners. Dedema et al. (2024) identify trust, fairness, '
    'and transparency as three non-negotiable design values for any task-based employment '
    'platform, and Rani and Furrer (2021) demonstrate that mutual verification between workers '
    'and clients is the most effective mechanism through which a platform resolves information '
    'asymmetry. Both concerns are best addressed by placing real users in direct contact with '
    'working interface prototypes as early as possible, rather than deferring their involvement '
    'to a final testing phase. Each increment therefore begins with the user-facing components '
    'running on target devices, observed with selected students and household contacts, and '
    'refined before the next layer of backend development proceeds. This approach means that '
    'by the time Increment Three is complete, the platform will have passed through three full '
    'cycles of user validation, providing a strong empirical foundation for the structured '
    'functional, usability, and performance testing described in Section 3.6.', indent=True
)

# Table 3.1
caption('Table 3.1: Mapping of Incremental Prototyping stages to the specific objectives '
        'defined in Chapter One (Author, 2026)')
add_table(
    headers=['Stage', 'Model Applied', 'Key Activities', 'Maps to Objective'],
    rows=[
        ['Increment 1',
         'Incremental Development + Evolutionary Prototyping',
         'User registration, admin student verification workflow, task posting, and '
         'broadcast matching engine.',
         'Objective iii'],
        ['Increment 2',
         'Incremental Development + Evolutionary Prototyping',
         'Task inbox, first-to-accept matching, in-app messaging, escrow check-in '
         'verification, and mutual ratings.',
         'Objectives iii, iv'],
        ['Increment 3',
         'Reuse-Oriented Engineering + Evolutionary Prototyping',
         'M-Pesa Daraja API integration as a COTS component: STK Push, callback '
         'handling, escrow hold, release, and refund flows.',
         'Objective iv'],
        ['Throughout',
         'Evolutionary Prototyping',
         'Iterative UI/UX refinement and user validation with students and household '
         'owners on target devices.',
         'Objectives iii, v'],
        ['Final Stage',
         'Incremental Testing',
         'Functional, usability, and performance testing of all modules in the '
         'integrated system.',
         'Objective v'],
    ],
    col_widths=[1.0, 1.6, 2.6, 1.0]
)

# Table 3.2 flow
caption('Table 3.2: Incremental Prototyping flow diagram showing the progression of '
        'increments, the isolated Reuse-Oriented increment for M-Pesa integration, and '
        'continuous evolutionary prototyping (Author, 2026)')
flow_box('Requirements Specification (Chapters 1 & 2 — completed)')
flow_box('         |')
flow_box('         v')
flow_box('+---------------------+   +----------------------+   +---------------------+   +--------------------+')
flow_box('|    Increment 1      |-->|    Increment 2       |-->|    Increment 3      |-->| Integrated System  |')
flow_box('| Registration,       |   | Matching, Escrow,    |   | M-Pesa Daraja API   |   | Testing & Final    |')
flow_box('| Verification &      |   | Check-in, Chat &     |   | (Reuse-Oriented)    |   | Validation         |')
flow_box('| Task Posting        |   | Ratings              |   |                     |   |                    |')
flow_box('+---------------------+   +----------------------+   +---------------------+   +--------------------+')
flow_box('   ^                             ^                           ^                          ^')
flow_box('   +-----------------------------+---------------------------+--------------------------+')
flow_box('        Evolutionary Prototyping & User Validation (Continuous, all increments)')
doc.add_paragraph()

# ── 3.2.1 ──────────────────────────────────────────────────────────────────────
h3('3.2.1 Increment One: User Registration, Verification, and Task Posting')
body(
    'The first increment addresses the prerequisite from Objective iii of building a platform '
    'architecture to register verified student profiles and create structured tasks. It begins '
    'with evolutionary prototypes of the student and household owner registration interfaces, '
    'deployed to target users\' devices and reviewed for clarity and ease of use before backend '
    'development commences. The core student registration system is then developed, requesting '
    'personal information, the university name, and student identification number. Household '
    'owners provide contact information and location. An administrative verification workflow '
    'is developed to allow the system administrator to verify student registrations before '
    'activating their profiles in the active broadcast pool. Concurrently, the task creation '
    'and posting module is developed, allowing household owners to populate the platform with '
    'structured task requests specifying category, location, scheduled date and time, and '
    'financial compensation. Django\'s built-in ORM and admin panel serve as the primary tools '
    'for constructing the registration and verification workflow, with PostgreSQL as the '
    'underlying relational data store providing ACID-compliant transaction support from the '
    'outset.', indent=True
)

# ── 3.2.2 ──────────────────────────────────────────────────────────────────────
h3('3.2.2 Increment Two: Broadcast Matching, Escrow Check-In, Messaging, and Ratings')
body(
    'The second increment introduces the platform\'s broadcast matching engine, escrow-based '
    'payment flow, check-in verification system, in-app messaging, and mutual rating module, '
    'fulfilling Objectives iii and iv. Evolutionary prototypes of the student task inbox, '
    'check-in screen, and messaging interface are deployed to real users and refined before '
    'backend development of these modules begins. The broadcast matching engine ranks eligible '
    'verified students by rating, proximity, and reliability score, and distributes task '
    'requests to the top-ranked students in round-one, widening to a broader pool in round-two '
    'if no acceptance is received. The first student to accept wins the task atomically, using '
    'a database-level row lock to prevent race conditions. Once a student accepts, the '
    'household owner confirms the match and initiates an M-Pesa STK Push to hold payment in '
    'escrow. On arrival, the student enters a four-digit start code provided by the household '
    'owner; the server validates the code and records a GPS check-in against the task\'s '
    'geofence, moving the task to In Progress. Django REST Framework processes all API '
    'requests, and the PostgreSQL relational schema enables multi-criteria filtering across '
    'task category, location, rating, and scheduling dimensions. The rating module requires '
    'both parties to rate each other upon task completion, with scores stored against user '
    'profiles to inform future broadcast ranking.', indent=True
)

# ── 3.2.3 ──────────────────────────────────────────────────────────────────────
h3('3.2.3 Increment Three: M-Pesa Payment Integration (Reuse-Oriented)')
body(
    'The third increment addresses the payments aspect of Objective iv using a reuse-oriented '
    'approach, as described in Section 3.2. Following the stages of the reuse-oriented process '
    'outlined by Sommerville (2016), this increment begins with component analysis, examining '
    'the M-Pesa Daraja API in terms of OAuth 2.0 authentication, the STK Push transaction '
    'endpoint, and asynchronous webhook callbacks, all of which are documented by Safaricom. '
    'Next is requirements modification, in which the platform\'s escrow payment flow — holding '
    'funds at task acceptance and releasing them upon confirmed completion — is mapped to the '
    'Daraja sandbox environment. System design with reuse positions the Daraja API as a '
    'payment gateway component integrated into the Django backend via a dedicated service '
    'class, with an append-only transaction ledger recording every payment event for '
    'auditability and idempotency. Finally, development and integration connects this component '
    'to the task acceptance and completion flows delivered in Increments One and Two. '
    'Isolating this integration in its own increment ensures that any disruption or version '
    'change to the Daraja API does not affect the core registration, matching, or messaging '
    'functionality of the platform.', indent=True
)

# ── 3.2.4 ──────────────────────────────────────────────────────────────────────
h3('3.2.4 Continuous Evolutionary Prototyping and User Validation')
body(
    'Evolutionary Prototyping continues throughout each of the three increments, with working '
    'prototypes developed for the two primary user types: university students and household '
    'owners. Because the application runs on users\' own devices during validation sessions, '
    'each prototype is a live, functional version of the system rather than a throwaway '
    'mockup. User feedback collected during these sessions — covering navigation clarity, '
    'task visibility, check-in flow, and notification responsiveness — is applied directly to '
    'the running system in the subsequent development cycle. This continuous validation, as '
    'demonstrated by Yang et al. (2020), enables the early detection of usability issues, '
    'directly supporting Objective v, which requires the final platform to be tested against '
    'defined usability requirements. After completing Increment Three, the platform will have '
    'undergone three full cycles of user validation on real devices, providing an empirical '
    'foundation for the structured functional and performance testing described in Section 3.6.', indent=True
)

# ── 3.3 ────────────────────────────────────────────────────────────────────────
h2('3.3 Deliverables')
body('This study will produce the following key deliverables:', indent=True)

for num, text in enumerate([
    'A fully functional, cross-platform application — available as both a browser-based web '
    'application and a companion mobile application built with React Native — implementing the '
    'key modules described in Section 3.2: user registration and verification, task posting '
    'and broadcast matching, escrow payment processing, in-app messaging, ratings and reviews, '
    'and geolocation-verified check-in.',
    'A relational PostgreSQL database schema for the major data entities identified in the '
    'conceptual diagram in Chapter Two: user profiles, tasks, transactions, ratings, check-in '
    'records, and audit logs, with ACID-compliant transaction handling and an append-only '
    'ledger for all financial events.',
    'An administrative dashboard through which the system administrator can verify new student '
    'registrations, monitor platform activity, review location audit maps for disputed tasks, '
    'and resolve disputes with recorded outcomes, as indicated by actor responsibilities in '
    'Chapter Two, Section 2.5.',
    'This written research proposal and its subsequent final report, documenting the full '
    'research, design, development, and testing process.',
    'Source code for both the web and mobile applications, version-controlled and maintained '
    'on GitHub, accompanied by technical documentation to support future maintenance or '
    'extension of the platform.',
], start=1):
    numbered(text, num)

body(
    'The following milestones mark the examinable checkpoints of this study. At the conclusion '
    'of the proposal phase, this written research proposal constitutes the first formal '
    'deliverable, approved by the supervisor before development commences. At the conclusion '
    'of Increment One, a functional proof-of-concept demonstrating student registration, admin '
    'verification, and task posting will be submitted for review, supported by evolutionary '
    'prototypes of the registration interfaces reviewed with target users. At the conclusion '
    'of Increment Two, a working prototype of the broadcast matching engine, in-app messaging, '
    'escrow check-in, and ratings modules will be demonstrated, accompanied by the updated '
    'class diagram and ERD reflecting the implemented schema. At the conclusion of Increment '
    'Three, the integrated platform, including the M-Pesa Daraja sandbox payment flow, will '
    'be presented for structured functional, usability, and performance testing as defined in '
    'Section 3.6. The final deliverable is the complete project report, submitted alongside '
    'the source code repository on GitHub. The timeline for these milestones is presented in '
    'Appendix 1 (Gantt Chart).', indent=True
)

# ── 3.4 ────────────────────────────────────────────────────────────────────────
h2('3.4 List of Design Diagrams for Chapter 4')
body(
    'The object-oriented approach to analysis and design bridges the gap between user '
    'requirements and system realisation. Chapter 4 describes the structure and runtime '
    'behaviour of the platform through the following Unified Modelling Language (UML) and '
    'data design diagrams:', indent=True
)

for heading, content in [
    ('Use Case Diagram',
     'Establishes the system boundary and defines how Students, Household Owners, and System '
     'Administrators interact with core features including posting tasks, accepting broadcasts, '
     'initiating M-Pesa payments, performing geolocation check-ins, raising disputes, and '
     'leaving ratings.'),
    ('3.4.1  Class Diagram',
     'Represents the static structure of the system. It describes the domain objects — '
     'CustomUser, StudentProfile, HouseholdProfile, Task, TaskCompletion, TaskRequest, '
     'CheckIn, Dispute, Transaction, TransactionLedger, and Rating — their attributes and '
     'operations, and the relationships between them. This class diagram maps directly to the '
     'Django ORM model definitions.'),
    ('3.4.2  Sequence Diagrams',
     'Show the dynamic interactions between objects and the chronological order of message '
     'passing for complex operations. Nine sequence diagrams are produced for this platform, '
     'covering registration and login, task posting and broadcast, atomic first-to-accept, '
     'escrow payment, geolocation check-in verification, task completion and escrow release, '
     'dispute resolution, no-show detection, and cancellation with refund policy.'),
    ('3.4.3  Entity-Relationship Diagram (ERD)',
     'Transforms the object-oriented domain model into a relational schema by specifying '
     'primary keys, foreign keys, and cardinalities necessary for database integrity. The ERD '
     'covers all tables across the users, tasks, and payments applications, with UNIQUE '
     'constraints and nullable fields documented explicitly.'),
    ('3.4.4  Activity Diagram',
     'Describes the internal logic and flow of control through major processes, including '
     'decisions and actions such as the broadcast matching algorithm, task completion, '
     'cancellation with refund policy application, and dispute resolution branching.'),
]:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after  = Pt(4)
    p.paragraph_format.left_indent  = Cm(1.27)
    p.paragraph_format.line_spacing = Pt(24)
    r1 = p.add_run(heading + ': ')
    r1.bold = True
    r1.font.name = 'Times New Roman'
    r1.font.size = Pt(12)
    r2 = p.add_run(content)
    r2.font.name = 'Times New Roman'
    r2.font.size = Pt(12)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

# ── 3.5 ────────────────────────────────────────────────────────────────────────
h2('3.5 Development Tools')
body(
    'There is a direct line of reasoning for each choice in the technical stack. The '
    'objectives of this study address the trust issues and payment friction identified in the '
    'literature review; the Incremental Prototyping methodology therefore requires tools that '
    'support rapid evolutionary iteration, modular component reuse, and cross-platform '
    'consistency. Each tool is chosen to directly facilitate one or more phases of the '
    'methodology:', indent=True
)

caption('Table 3.4: Tools and technologies used in development (Author, 2026)')
add_table(
    headers=['Tool / Technology', 'Category', 'Justification & Alignment to Methodology'],
    rows=[
        ['Django & Django REST Framework (DRF)',
         'Backend Framework',
         'Accelerates evolutionary prototyping through its built-in admin panel, ORM that '
         'maps directly to class diagram entities, and DRF serialisers that define the RESTful '
         'API surface consumed by both web and mobile clients.'],
        ['React Native (Expo)',
         'Frontend Framework',
         'Single codebase targets both Android/iOS mobile and web browsers, ensuring '
         'full feature parity across all form factors and allowing prototypes reviewed on '
         'users\' own phones to be functionally identical to the delivered system.'],
        ['PostgreSQL',
         'Relational Database',
         'Provides full ACID compliance for concurrent escrow transactions, row-level locking '
         'for the atomic first-to-accept broadcast model, native JSONB support for flexible '
         'fields such as categories_offered and device_info, and native UUID types for '
         'idempotency keys on the transaction ledger.'],
        ['psycopg2-binary',
         'Database Driver',
         'Python adapter connecting the Django application layer to the PostgreSQL server, '
         'enabling the ORM to execute parameterised queries and transactions securely.'],
        ['M-Pesa Daraja API',
         'Payment Integration (COTS)',
         'Anchors the reuse-oriented strategy by providing an established, documented '
         'financial gateway that handles STK Push initiation, asynchronous payment callbacks, '
         'and B2C disbursement, solving the localised payment friction identified in the '
         'literature review without requiring custom payment infrastructure.'],
        ['Expo Location',
         'Device Location',
         'Captures a single high-accuracy GPS snapshot at check-in and task completion '
         'events only — never in the background — supporting the geolocation verification '
         'feature while respecting user privacy requirements.'],
        ['OpenStreetMap / Leaflet',
         'Mapping (Free Tier)',
         'Renders interactive map pins for task location setting and the admin dispute audit '
         'view without requiring a paid API key, keeping the system deployable in a '
         'resource-constrained student project environment.'],
        ['Git / GitHub',
         'Version Control',
         'Supports the incremental development model through feature branches, stable '
         'main-line releases, and rollback capability, directly addressing the risk-management '
         'rationale for choosing iterative over Waterfall development (Khoza & Marnewick, 2020).'],
        ['Figma',
         'Prototyping',
         'Produces low-fidelity wireframes at the start of each increment for review with '
         'target users before backend development begins, operationalising the evolutionary '
         'prototyping cycle.'],
    ],
    col_widths=[1.5, 1.3, 3.5]
)

# ── 3.6 ────────────────────────────────────────────────────────────────────────
h2('3.6 Testing Methodology')
body(
    'To ensure the platform is secure, reliable, and fits actual user workflows, testing '
    'follows a layered approach embedded within the incremental development cycle rather than '
    'applied only at the end of the project.', indent=True
)

h3('3.6.1 Unit Testing')
body(
    'Unit tests exercise code in isolated units, such as helper functions or model methods. '
    'Django\'s built-in unittest framework is used to run these tests. Unit tests verify that '
    'internal business logic — such as the Haversine distance calculation for geofence '
    'verification, average rating computation, reliability score reduction on cancellation, '
    'and idempotency key enforcement on the transaction ledger — behaves correctly before '
    'these components are integrated into larger subsystems. A test suite of over ninety unit '
    'and integration tests covering task lifecycle transitions, geolocation verification '
    'outcomes, cancellation refund policy, dispute resolution, and access control is '
    'maintained alongside the codebase.', indent=True
)

h3('3.6.2 Integration Testing')
body(
    'Integration testing verifies that different components of the system communicate as '
    'expected. The primary focus is on the interaction between the Django backend and the '
    'PostgreSQL database under concurrent load, the atomic row-level locking behaviour of '
    'the first-to-accept broadcast model, and the processing of simulated webhook callbacks '
    'from the M-Pesa Daraja sandbox. Integration tests confirm that escrow state transitions '
    '— from PendingDeposit through Held to Released or Refunded — are recorded correctly in '
    'both the Transaction record and the append-only TransactionLedger.', indent=True
)

h3('3.6.3 Black-Box Testing')
body(
    'Black-box testing verifies the system\'s adherence to functional requirements without '
    'reference to internal implementation. It confirms that a given user action — such as '
    'posting a task, accepting a broadcast request, entering a start code, or cancelling an '
    'assigned task — produces the expected outcome and user interface feedback, regardless of '
    'the underlying code path. This includes boundary conditions such as attempting to delete '
    'a task with held escrow, raising a second dispute on the same task, and submitting a '
    'check-in with a mock GPS location flag.', indent=True
)

h3('3.6.4 Usability Testing')
body(
    'Given the diverse technical backgrounds of the two user groups — university students and '
    'household owners — usability testing is conducted during the evolutionary prototyping '
    'phase of each increment. Evaluation consists of observational sessions in which real '
    'users interact with working prototypes on their own devices, with feedback collected on '
    'navigation clarity, task flow comprehension, check-in ease, and interface responsiveness '
    'across screen sizes. Issues identified in these sessions are resolved before the next '
    'increment begins, operationalising the continuous improvement cycle described by Yang '
    'et al. (2020).', indent=True
)

# ── 3.7 ────────────────────────────────────────────────────────────────────────
h2('3.7 Domain of Execution')
body(
    'The platform is designed for a modern web-and-mobile environment in which users expect '
    'full feature parity regardless of the device they are using. No functionality — from task '
    'creation through to M-Pesa payment release — is restricted to a single form factor. This '
    'is non-negotiable for two reasons grounded in the behaviour patterns of the target users:', indent=True
)

body_mixed([
    ('Omnichannel Access for Household Owners: ', True),
    ('While a household owner may prefer a desktop monitor for drafting detailed task '
     'descriptions or reviewing financial receipts, they also require the mobile flexibility '
     'to review incoming student task acceptances, communicate with an assigned worker, or '
     'authorise an M-Pesa escrow release while away from their computer.', False)
], indent=True)

body_mixed([
    ('Omnichannel Access for Students: ', True),
    ('While students primarily rely on mobile access to browse their task inbox, track job '
     'locations, and receive real-time notifications between classes, they also need full '
     'access on desktop environments when updating their profile categories, reviewing '
     'long-term earnings, or responding to a formal dispute.', False)
], indent=True)

body(
    'This requirement is met by the React Native application built with Expo, which compiles '
    'a single shared codebase to Android, iOS, and web browser targets. All UI changes, data '
    'validation rules, and new features are therefore simultaneously live on all platforms, '
    'with no risk of feature drift between the mobile and web versions.', indent=True
)

# ── 3.8 ────────────────────────────────────────────────────────────────────────
h2('3.8 Proposed Modules and System Architecture')

h3('3.8.1 Proposed Modules')
body(
    'The application is composed of five interrelated core functional modules, available on '
    'both desktop and mobile clients:', indent=True
)

for bold_part, rest in [
    ('Identity and Access Management (IAM): ',
     'Handles user registration, secure token-based login, role-based access control '
     '(Student, Household Owner, Administrator), student verification workflows, and location '
     'consent recording prior to the first GPS check-in.'),
    ('Task and Broadcast Matching: ',
     'Allows household owners to post, manage, and cancel tasks with an optional map pin and '
     'geofence radius. Automatically broadcasts tasks to eligible verified students ranked by '
     'rating, proximity, and reliability score, using an atomic first-to-accept model to '
     'prevent race conditions.'),
    ('Payments and Escrow: ',
     'Integrates the M-Pesa Daraja API to hold funds in escrow at task acceptance, release '
     'payment to the student upon confirmed completion, and process full or partial refunds '
     'according to the configurable cancellation policy. All financial events are recorded in '
     'an append-only transaction ledger with idempotency guarantees.'),
    ('Reputation and Trust: ',
     'Drives the mutual rating and review system following task completion, computing public '
     'trust scores for both roles that inform future broadcast matching priority. Includes a '
     'geolocation-verified check-in mechanism that records a GPS snapshot at the moment of '
     'arrival, confirming that the student was physically present at the task location.'),
    ('Notifications and Communication: ',
     'Handles all real-time status updates, keeping both parties informed at every stage of '
     'the task lifecycle. Includes in-app messaging between household owners and assigned '
     'students, and a dispute management channel with structured admin resolution.'),
]:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after  = Pt(4)
    p.paragraph_format.left_indent  = Cm(1.27)
    p.paragraph_format.line_spacing = Pt(24)
    r1 = p.add_run(bold_part)
    r1.bold = True
    r1.font.name = 'Times New Roman'
    r1.font.size = Pt(12)
    r2 = p.add_run(rest)
    r2.font.name = 'Times New Roman'
    r2.font.size = Pt(12)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

h3('3.8.2 System Architecture')
body(
    'The application uses a decoupled three-tier architecture to separate concerns, making '
    'the codebase maintainable and independently scalable:', indent=True
)

for bold_part, rest in [
    ('Presentation Tier: ',
     'A React Native application built with Expo serves a single shared codebase to mobile '
     'devices and web browsers. This ensures that UI changes, validation rules, and new '
     'features are simultaneously live on all platforms with no feature drift between form '
     'factors.'),
    ('Application (Logic) Tier: ',
     'Django and Django REST Framework provide a unified, consistent RESTful API surface. All '
     'business logic — broadcast matching, state machine transitions, escrow management, '
     'geolocation validation, and dispute resolution — is enforced at this layer, with requests '
     'processed identically regardless of whether they originate from a smartphone or a '
     'desktop browser.'),
    ('Data Tier: ',
     'PostgreSQL serves as the relational data store, providing ACID-compliant transaction '
     'handling for concurrent escrow operations, row-level locking for the atomic '
     'first-to-accept broadcast model, native JSONB support for flexible profile fields, and '
     'append-only table design for audit logs and transaction ledger entries. The database '
     'adapter psycopg2-binary connects the Django application layer to the PostgreSQL server.'),
]:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after  = Pt(4)
    p.paragraph_format.left_indent  = Cm(1.27)
    p.paragraph_format.line_spacing = Pt(24)
    r1 = p.add_run(bold_part)
    r1.bold = True
    r1.font.name = 'Times New Roman'
    r1.font.size = Pt(12)
    r2 = p.add_run(rest)
    r2.font.name = 'Times New Roman'
    r2.font.size = Pt(12)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

# ── Save ───────────────────────────────────────────────────────────────────────
os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
doc.save(OUT_PATH)
print(f'Saved: {os.path.abspath(OUT_PATH)}')
