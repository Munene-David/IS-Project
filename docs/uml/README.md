# Domestic Job Platform — UML Diagrams

All diagrams are written in **PlantUML** format (`.puml`).

## Files

| File | Diagram | Description |
|------|---------|-------------|
| `class_diagram.puml` | Class Diagram | All models, attributes, relationships, multiplicities |
| `seq_01_registration_login.puml` | Sequence 1 | User registration (Student & Household) and login |
| `seq_02_task_posting_broadcast.puml` | Sequence 2 | Task posting, broadcast rounds, eligibility scoring |
| `seq_03_student_accept.puml` | Sequence 3 | Atomic first-to-accept with row-level locking |
| `seq_04_escrow_payment.puml` | Sequence 4 | Confirm-match, M-Pesa STK Push, escrow hold |
| `seq_05_checkin_verification.puml` | Sequence 5 | GPS check-in, geo evaluation, start code validation |
| `seq_06_completion_escrow_release.puml` | Sequence 6 | Student completes job, household confirms, funds released |
| `seq_07_dispute_flow.puml` | Sequence 7 | Dispute raised → student responds → admin resolves |
| `seq_08_noshow_detection.puml` | Sequence 8 | Scheduled job detects no-shows, penalises student |
| `seq_09_cancellation_refund.puml` | Sequence 9 | Household/student cancellation with refund policy |

## How to Render

### Option 1 — VS Code Extension
Install **PlantUML** by `jebbs` from the VS Code marketplace.  
Open any `.puml` file and press `Alt+D` (or `Cmd+D` on Mac) to preview.

### Option 2 — Online
Paste the contents of any file at **https://www.plantuml.com/plantuml/uml/**

### Option 3 — CLI (requires Java + Graphviz)
```bash
java -jar plantuml.jar docs/uml/*.puml
```
Outputs `.png` files alongside each `.puml`.

### Option 4 — Docker
```bash
docker run --rm -v ${PWD}:/data plantuml/plantuml -tpng /data/docs/uml/*.puml
```
